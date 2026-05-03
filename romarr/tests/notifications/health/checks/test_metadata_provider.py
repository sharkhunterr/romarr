"""Tests for MetadataProviderHealthCheck (spec 011 T048)."""

from __future__ import annotations

from typing import Any

import pytest

from romarr.notifications.health.checks.metadata_provider import (
    MetadataProviderHealthCheck,
)
from romarr.notifications.types import HealthStatus


class _StubProvider:
    """Minimal stand-in for ``MetadataProvider`` — only
    ``health_check`` is exercised by this check class."""

    def __init__(
        self, *, returns: bool | None = None, raises: BaseException | None = None
    ) -> None:
        self._returns = returns
        self._raises = raises

    async def health_check(self) -> bool:
        if self._raises is not None:
            raise self._raises
        assert self._returns is not None
        return self._returns


@pytest.mark.asyncio
async def test_each_provider_health_check_ok() -> None:
    """``health_check() -> True`` → ``ok``."""
    provider: Any = _StubProvider(returns=True)
    check = MetadataProviderHealthCheck(
        provider=provider, component_id="metadata.igdb"
    )
    result = await check.run()
    assert result.status is HealthStatus.OK
    assert result.component == "metadata.igdb"


@pytest.mark.asyncio
async def test_each_provider_health_check_warning_on_unreachable() -> None:
    """``health_check() -> False`` → ``warning``.

    The provider is configured but the credential / endpoint
    isn't usable right now. The engine surfaces this as a
    warning so the operator can fix it without the rest of the
    stack going to ``error``."""
    provider: Any = _StubProvider(returns=False)
    check = MetadataProviderHealthCheck(
        provider=provider, component_id="metadata.screenscraper"
    )
    result = await check.run()
    assert result.status is HealthStatus.WARNING
    assert result.component == "metadata.screenscraper"


@pytest.mark.asyncio
async def test_each_provider_health_check_error_on_exception() -> None:
    """An exception escaping the provider's own swallow path
    surfaces as ``error`` with the class name + message."""
    provider: Any = _StubProvider(
        raises=RuntimeError("network unreachable")
    )
    check = MetadataProviderHealthCheck(
        provider=provider, component_id="metadata.mobygames"
    )
    result = await check.run()
    assert result.status is HealthStatus.ERROR
    assert "RuntimeError" in result.message
    assert "network unreachable" in result.message
