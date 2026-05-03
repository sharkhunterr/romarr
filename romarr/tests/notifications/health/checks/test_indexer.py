"""Tests for IndexerHealthCheck (spec 011 T043)."""

from __future__ import annotations

import pytest

from romarr.notifications.health.checks.indexer import IndexerHealthCheck
from romarr.notifications.types import HealthStatus


class _FakeCaps:
    """Stand-in for ``IndexerCapabilities`` — we only need
    truthy presence."""

    pass


class _FakeClient:
    """Minimal ``NewznabClient`` substitute. The real type's
    surface is much wider; the health check only consults
    ``caps()`` and ``aclose()``."""

    def __init__(
        self, *, raises: BaseException | None = None
    ) -> None:
        self._raises = raises
        self.aclose_called = False

    async def caps(self) -> _FakeCaps:
        if self._raises is not None:
            raise self._raises
        return _FakeCaps()

    async def aclose(self) -> None:
        self.aclose_called = True


@pytest.mark.asyncio
async def test_caps_reachable_returns_ok() -> None:
    client = _FakeClient()

    async def _factory():  # type: ignore[no-untyped-def]
        return client

    check = IndexerHealthCheck(
        indexer_id=1,
        client_factory=_factory,
        component_id="indexer.1",
    )
    result = await check.run()
    assert result.status is HealthStatus.OK
    assert client.aclose_called is True


@pytest.mark.asyncio
async def test_caps_failure_returns_warning() -> None:
    """A failing caps probe surfaces as warning (the indexer
    is configured but currently unreachable). The client is
    still closed."""
    client = _FakeClient(raises=RuntimeError("connection reset"))

    async def _factory():  # type: ignore[no-untyped-def]
        return client

    check = IndexerHealthCheck(
        indexer_id=2,
        client_factory=_factory,
        component_id="indexer.2",
    )
    result = await check.run()
    assert result.status is HealthStatus.WARNING
    assert "RuntimeError" in result.message
    assert "connection reset" in result.message
    assert client.aclose_called is True


@pytest.mark.asyncio
async def test_factory_failure_returns_error() -> None:
    """Construction-time failure (DB row missing, decryption
    failed, etc.) surfaces as error rather than warning —
    misconfiguration is louder than transient network."""

    async def _factory():  # type: ignore[no-untyped-def]
        raise RuntimeError("indexer row not found")

    check = IndexerHealthCheck(
        indexer_id=99,
        client_factory=_factory,
        component_id="indexer.99",
    )
    result = await check.run()
    assert result.status is HealthStatus.ERROR
    assert "indexer row not found" in result.message
