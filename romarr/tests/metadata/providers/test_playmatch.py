"""PlayMatch metadata-adapter tests (T046, T047).

Same shape as the Hasheous tests: the adapter wraps the existing
identification :class:`PlayMatchBackend` and exposes the title-driven
methods as NotImplementedError contracts.
"""

from __future__ import annotations

import pytest

from romarr.identification.hashmatch.remote import PlayMatchBackend
from romarr.metadata import PROVIDER_REGISTRY
from romarr.metadata.providers.playmatch import PlayMatchProvider


def _make_backend() -> PlayMatchBackend:
    from romarr.config.settings import get_settings

    return PlayMatchBackend(get_settings())


def test_adapter_reuses_supplied_backend() -> None:
    backend = _make_backend()
    provider = PlayMatchProvider(backend=backend)
    assert provider.backend is backend


def test_adapter_default_constructs_a_backend() -> None:
    provider = PlayMatchProvider()
    assert isinstance(provider.backend, PlayMatchBackend)


def test_adapter_does_not_open_its_own_httpx_client() -> None:
    provider = PlayMatchProvider()
    assert not hasattr(provider, "_client") or provider._client is None  # type: ignore[attr-defined]


async def test_search_games_raises_not_implemented() -> None:
    provider = PlayMatchProvider()
    with pytest.raises(NotImplementedError):
        await provider.search_games("Sonic")


async def test_get_game_raises_not_implemented() -> None:
    provider = PlayMatchProvider()
    with pytest.raises(NotImplementedError):
        await provider.get_game("123")


async def test_get_cover_raises_not_implemented() -> None:
    provider = PlayMatchProvider()
    with pytest.raises(NotImplementedError):
        await provider.get_cover("123")


def test_self_registered() -> None:
    assert PROVIDER_REGISTRY.get("playmatch") is PlayMatchProvider


def test_excluded_from_scan_flow_via_capabilities() -> None:
    assert PlayMatchProvider.capabilities.invoked_in_scan is False


async def test_health_check_returns_true() -> None:
    provider = PlayMatchProvider()
    assert await provider.health_check() is True


def test_platform_mapping_returns_none() -> None:
    provider = PlayMatchProvider()
    assert provider.get_platform_mapping("megadrive") is None
