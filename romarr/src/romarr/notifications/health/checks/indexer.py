"""Indexer health check (spec 011 T043).

Wraps a single :class:`NewznabClient` and probes its ``caps()``
endpoint — the same call the search round uses, so a passing
health check guarantees the next search would also reach the
indexer. Per FR-018: one component instance per configured
indexer; the engine builds the list during lifespan startup
based on the ``indexer`` table.

The ``client_factory`` is injected so the lifespan wiring can
hand in the production ``IndexerRegistry._build_client``-backed
factory while tests pass a stub.
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
    from romarr.indexers.client import NewznabClient


ClientFactory = Callable[[], Awaitable["NewznabClient"]]


@dataclass
class IndexerHealthCheck:
    """One probe per configured indexer.

    The component_id is namespaced as ``indexer.<id>`` so the
    operator UI can show "Prowlarr indexer 3 unreachable"
    without aggregating across the indexer layer.
    """

    indexer_id: int
    client_factory: ClientFactory
    component_id: str = "indexer.unknown"
    category: ComponentCategory = ComponentCategory.INDEXER

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
                await client.caps()
            except Exception as exc:
                return HealthCheckResult(
                    component=self.component_id,
                    category=self.category,
                    status=HealthStatus.WARNING,
                    message=(
                        f"caps probe failed: "
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
            message="caps reachable",
        )


__all__ = ["ClientFactory", "IndexerHealthCheck"]
