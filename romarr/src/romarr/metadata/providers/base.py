""":class:`MetadataProvider` ABC + the per-provider runtime guards.

Every provider client (IGDB, ScreenScraper, …) inherits from
:class:`MetadataProvider` and implements the six abstract methods
listed in spec 002 FR-001:

  - ``configure(config)``      — apply credentials decrypted from
                                 :class:`MetadataProviderConfig.config_encrypted`
  - ``health_check()``         — quick reachability probe
  - ``search_games(query)``    — title-search, returns ranked candidates
  - ``get_game(provider_id)``  — full record for a known provider id
  - ``get_cover(provider_id)`` — cover bytes + content-type
  - ``get_platform_mapping(slug)`` — translate Romarr platform slug to
                                     the provider's native id

The base class wires three runtime guards every provider gets for free:

  1. **Circuit breaker** — 5 failures / 60 s opens the per-provider
     breaker (FR-004). Reuses :class:`identification.circuit_breaker.CircuitBreaker`
     to honour Article III ("no duplicated breaker library").
  2. **Tenacity retry** — up to 3 attempts with exponential backoff for
     :class:`romarr.metadata.errors.TransientError` (FR-004).
  3. **Token-bucket throttle** — proactive per-provider limiter (FR-004a).

Provider modules call :func:`romarr.metadata.providers.register_provider`
from import side so :func:`romarr.metadata.registry.load_enabled_providers`
can resolve them by ``name``.
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar

from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from romarr.identification.circuit_breaker import CircuitBreaker
from romarr.metadata.errors import (
    AuthError,
    NotFoundError,
    ProviderError,
    RateLimitError,
    TransientError,
)

if TYPE_CHECKING:
    from romarr.metadata.types import GameMetadata, GameSearchResult, ProviderField

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    """Static description of what a provider can contribute.

    The aggregator consults ``contributable_fields`` to skip fields
    a provider has explicitly disclaimed (e.g. RetroAchievements only
    contributes ``achievements_count``, FR-006). ``invoked_in_scan``
    is the FR-005 SteamGridDB knob: when False the provider is skipped
    by the scan-flow loader entirely.
    """

    name: str
    requires_auth: bool
    contributable_fields: frozenset[ProviderField]
    invoked_in_scan: bool = True


class TokenBucket:
    """Plain-Python token-bucket limiter used by the provider base.

    The bucket holds ``burst`` tokens at most and refills at ``rps``
    per second. ``acquire()`` awaits until a token is available — it
    never queues unbounded; concurrent acquirers are serialized through
    the internal lock so the refill computation stays consistent.
    """

    def __init__(
        self,
        *,
        rps: float,
        burst: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if rps <= 0:
            raise ValueError("rps must be positive")
        if burst <= 0:
            raise ValueError("burst must be positive")
        self._rps = rps
        self._burst = float(burst)
        self._tokens = float(burst)
        self._last = clock()
        self._clock = clock
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        now = self._clock()
        delta = now - self._last
        if delta > 0:
            self._tokens = min(self._burst, self._tokens + delta * self._rps)
            self._last = now

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                deficit = 1.0 - self._tokens
                wait_seconds = deficit / self._rps
                # Sleep without holding the lock-contended fast path open
                # forever — but we DO hold the lock during sleep so the
                # serialization invariant holds.
                await asyncio.sleep(wait_seconds)


class MetadataProvider(ABC):
    """Base class for every metadata provider.

    Concrete subclasses MUST set :attr:`capabilities` and implement the
    six abstract methods. Network-bound methods SHOULD invoke
    :meth:`_call` so they get the breaker + retry + throttle guards
    uniformly.
    """

    capabilities: ProviderCapabilities

    def __init__(
        self,
        *,
        rate_limit_rps: int = 5,
        rate_limit_burst: int = 10,
    ) -> None:
        self._breaker = CircuitBreaker(
            f"metadata.provider.{self.capabilities.name}"
        )
        self._bucket = TokenBucket(rps=rate_limit_rps, burst=rate_limit_burst)

    @property
    def name(self) -> str:
        return self.capabilities.name

    @property
    def requires_auth(self) -> bool:
        return self.capabilities.requires_auth

    # ------------------------------------------------------------------
    # Abstract surface (FR-001)
    # ------------------------------------------------------------------

    @abstractmethod
    def configure(self, config: dict[str, Any]) -> None:
        """Apply credentials/options. Called once after construction."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Cheap reachability probe; True iff the provider is usable."""

    @abstractmethod
    async def search_games(
        self, query: str, *, platform_slug: str | None = None
    ) -> list[GameSearchResult]:
        """Title-search returning provider-native ids + confidence."""

    @abstractmethod
    async def get_game(self, provider_game_id: str) -> GameMetadata:
        """Fetch the full record for a known provider id."""

    @abstractmethod
    async def get_cover(self, provider_game_id: str) -> tuple[bytes, str]:
        """Return ``(bytes, content_type)`` for the provider's cover."""

    @abstractmethod
    def get_platform_mapping(self, platform_slug: str) -> int | str | None:
        """Translate a Romarr platform slug to the provider's native id."""

    # ------------------------------------------------------------------
    # Shared helpers — used by concrete providers, no need to override.
    # ------------------------------------------------------------------

    async def _call(self, fn: Callable[[], Awaitable[T]]) -> T:
        """Run ``fn`` through breaker + retry + throttle.

        :class:`AuthError` and :class:`NotFoundError` are NOT retried;
        :class:`TransientError` and :class:`RateLimitError` are retried
        per tenacity's policy and then surface to the caller (so the
        breaker can record the failure).
        """
        await self._bucket.acquire()

        async def _attempt() -> T:
            return await self._breaker.call(fn)

        try:
            async for attempt in AsyncRetrying(
                reraise=True,
                stop=stop_after_attempt(3),
                wait=wait_exponential_jitter(initial=0.5, max=4.0),
                retry=retry_if_exception_type(
                    (TransientError, RateLimitError)
                ),
            ):
                with attempt:
                    return await _attempt()
        except RetryError as exc:  # pragma: no cover — reraise=True covers this
            raise ProviderError("retry budget exhausted") from exc
        # AsyncRetrying with reraise=True always either returns or raises.
        raise RuntimeError(
            "unreachable: AsyncRetrying must return or raise"
        )  # pragma: no cover


# Re-export the error classes alongside the ABC so providers can do
# ``from romarr.metadata.providers.base import MetadataProvider, AuthError, …``.
__all__ = [
    "AuthError",
    "MetadataProvider",
    "NotFoundError",
    "ProviderCapabilities",
    "ProviderError",
    "RateLimitError",
    "TokenBucket",
    "TransientError",
]


