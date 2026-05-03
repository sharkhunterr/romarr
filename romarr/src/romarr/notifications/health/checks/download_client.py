"""Download client health check (spec 011 T044).

Wraps a single :class:`DownloadClient` and probes its
``test_connection()`` adapter — the same call the Settings UI
uses for the "Test" button, so a passing health check
guarantees the search-round's grab path would also reach the
client. Per FR-018: one component instance per configured
download client.

``client_factory`` is injected so the lifespan wiring can hand
in the production ``DownloadClientRegistry``-backed factory
while tests pass a stub.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from romarr.notifications.types import (
    ComponentCategory,
    HealthCheckResult,
    HealthStatus,
)

if TYPE_CHECKING:
    from romarr.downloaders.base import DownloadClient


ClientFactory = Callable[[], Awaitable["DownloadClient"]]


@dataclass
class DownloadClientHealthCheck:
    """One probe per configured download client.

    The component_id is namespaced as
    ``downloadclient.<id>`` so the operator UI can show
    "qBittorrent client 1 unreachable" without aggregating
    across the download-client layer.
    """

    client_id: int
    client_factory: ClientFactory
    component_id: str = "downloadclient.unknown"
    category: ComponentCategory = ComponentCategory.DOWNLOAD_CLIENT

    async def run(self) -> HealthCheckResult:
        try:
            client = await self.client_factory()
        except Exception as exc:
            return HealthCheckResult(
                component=self.component_id,
                category=self.category,
                status=HealthStatus.ERROR,
                message=(
                    f"client construction failed: "
                    f"{exc.__class__.__name__}: {exc}"
                ),
            )

        try:
            try:
                version = await client.test_connection()
            except Exception as exc:
                return HealthCheckResult(
                    component=self.component_id,
                    category=self.category,
                    status=HealthStatus.WARNING,
                    message=(
                        f"connection test failed: "
                        f"{exc.__class__.__name__}: {exc}"
                    ),
                )
        finally:
            close = getattr(client, "aclose", None)
            if close is not None:
                try:
                    await close()
                except Exception:
                    pass

        return HealthCheckResult(
            component=self.component_id,
            category=self.category,
            status=HealthStatus.OK,
            message=f"client reachable (version {version})",
        )


__all__ = ["ClientFactory", "DownloadClientHealthCheck"]
