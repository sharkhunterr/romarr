"""PackSourcesSyncRunner — periodic auto-sync of every enabled pack source.

Delegates each source through the same code path as the manual
`POST /api/v3/rom/platform-pack-source/{id}/sync` endpoint: fetch
YAMLs, iterate, hand each body to `ingest_pack`. Per-source
failures are caught + stamped on the row's `last_status`/`last_error`
so one dead mirror doesn't kill the sweep.

The runner does NOT emit `OnDatUpdate` or any bespoke event yet —
health / notification wiring lands with the same follow-up that
adds per-source scheduling (today the runner sweeps ALL enabled
sources on one cadence, driven by the seeded ``PackSourcesSync``
job).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from romarr.platform_packs import (
    IngestSource,
    PackValidationError,
    PackVersionConflictError,
    ingest_pack,
)
from romarr.platform_packs.builtin import apply_builtin_pack
from romarr.platform_packs.config import get_or_create_platform_pack_config
from romarr.platform_packs.models import PackSource
from romarr.platform_packs.remote import (
    RemotePackError,
    fetch_from_source,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

_logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SourceOutcome:
    """Per-source result of one sweep."""

    source_id: int
    name: str
    status: str  # "ok" | "partial" | "error"
    applied: int
    total_yamls: int
    error: str | None = None


@dataclass
class PackSourcesSyncResult:
    total_sources: int = 0
    total_applied: int = 0
    outcomes: list[SourceOutcome] = field(default_factory=list)


async def run_pack_sources_sync(
    session: "AsyncSession",
    *,
    sessionmaker: "async_sessionmaker[AsyncSession]",
    applied_by: str = "scheduler",
) -> PackSourcesSyncResult:
    """Sweep every enabled ``PackSource`` row and sync it in place.

    The passed ``session`` is used to load and update the
    ``pack_sources`` rows (status stamps). Each individual ingest
    runs in its own session from ``sessionmaker`` so a failure in
    one source or one YAML doesn't rollback the previous
    successes.
    """
    rows = (
        (
            await session.execute(
                select(PackSource).where(PackSource.enabled.is_(True))
            )
        )
        .scalars()
        .all()
    )

    result = PackSourcesSyncResult(total_sources=len(rows))
    src = IngestSource(pack_source="community", applied_by=applied_by)

    for row in rows:
        fetched_at = datetime.now(UTC)
        try:
            yamls = await fetch_from_source(row.url, row.kind)
        except RemotePackError as e:
            row.last_synced_at = fetched_at
            row.last_status = "error"
            row.last_error = str(e)[:1024]
            row.last_applied_count = 0
            result.outcomes.append(
                SourceOutcome(
                    source_id=row.id,
                    name=row.name,
                    status="error",
                    applied=0,
                    total_yamls=0,
                    error=str(e)[:512],
                )
            )
            continue

        applied = 0
        errors: list[str] = []
        for yaml_body in yamls:
            try:
                async with sessionmaker() as ingest_session:
                    ires = await ingest_pack(
                        ingest_session,
                        sessionmaker=sessionmaker,
                        content=yaml_body.body,
                        source=src,
                    )
                    await ingest_session.commit()
                if ires.action in ("applied", "reapplied"):
                    applied += 1
            except (
                PackValidationError,
                PackVersionConflictError,
            ) as e:
                errors.append(f"{yaml_body.filename}: {e}"[:256])
            except Exception as e:  # noqa: BLE001
                errors.append(
                    f"{yaml_body.filename}: {type(e).__name__} {str(e)[:200]}"
                )

        if applied == 0 and errors:
            status_s = "error"
        elif errors:
            status_s = "partial"
        else:
            status_s = "ok"

        row.last_synced_at = fetched_at
        row.last_status = status_s
        row.last_error = "; ".join(errors)[:1024] if errors else None
        row.last_applied_count = applied

        result.total_applied += applied
        result.outcomes.append(
            SourceOutcome(
                source_id=row.id,
                name=row.name,
                status=status_s,
                applied=applied,
                total_yamls=len(yamls),
                error="; ".join(errors)[:512] if errors else None,
            )
        )

    await session.commit()

    # Priority post-step: if config says builtin wins, re-apply the
    # builtin pack over any slugs the community sync just touched.
    # No-op when builtin is disabled or priority=community.
    if result.total_applied > 0:
        try:
            cfg = await get_or_create_platform_pack_config(session)
            await session.commit()
            if cfg.builtin_enabled and cfg.priority == "builtin":
                async with sessionmaker() as reapply_session:
                    reapplied = await apply_builtin_pack(
                        reapply_session, sessionmaker=sessionmaker
                    )
                    await reapply_session.commit()
                _logger.info(
                    "tasks.pack_sources_sync.builtin_priority_reapply",
                    extra={"applied": reapplied is not None},
                )
        except Exception:  # noqa: BLE001
            _logger.exception(
                "tasks.pack_sources_sync.builtin_priority_reapply_failed"
            )

    _logger.info(
        "tasks.pack_sources_sync.complete",
        extra={
            "sources": result.total_sources,
            "applied_packs": result.total_applied,
        },
    )
    return result


__all__ = [
    "PackSourcesSyncResult",
    "SourceOutcome",
    "run_pack_sources_sync",
]
