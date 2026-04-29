"""Hasheous metadata-adapter tests (T044, T045).

The metadata Hasheous adapter wraps the existing identification
:class:`HasheousBackend` rather than opening its own httpx pool —
the test asserts the adapter holds a *reference* to the same
backend it was constructed with, and that the title-driven
methods all raise NotImplementedError (FR-002 + plan.md design).
"""

from __future__ import annotations

import pytest

from romarr.identification.hashmatch.remote import HasheousBackend
from romarr.metadata import PROVIDER_REGISTRY
from romarr.metadata.providers.hasheous import HasheousProvider


def _make_backend() -> HasheousBackend:
    """Build a HasheousBackend without touching real settings."""
    from romarr.config.settings import get_settings

    return HasheousBackend(get_settings())


# ---------------------------------------------------------------------------
# T044 — adapter shares the identification client (no second pool)
# ---------------------------------------------------------------------------


def test_adapter_reuses_supplied_backend() -> None:
    backend = _make_backend()
    provider = HasheousProvider(backend=backend)
    assert provider.backend is backend


def test_adapter_default_constructs_a_backend() -> None:
    """When no backend is supplied, the adapter builds one off
    :func:`romarr.config.get_settings`. Assert the type is the existing
    identification backend so we know we're not silently constructing
    a fresh httpx-only client."""
    provider = HasheousProvider()
    assert isinstance(provider.backend, HasheousBackend)


def test_adapter_does_not_open_its_own_httpx_client() -> None:
    """The adapter MUST NOT have an ``_client`` attribute distinct from
    the backend's. Per Article III: no duplicated HTTP pool."""
    provider = HasheousProvider()
    # Spec invariant: no httpx.AsyncClient on the adapter itself.
    # The pool, if any, lives on the wrapped backend.
    assert not hasattr(provider, "_client") or provider._client is None  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# T045 — title-driven methods are NotImplementedError contracts
# ---------------------------------------------------------------------------


async def test_search_games_raises_not_implemented() -> None:
    provider = HasheousProvider()
    with pytest.raises(NotImplementedError):
        await provider.search_games("Sonic")


async def test_get_game_raises_not_implemented() -> None:
    provider = HasheousProvider()
    with pytest.raises(NotImplementedError):
        await provider.get_game("123")


async def test_get_cover_raises_not_implemented() -> None:
    provider = HasheousProvider()
    with pytest.raises(NotImplementedError):
        await provider.get_cover("123")


# ---------------------------------------------------------------------------
# Registry + capabilities
# ---------------------------------------------------------------------------


def test_self_registered() -> None:
    assert PROVIDER_REGISTRY.get("hasheous") is HasheousProvider


def test_excluded_from_scan_flow_via_capabilities() -> None:
    """Hash-only API → invoked_in_scan=False keeps the standard
    title-driven refresh from invoking us at all."""
    assert HasheousProvider.capabilities.invoked_in_scan is False


async def test_health_check_returns_true() -> None:
    """Until the hash-driven refresh path lands, health-check is a
    pass-through that just confirms the adapter is constructed."""
    provider = HasheousProvider()
    assert await provider.health_check() is True


def test_platform_mapping_returns_none() -> None:
    """Hasheous keys on IGDB platform ids on the identification side;
    the metadata adapter exposes no per-platform mapping of its own."""
    provider = HasheousProvider()
    assert provider.get_platform_mapping("megadrive") is None
