"""Metadata provider health check (spec 011 T048, FR-018).

Wraps a single :class:`MetadataProvider` instance and probes its
``health_check()`` reachability method. One probe per configured
provider — the engine builds the list of checks during lifespan
startup based on ``metadata_provider_config.enabled``.

The check returns ``ok`` when the provider's ``health_check()``
yields ``True``, ``warning`` when it yields ``False`` (the
provider is configured but unreachable / misauthenticated), and
``error`` for any exception that escapes the provider's own
swallow-and-log path. The engine's outer ``run_check`` timeout
still applies as the last line of defense.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from romarr.notifications.types import (
    ComponentCategory,
    HealthCheckResult,
    HealthStatus,
)

if TYPE_CHECKING:
    from romarr.metadata.providers.base import MetadataProvider


@dataclass
class MetadataProviderHealthCheck:
    """One probe per configured metadata provider.

    ``provider`` is injected by the lifespan wiring (so tests
    can pass a stub that returns ``True``/``False``/raises).
    The ``component_id`` is namespaced as ``metadata.<provider>``
    so the operator UI can show "IGDB unreachable" without
    aggregating across the metadata layer.
    """

    provider: "MetadataProvider"
    component_id: str = "metadata.unknown"
    category: ComponentCategory = ComponentCategory.METADATA

    async def run(self) -> HealthCheckResult:
        try:
            healthy = await self.provider.health_check()
        except Exception as exc:
            return HealthCheckResult(
                component=self.component_id,
                category=self.category,
                status=HealthStatus.ERROR,
                message=f"{exc.__class__.__name__}: {exc}",
            )

        if healthy:
            return HealthCheckResult(
                component=self.component_id,
                category=self.category,
                status=HealthStatus.OK,
                message="provider reachable",
            )
        return HealthCheckResult(
            component=self.component_id,
            category=self.category,
            status=HealthStatus.WARNING,
            message="provider unreachable or misauthenticated",
        )


__all__ = ["MetadataProviderHealthCheck"]
