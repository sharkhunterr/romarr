"""Indexer registry (Phase 6).

Loads enabled indexers from the DB, decrypts their API keys via the
metadata encryption helper, and constructs configured
:class:`NewznabClient` instances. Per-indexer
:class:`RateLimiter` + :class:`CircuitBreaker` are cached on the
registry so the same in-memory limiter/breaker persists across calls.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from sqlalchemy import select

from romarr.identification.circuit_breaker import CircuitBreaker
from romarr.indexers.client import NewznabClient
from romarr.indexers.models import Indexer
from romarr.indexers.rate_limiter import RateLimiter
from romarr.metadata.encryption import decrypt

if TYPE_CHECKING:
    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession


class IndexerRegistry:
    """Cache + factory for :class:`NewznabClient` instances.

    Rate limiters and circuit breakers are constructed once per
    indexer id and re-used on every call so the gap-enforcement +
    failure-window state survive across requests.
    """

    def __init__(
        self,
        *,
        client_factory: type[NewznabClient] = NewznabClient,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client_factory = client_factory
        # A SHARED httpx.AsyncClient — passed into every NewznabClient
        # the registry builds so connection pooling works across
        # indexers without N separate pools. Tests that need to mock
        # transport pass their own client in.
        self._http = http_client
        self._limiters: dict[int, RateLimiter] = {}
        self._breakers: dict[int, CircuitBreaker] = {}

    def _limiter_for(self, indexer: Indexer) -> RateLimiter:
        existing = self._limiters.get(indexer.id)
        if (
            existing is not None
            and existing.seconds == float(indexer.rate_limit_seconds)
        ):
            return existing
        limiter = RateLimiter(seconds=float(indexer.rate_limit_seconds))
        self._limiters[indexer.id] = limiter
        return limiter

    def _breaker_for(self, indexer: Indexer) -> CircuitBreaker:
        existing = self._breakers.get(indexer.id)
        if existing is not None:
            return existing
        breaker = CircuitBreaker(f"indexers.{indexer.id}")
        self._breakers[indexer.id] = breaker
        return breaker

    def reset_breaker(self, indexer_id: int) -> None:
        """Force the named indexer's circuit breaker back to CLOSED.

        Operator-driven retries (the Test button) call this so the
        probe doesn't sit out an active cooldown from an earlier
        automatic burst of failures.
        """
        existing = self._breakers.get(indexer_id)
        if existing is not None:
            existing.reset()

    def _build_client(self, indexer: Indexer) -> NewznabClient:
        api_key: str | None = None
        if indexer.api_key_encrypted is not None:
            try:
                api_key = json.loads(
                    decrypt(indexer.api_key_encrypted).decode("utf-8")
                )
            except (json.JSONDecodeError, ValueError):
                # Older format: stored as raw plaintext bytes inside
                # the Fernet token.
                api_key = decrypt(indexer.api_key_encrypted).decode("utf-8")
        return self._client_factory(
            indexer_id=indexer.id,
            name=indexer.name,
            base_url=indexer.url,
            api_key=api_key,
            timeout_seconds=indexer.timeout_seconds,
            rate_limiter=self._limiter_for(indexer),
            breaker=self._breaker_for(indexer),
            result_limit=indexer.result_limit,
            client=self._http,
        )

    async def load_enabled(
        self, session: AsyncSession
    ) -> list[NewznabClient]:
        """Return clients for every indexer with at least one
        enable-* flag set."""
        rows = (
            (
                await session.execute(
                    select(Indexer).where(
                        (Indexer.enable_rss.is_(True))
                        | (Indexer.enable_automatic_search.is_(True))
                        | (Indexer.enable_interactive_search.is_(True))
                    )
                )
            )
            .scalars()
            .all()
        )
        return [self._build_client(row) for row in rows]

    async def get(
        self, session: AsyncSession, *, indexer_id: int
    ) -> NewznabClient | None:
        row = (
            await session.execute(
                select(Indexer).where(Indexer.id == indexer_id)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return self._build_client(row)


__all__ = ["IndexerRegistry"]
