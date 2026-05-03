"""Tests for DownloadClientHealthCheck (spec 011 T044)."""

from __future__ import annotations

import pytest

from romarr.notifications.health.checks.download_client import (
    DownloadClientHealthCheck,
)
from romarr.notifications.types import HealthStatus


class _FakeClient:
    """Minimal stand-in for ``DownloadClient``. The real
    contract has more methods; the health check only uses
    ``test_connection()`` and ``aclose()``."""

    def __init__(
        self,
        *,
        version: str = "4.6.5",
        raises: BaseException | None = None,
    ) -> None:
        self._version = version
        self._raises = raises
        self.aclose_called = False

    async def test_connection(self) -> str:
        if self._raises is not None:
            raise self._raises
        return self._version

    async def aclose(self) -> None:
        self.aclose_called = True


@pytest.mark.asyncio
async def test_connection_test_returns_ok_with_version() -> None:
    client = _FakeClient(version="qBittorrent 4.6.5")

    async def _factory():  # type: ignore[no-untyped-def]
        return client

    check = DownloadClientHealthCheck(
        client_id=1,
        client_factory=_factory,
        component_id="downloadclient.1",
    )
    result = await check.run()
    assert result.status is HealthStatus.OK
    assert "qBittorrent 4.6.5" in result.message
    assert client.aclose_called is True


@pytest.mark.asyncio
async def test_connection_failure_returns_warning() -> None:
    """A connection-test failure surfaces as warning. The
    client is still closed cleanly."""
    client = _FakeClient(raises=RuntimeError("HTTP 401"))

    async def _factory():  # type: ignore[no-untyped-def]
        return client

    check = DownloadClientHealthCheck(
        client_id=2,
        client_factory=_factory,
        component_id="downloadclient.2",
    )
    result = await check.run()
    assert result.status is HealthStatus.WARNING
    assert "HTTP 401" in result.message
    assert client.aclose_called is True


@pytest.mark.asyncio
async def test_factory_failure_returns_error() -> None:
    """Construction-time failure surfaces as error."""

    async def _factory():  # type: ignore[no-untyped-def]
        raise RuntimeError("download_client row missing")

    check = DownloadClientHealthCheck(
        client_id=99,
        client_factory=_factory,
        component_id="downloadclient.99",
    )
    result = await check.run()
    assert result.status is HealthStatus.ERROR
    assert "download_client row missing" in result.message
