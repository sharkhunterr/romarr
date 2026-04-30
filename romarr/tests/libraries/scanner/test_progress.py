"""ScanProgressEmitter tests (T039 / FR-012)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from romarr.libraries.scanner.progress import (
    ScanProgressEmitter,
    ScanProgressEvent,
)


def _at(seconds: int) -> datetime:
    return datetime(2026, 4, 30, tzinfo=UTC) + timedelta(seconds=seconds)


def _make_emitter(*, every: int = 100) -> tuple[ScanProgressEmitter, list[ScanProgressEvent]]:
    events: list[ScanProgressEvent] = []
    emitter = ScanProgressEmitter(
        library_id=42,
        scan_kind="full",
        started_at=_at(0),
        sink=events.append,
        every=every,
    )
    return emitter, events


# ---------------------------------------------------------------------------
# T039 — emits every 100 files (250 files ⇒ 3 mid-scan events + 1 final)
# ---------------------------------------------------------------------------


def test_emits_every_100_files() -> None:
    emitter, events = _make_emitter(every=100)
    for i in range(250):
        emitter.record_processed(now=_at(i))
    emitter.finish(now=_at(250), note="done")

    # 100, 200 emit during processing → 2 events; 250 finish → 1 final.
    assert len(events) == 3
    assert events[0].files_seen == 100
    assert events[1].files_seen == 200
    assert events[2].files_seen == 250
    assert events[2].note == "done"


def test_no_event_below_threshold() -> None:
    emitter, events = _make_emitter(every=100)
    for i in range(50):
        emitter.record_processed(now=_at(i))
    assert events == []
    # Finish always emits.
    emitter.finish(now=_at(50))
    assert len(events) == 1


def test_orphan_force_emits() -> None:
    emitter, events = _make_emitter(every=100)
    emitter.record_orphan(now=_at(1))
    # Orphan events skip the modulo check — the operator wants the
    # orphan signal as soon as it surfaces.
    assert len(events) == 1
    assert events[0].files_orphaned == 1
    # files_seen is NOT incremented by orphan-recording.
    assert events[0].files_seen == 0


def test_finish_returns_terminal_snapshot() -> None:
    emitter, events = _make_emitter(every=100)
    emitter.record_processed(now=_at(1))
    emitter.record_skipped(now=_at(2))
    snapshot = emitter.finish(now=_at(3), note="done")
    assert snapshot.files_seen == 2
    assert snapshot.files_processed == 1
    assert snapshot.files_skipped == 1
    assert snapshot.note == "done"
    assert events == [snapshot]


def test_no_sink_silently_no_op() -> None:
    """An emitter built without a sink is still usable — it just
    tracks counters internally for the orchestrator's use."""
    emitter = ScanProgressEmitter(
        library_id=1,
        scan_kind="full",
        started_at=_at(0),
        sink=None,
        every=10,
    )
    for _ in range(25):
        emitter.record_processed(now=_at(0))
    emitter.finish(now=_at(0))
    assert emitter.files_seen == 25
