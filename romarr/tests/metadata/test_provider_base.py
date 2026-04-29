"""Provider base class — breaker, retry, throttle (T020)."""

from __future__ import annotations

from typing import Any

import pytest

from romarr.metadata import (
    GameMetadata,
    GameSearchResult,
    MetadataProvider,
    ProviderCapabilities,
    ProviderField,
)
from romarr.metadata.errors import AuthError, NotFoundError, TransientError
from romarr.metadata.providers.base import TokenBucket


class _Stub(MetadataProvider):
    capabilities = ProviderCapabilities(
        name="stub",
        requires_auth=False,
        contributable_fields=frozenset({ProviderField.TITLE}),
    )

    def configure(self, config: dict[str, Any]) -> None:
        pass

    async def health_check(self) -> bool:
        return True

    async def search_games(
        self, query: str, *, platform_slug: str | None = None
    ) -> list[GameSearchResult]:
        return []

    async def get_game(self, provider_game_id: str) -> GameMetadata:
        raise NotImplementedError

    async def get_cover(self, provider_game_id: str) -> tuple[bytes, str]:
        raise NotImplementedError

    def get_platform_mapping(self, platform_slug: str) -> int | str | None:
        return None


async def test_call_succeeds() -> None:
    p = _Stub(rate_limit_rps=100, rate_limit_burst=100)
    n = 0

    async def hit() -> int:
        nonlocal n
        n += 1
        return 7

    out = await p._call(hit)
    assert out == 7
    assert n == 1


async def test_call_retries_transient_errors() -> None:
    p = _Stub(rate_limit_rps=100, rate_limit_burst=100)
    attempts = 0

    async def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise TransientError("nope")
        return "ok"

    out = await p._call(flaky)
    assert out == "ok"
    assert attempts == 3


async def test_call_does_not_retry_auth_error() -> None:
    p = _Stub(rate_limit_rps=100, rate_limit_burst=100)
    attempts = 0

    async def boom() -> None:
        nonlocal attempts
        attempts += 1
        raise AuthError("bad creds")

    with pytest.raises(AuthError):
        await p._call(boom)
    assert attempts == 1  # NOT retried


async def test_call_does_not_retry_not_found() -> None:
    p = _Stub(rate_limit_rps=100, rate_limit_burst=100)
    attempts = 0

    async def gone() -> None:
        nonlocal attempts
        attempts += 1
        raise NotFoundError("nope")

    with pytest.raises(NotFoundError):
        await p._call(gone)
    assert attempts == 1


def test_token_bucket_rejects_invalid_params() -> None:
    with pytest.raises(ValueError):
        TokenBucket(rps=0, burst=1)
    with pytest.raises(ValueError):
        TokenBucket(rps=1, burst=0)


async def test_token_bucket_acquire_burst_then_throttles() -> None:
    """The burst quota allows ``burst`` immediate acquires; the next one
    must wait ``1/rps`` seconds."""
    clock = [0.0]
    bucket = TokenBucket(rps=10, burst=3, clock=lambda: clock[0])

    # Burst of 3 immediate acquires (no clock advance needed).
    for _ in range(3):
        await bucket.acquire()

    # Next acquire requires waiting; advance the clock manually so the
    # internal asyncio.sleep returns immediately and the refill grants
    # a token.
    clock[0] = 0.2  # 0.2 s * 10 rps = 2 tokens refilled
    await bucket.acquire()  # one of the freshly refilled tokens
