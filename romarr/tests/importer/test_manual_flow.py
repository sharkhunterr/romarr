"""Manual-flow contract tests (spec 008 HARD).

The spec carves the manual flow into two surfaces:

* the manual-match endpoint (``POST /api/v3/rom/unidentified/{id}/match``)
  — covered by ``tests/importer/api/test_unidentified_endpoints.py``
* the retry contract — re-running the orchestrator against a
  source path that previously produced a failure history row
  must produce a NEW row without mutating the original.

T087 pins the retry contract here. The retry-endpoint that
exposes this over HTTP doesn't ship yet (deferred together
with T088); the orchestrator itself is the single source of
truth for the retry semantics, so we exercise the contract
through ``run_import`` directly. The HTTP retry endpoint will
be a thin façade over the same call.

The orchestrator is idempotent on path for the
``unidentified_dump`` row (FR-038 / ``park_in_unidentified``
upserts on path) but NOT on the ``import_history`` row — every
call writes a fresh audit entry by design (FR-035).
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.domain.models import UnidentifiedDump
from romarr.importer.models import ImportHistory
from romarr.importer.orchestrator import run_import
from romarr.importer.types import ImportContext


def _make_rom(tmp_path: Path) -> Path:
    src = tmp_path / "downloads" / "Sonic the Hedgehog (USA).md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"\x00" * 4096)
    return src


@pytest.mark.asyncio
async def test_retry_creates_new_history_row(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """T087 — POST retry on a failed import:

    * a NEW ``import_history`` row is written (per-run audit
      trail per FR-035);
    * the original row is preserved (no UPDATE or DELETE);
    * each run's correlation id is independent;
    * the parked ``unidentified_dump`` row is the SAME row
      (idempotent on path per FR-038), so a retry doesn't
      orphan the operator's triage state.
    """
    rom = _make_rom(tmp_path)

    first_correlation_id = uuid4()
    first_context = ImportContext(
        source_path=rom,
        correlation_id=first_correlation_id,
        imported_via="manual",
    )
    first_outcome = await run_import(first_context, session=async_session)
    assert first_outcome.success is False
    assert first_outcome.history_id > 0

    # Simulate the operator hitting "Retry" on the failed import:
    # a new correlation id, same source path.
    retry_correlation_id = uuid4()
    retry_context = ImportContext(
        source_path=rom,
        correlation_id=retry_correlation_id,
        imported_via="manual",
    )
    retry_outcome = await run_import(retry_context, session=async_session)
    assert retry_outcome.success is False
    assert retry_outcome.history_id > 0
    assert retry_outcome.history_id != first_outcome.history_id

    # Pull every history row referencing this rom path. Two rows
    # must exist; both must still be present (no destructive
    # update on retry).
    rows = (
        await async_session.execute(
            select(ImportHistory)
            .where(ImportHistory.source_path == str(rom))
            .order_by(ImportHistory.id.asc())
        )
    ).scalars().all()
    assert len(rows) == 2

    original, retry = rows
    assert original.id == first_outcome.history_id
    assert retry.id == retry_outcome.history_id

    # Each run carries its own correlation id.
    assert original.correlation_id == str(first_correlation_id)
    assert retry.correlation_id == str(retry_correlation_id)

    # Both rows are failures (still gated on no-game-match in
    # the audit-only orchestrator); the retry contract holds
    # for failure → failure today and will hold for
    # failure → success once the full happy path lands.
    assert original.success is False
    assert retry.success is False

    # Same parked unidentified row across both runs — retry must
    # not orphan the operator's triage state (FR-038).
    parked = (
        await async_session.execute(
            select(UnidentifiedDump).where(
                UnidentifiedDump.path == str(rom),
            )
        )
    ).scalars().all()
    assert len(parked) == 1
