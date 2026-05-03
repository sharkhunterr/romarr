"""DatUpdateRunner (spec 012 T051).

Refresh DAT packs from configured remote sources. For each
configured ``DatSourceSpec`` the runner downloads the file via
httpx and hands the bytes to spec 001's
:meth:`DatManager.ingest`. Per-source failures are caught +
counted so a single dead mirror doesn't kill the whole sweep.

Source configuration is passed in by the caller — there's no
DB table for "DAT source URLs" yet. The adapter that fronts
this runner can pull the list from settings, a future
``DatSourceConfig`` table, or a Platform Pack manifest. The
runner itself stays a thin orchestrator so wiring stays
flexible.

Event emission (``OnDatUpdate``) is left to the caller — the
notifications fan-out helper hasn't been surfaced as a single
entry point yet (slice 173 noted the same for the bootstrap
hooks). Callers that want to fire the event today can do so
based on the per-source counts in the returned result.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Awaitable, Callable

import httpx

from romarr.identification.dat.manager import DatManager

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlalchemy.ext.asyncio import AsyncSession

_logger = logging.getLogger(__name__)

# Cap one pack at ~64 MiB — DATs are XML, even a maximalist
# No-Intro pack sits well under this. Catches a misconfigured
# URL pointing at a tarball before we hold gigabytes in memory.
_MAX_DAT_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class DatSourceSpec:
    """One ``(url, source, platform_id)`` triple to refresh."""

    url: str
    source: str
    platform_id: int


@dataclass(frozen=True, slots=True)
class DatUpdateOutcome:
    """Per-source result of one fetch+ingest pass."""

    spec: DatSourceSpec
    inserted: int
    skipped_idempotent: bool
    error: str | None = None


@dataclass
class DatUpdateResult:
    """Aggregate result of one ``run_dat_update`` invocation."""

    total: int = 0
    succeeded: int = 0
    failed: int = 0
    outcomes: list[DatUpdateOutcome] = field(default_factory=list)


HttpFetcher = Callable[[str], Awaitable[bytes]]


async def _default_fetcher(url: str) -> bytes:
    """Download ``url`` with a strict size cap."""
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(30.0, connect=10.0),
        follow_redirects=True,
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        body = response.content
        if len(body) > _MAX_DAT_BYTES:
            raise ValueError(
                f"DAT body {len(body)} bytes exceeds cap "
                f"{_MAX_DAT_BYTES} bytes ({url!r})"
            )
        return body


async def run_dat_update(
    session: "AsyncSession",
    *,
    sources: "Iterable[DatSourceSpec]",
    fetcher: HttpFetcher | None = None,
) -> DatUpdateResult:
    """Download + ingest every entry in ``sources``.

    ``fetcher`` is dependency-injected so tests can short-circuit
    the network. The default uses ``httpx.AsyncClient`` with a
    30-second total timeout and a 64 MiB body cap.

    Per-source errors are caught — the sweep keeps going so one
    dead mirror doesn't block the rest. The exception class +
    message are captured in the corresponding
    :class:`DatUpdateOutcome` so the audit trail is complete.
    """
    fetch = fetcher or _default_fetcher
    manager = DatManager(session)
    result = DatUpdateResult()

    for spec in sources:
        result.total += 1
        try:
            payload = await fetch(spec.url)
            stats = await manager.ingest(
                platform_id=spec.platform_id,
                source=spec.source,
                dat_bytes=payload,
            )
        except Exception as exc:
            _logger.warning(
                "tasks.dat_update.source_failed",
                extra={
                    "url": spec.url,
                    "source": spec.source,
                    "platform_id": spec.platform_id,
                    "error": f"{exc.__class__.__name__}: {exc}",
                },
            )
            result.failed += 1
            result.outcomes.append(
                DatUpdateOutcome(
                    spec=spec,
                    inserted=0,
                    skipped_idempotent=False,
                    error=f"{exc.__class__.__name__}: {exc}",
                )
            )
            continue

        result.succeeded += 1
        result.outcomes.append(
            DatUpdateOutcome(
                spec=spec,
                inserted=stats.inserted,
                skipped_idempotent=stats.skipped_idempotent,
            )
        )

    _logger.info(
        "tasks.dat_update.complete",
        extra={
            "total": result.total,
            "succeeded": result.succeeded,
            "failed": result.failed,
        },
    )
    return result


__all__ = [
    "DatSourceSpec",
    "DatUpdateOutcome",
    "DatUpdateResult",
    "HttpFetcher",
    "run_dat_update",
]
