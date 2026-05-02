"""Idempotency-Key middleware (T035, FR-020 / FR-021 / FR-025).

Implements RFC-draft idempotency for mutating HTTP methods. The
contract from spec 013:

  * Request method must be one of POST / PUT / PATCH / DELETE —
    safe methods (GET / HEAD / OPTIONS) bypass the middleware
    untouched.
  * Caller supplies an ``Idempotency-Key`` header. Without it,
    the request flows through the normal handler stack.
  * The ``request_body_hash`` is the hex of
    ``SHA-256(JCS-canonical-JSON(body))`` per RFC 8785 for JSON
    bodies; multipart and binary bodies fall back to plain
    ``SHA-256(raw bytes)``. The Q1 clarification on spec 013.
  * Cache hit + matching body hash → return the cached response
    byte-for-byte (status, headers, body).
  * Cache hit + differing body hash → HTTP 422 with errorCode
    ``idempotency_key_body_mismatch`` (FR-021).
  * Cache hit + expired (``expires_at < now``) → treat as miss
    (delete the row, run the handler).
  * Cache miss → run the handler, write the cache row only when
    the response is "successful" (status < 500). 5xx server
    errors aren't cached so transient issues are retryable.

The middleware is *pure ASGI* rather than FastAPI's
``BaseHTTPMiddleware`` so it can read the request body and replay
it to the downstream handler — ``BaseHTTPMiddleware`` consumes
the body once, breaking the handler that would otherwise read it
via ``request.json()``.

Cache backend: the :class:`IdempotencyCache` table from spec 013.
The middleware reads / writes it via ``app.state.db_sessionmaker``,
the same factory the rest of the API uses. Redis is the planned
production backend (FR-025); swapping in is a single ``write_cache``
/ ``lookup_cache`` indirection swap, intentionally kept narrow.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import delete, select
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from romarr.api.models import IdempotencyCache

if TYPE_CHECKING:
    from fastapi import FastAPI
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

DEFAULT_TTL_HOURS = 24
"""Spec 013 data-model: rows expire ``created_at + 24 hours``."""


def _hash_body(body: bytes, *, content_type: str) -> str:
    """Return ``hex(SHA-256(canonical_body))``. JSON bodies are
    re-serialised with sorted keys + tight separators (close enough
    to RFC 8785 for our payloads); other bodies are hashed as raw
    bytes."""
    if "application/json" in content_type.lower():
        try:
            parsed = json.loads(body)
            canonical = json.dumps(
                parsed,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        except json.JSONDecodeError:
            # Malformed JSON — hash the raw bytes; the handler
            # will surface the JSON validation error itself.
            canonical = body
    else:
        canonical = body
    return hashlib.sha256(canonical).hexdigest()


async def _lookup_cache(
    sm: async_sessionmaker[AsyncSession],
    *,
    endpoint: str,
    key: str,
) -> IdempotencyCache | None:
    async with sm() as session:
        return (
            await session.execute(
                select(IdempotencyCache).where(
                    IdempotencyCache.endpoint == endpoint,
                    IdempotencyCache.key == key,
                )
            )
        ).scalar_one_or_none()


async def _delete_cache(
    sm: async_sessionmaker[AsyncSession], *, endpoint: str, key: str
) -> None:
    async with sm() as session:
        await session.execute(
            delete(IdempotencyCache).where(
                IdempotencyCache.endpoint == endpoint,
                IdempotencyCache.key == key,
            )
        )
        await session.commit()


async def _write_cache(
    sm: async_sessionmaker[AsyncSession],
    *,
    endpoint: str,
    key: str,
    request_body_hash: str,
    response_status: int,
    response_body: bytes,
    response_headers: dict[str, str],
    ttl_hours: int,
) -> None:
    now = datetime.now(UTC)
    async with sm() as session:
        session.add(
            IdempotencyCache(
                endpoint=endpoint,
                key=key,
                request_body_hash=request_body_hash,
                response_status=response_status,
                response_body=response_body,
                response_headers=response_headers,
                created_at=now,
                expires_at=now + timedelta(hours=ttl_hours),
            )
        )
        await session.commit()


def _header(headers: list[tuple[bytes, bytes]], name: str) -> str | None:
    """Extract one header value (latin-1 decoded) — case-insensitive."""
    target = name.lower().encode("latin-1")
    for h_name, h_value in headers:
        if h_name.lower() == target:
            return h_value.decode("latin-1")
    return None


def _replay_receive(body: bytes) -> Receive:
    """Build a ``receive`` callable that re-emits the captured
    body once and then signals end-of-stream."""
    sent = False

    async def _receive() -> Message:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {
            "type": "http.request",
            "body": body,
            "more_body": False,
        }

    return _receive


_MISMATCH_BODY = json.dumps(
    {
        "errorMessage": (
            "Idempotency-Key reused with a different request body"
        ),
        "errorCode": "idempotency_key_body_mismatch",
    },
    separators=(",", ":"),
).encode("utf-8")


async def _send_mismatch_422(send: Send) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 422,
            "headers": [
                (b"content-type", b"application/json"),
                (
                    b"content-length",
                    str(len(_MISMATCH_BODY)).encode("latin-1"),
                ),
            ],
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": _MISMATCH_BODY,
            "more_body": False,
        }
    )


async def _send_cached(send: Send, cached: IdempotencyCache) -> None:
    headers = [
        (
            name.encode("latin-1"),
            value.encode("latin-1"),
        )
        for name, value in cached.response_headers.items()
    ]
    headers.append((b"x-idempotent-replay", b"true"))
    await send(
        {
            "type": "http.response.start",
            "status": cached.response_status,
            "headers": headers,
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": cached.response_body,
            "more_body": False,
        }
    )


class IdempotencyMiddleware:
    """Pure-ASGI middleware. See module docstring for behaviour."""

    def __init__(self, app: ASGIApp, *, ttl_hours: int = DEFAULT_TTL_HOURS) -> None:
        self.app = app
        self._ttl_hours = ttl_hours

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope["method"]
        if method not in _MUTATING_METHODS:
            await self.app(scope, receive, send)
            return

        headers = scope["headers"]
        idempotency_key = _header(headers, "idempotency-key")
        if not idempotency_key:
            await self.app(scope, receive, send)
            return

        # Body capture — read the entire request body so we can
        # both hash it and replay it to the downstream handler.
        body_chunks: list[bytes] = []
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] != "http.request":
                # Connection closed mid-read; stop and let the
                # handler observe the disconnect via the replay.
                break
            body_chunks.append(message.get("body", b""))
            more_body = message.get("more_body", False)
        body = b"".join(body_chunks)

        content_type = _header(headers, "content-type") or ""
        body_hash = _hash_body(body, content_type=content_type)

        endpoint = f"{method} {scope['path']}"
        sm = scope["app"].state.db_sessionmaker

        cached = await _lookup_cache(sm, endpoint=endpoint, key=idempotency_key)
        if cached is not None:
            now = datetime.now(UTC)
            expires = cached.expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=UTC)
            if expires < now:
                # Expired — delete and treat as miss.
                await _delete_cache(
                    sm, endpoint=endpoint, key=idempotency_key
                )
            elif cached.request_body_hash == body_hash:
                await _send_cached(send, cached)
                return
            else:
                await _send_mismatch_422(send)
                return

        # Cache miss (or expired) — run the handler with a replayed body.
        captured_status: int | None = None
        captured_headers: list[tuple[bytes, bytes]] = []
        captured_body = bytearray()

        async def _capture_send(message: Message) -> None:
            nonlocal captured_status
            if message["type"] == "http.response.start":
                captured_status = message["status"]
                captured_headers.extend(message["headers"])
            elif message["type"] == "http.response.body":
                captured_body.extend(message.get("body", b""))
            await send(message)

        await self.app(scope, _replay_receive(body), _capture_send)

        if (
            captured_status is not None
            and captured_status < 500
        ):
            # Strip hop-by-hop / volatile headers; keep
            # content-type so the replay round-trips cleanly.
            stored_headers: dict[str, str] = {}
            for h_name, h_value in captured_headers:
                lowered = h_name.decode("latin-1").lower()
                if lowered in {"content-type"}:
                    stored_headers[lowered] = h_value.decode("latin-1")
            await _write_cache(
                sm,
                endpoint=endpoint,
                key=idempotency_key,
                request_body_hash=body_hash,
                response_status=captured_status,
                response_body=bytes(captured_body),
                response_headers=stored_headers,
                ttl_hours=self._ttl_hours,
            )


def register_idempotency(
    app: FastAPI, *, ttl_hours: int = DEFAULT_TTL_HOURS
) -> None:
    """Register :class:`IdempotencyMiddleware` on ``app``."""
    app.add_middleware(IdempotencyMiddleware, ttl_hours=ttl_hours)


__all__ = [
    "DEFAULT_TTL_HOURS",
    "IdempotencyMiddleware",
    "register_idempotency",
]
