"""RomM remote-push exporter (FR-015).

After every successful import targeting a library with
``exporter_romm_enabled=true``, the system POSTs to
``<romm_url>/api/platforms/<id>/scan`` to ask the running RomM
instance to re-scan that platform's directory. The push is
**best-effort** — any failure returns a structured
:class:`RommPushOutcome` and the import is recorded as success
with a warning (US9, FR-015). The exporter never raises, never
blocks the import.

Transient failures (connect error, timeout, 5xx) are retried up to
3 times with exponential-jitter backoff via :mod:`tenacity`.
Non-transient failures (4xx, malformed response) return immediately.

The RomM API key is stored encrypted on the ``library`` row; this
module decrypts via :mod:`romarr.metadata.encryption` on each
call so the plaintext never lives in memory between requests.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from romarr.metadata.encryption import decrypt


@dataclass(frozen=True)
class RommPushOutcome:
    """Result of one push attempt.

    ``status_code`` is ``None`` when the request never reached the
    server (DNS failure, connect timeout, etc.). ``error_message``
    is operator-facing and surfaces in the post-import warning.
    """

    success: bool
    status_code: int | None
    error_message: str | None
    duration_ms: int


class _TransientHttpError(Exception):
    """Internal marker so tenacity retries on connect errors,
    timeouts, and 5xx responses."""


async def push_to_romm(
    *,
    romm_url: str,
    encrypted_api_key: bytes,
    platform_id: int,
    timeout_s: float = 10.0,
    client: httpx.AsyncClient | None = None,
) -> RommPushOutcome:
    """POST ``/api/platforms/<id>/scan`` on the configured RomM
    instance with the encrypted API key decrypted at call time.

    ``client`` lets tests (and future callers) inject a shared
    :class:`httpx.AsyncClient` rather than spinning one up per
    request. When omitted, the function builds and disposes its
    own client.

    Returns :class:`RommPushOutcome`; never raises. Transient
    failures (connect / timeout / 5xx) are retried up to 3 times
    with exponential-jitter backoff before surfacing as
    ``success=False``.
    """
    started = time.perf_counter()
    bearer = decrypt(encrypted_api_key).decode("utf-8")
    url = f"{romm_url.rstrip('/')}/api/platforms/{platform_id}/scan"
    headers = {"Authorization": f"Bearer {bearer}"}

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=timeout_s)

    async def _attempt() -> httpx.Response:
        response = await client.post(url, headers=headers)
        if response.status_code >= 500:
            raise _TransientHttpError(
                f"romm returned {response.status_code}: "
                f"{response.text[:200]}"
            )
        return response

    try:
        async for attempt in AsyncRetrying(
            reraise=True,
            stop=stop_after_attempt(3),
            wait=wait_exponential_jitter(initial=0.5, max=4.0),
            retry=retry_if_exception_type(
                (
                    httpx.ConnectError,
                    httpx.ConnectTimeout,
                    httpx.ReadTimeout,
                    _TransientHttpError,
                )
            ),
        ):
            with attempt:
                response = await _attempt()
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        if response.is_success:
            return RommPushOutcome(
                success=True,
                status_code=response.status_code,
                error_message=None,
                duration_ms=elapsed_ms,
            )
        return RommPushOutcome(
            success=False,
            status_code=response.status_code,
            error_message=(
                f"romm rejected push: HTTP {response.status_code} "
                f"{response.text[:200]}"
            ),
            duration_ms=elapsed_ms,
        )
    except _TransientHttpError as exc:
        return RommPushOutcome(
            success=False,
            status_code=None,
            error_message=f"romm push failed after retries: {exc}",
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
        return RommPushOutcome(
            success=False,
            status_code=None,
            error_message=f"romm unreachable: {exc.__class__.__name__}: {exc}",
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
    except Exception as exc:
        return RommPushOutcome(
            success=False,
            status_code=None,
            error_message=f"romm push unexpected error: {exc}",
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
    finally:
        if owns_client:
            await client.aclose()


__all__ = ["RommPushOutcome", "push_to_romm"]
