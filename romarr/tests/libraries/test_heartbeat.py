"""Heartbeat probe + loop tests (T025-T028)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from romarr.libraries._debounce import WindowedDebouncer
from romarr.libraries.heartbeat import (
    HeartbeatProbe,
    run_heartbeat_pass,
)
from romarr.libraries.types import LibrarySnapshot, LibraryStatus


def _at(seconds: int) -> datetime:
    return datetime(2026, 4, 30, tzinfo=UTC) + timedelta(seconds=seconds)


def _snapshot(
    *,
    library_id: int,
    path: Path,
    status: LibraryStatus = LibraryStatus.OK,
) -> LibrarySnapshot:
    return LibrarySnapshot(
        id=library_id,
        name=f"library-{library_id}",
        path=path,
        status=status,
        platforms_restricted=False,
        accepted_platform_ids=frozenset(),
        quality_profile_id=1,
        region_profile_id=1,
        dump_profile_id=1,
        language_profile_id=1,
        naming_profile_id=1,
        use_hardlinks=True,
        lifecycle_policy="hardlink_and_seed",
        keep_dump_history=False,
        min_disk_free_gb=5,
        preserve_archive=False,
    )


def _debouncer() -> WindowedDebouncer[tuple[int, LibraryStatus]]:
    return WindowedDebouncer(window=timedelta(minutes=5))


# ---------------------------------------------------------------------------
# T025 — unavailable emits an event
# ---------------------------------------------------------------------------


def test_unavailable_emits_event_on_first_transition(tmp_path: Path) -> None:
    deb = _debouncer()
    probe = HeartbeatProbe(library_id=1, debouncer=deb)

    # First observation against a missing path: transition OK→UNAVAILABLE.
    missing = tmp_path / "missing"
    event = probe.observe(path=missing, now=_at(0))
    assert event is not None
    assert event.status is LibraryStatus.UNAVAILABLE
    assert event.is_recovery is False
    assert event.error is not None and "exist" in event.error


def test_no_event_when_initial_status_already_unavailable(tmp_path: Path) -> None:
    """If the library row is already ``unavailable`` and the path
    is still missing, the probe doesn't re-emit on the very next
    observation."""
    deb = _debouncer()
    probe = HeartbeatProbe(
        library_id=1, debouncer=deb, initial_status=LibraryStatus.UNAVAILABLE
    )
    event = probe.observe(path=tmp_path / "missing", now=_at(0))
    assert event is None


# ---------------------------------------------------------------------------
# T026 — recovery emits an event
# ---------------------------------------------------------------------------


def test_recovery_emits_event(tmp_path: Path) -> None:
    deb = _debouncer()
    probe = HeartbeatProbe(library_id=1, debouncer=deb)

    missing = tmp_path / "lib"
    # Down.
    down = probe.observe(path=missing, now=_at(0))
    assert down is not None and down.status is LibraryStatus.UNAVAILABLE

    # Restore the path; up.
    missing.mkdir()
    up = probe.observe(path=missing, now=_at(10))
    assert up is not None
    assert up.status is LibraryStatus.OK
    assert up.is_recovery is True
    assert up.error is None


# ---------------------------------------------------------------------------
# T027 — debounce 5-min window
# ---------------------------------------------------------------------------


def test_debounce_suppresses_flapping_events(tmp_path: Path) -> None:
    deb = _debouncer()
    probe = HeartbeatProbe(library_id=1, debouncer=deb)

    p = tmp_path / "lib"
    # t=0:  down (emit)
    e1 = probe.observe(path=p, now=_at(0))
    assert e1 is not None and e1.status is LibraryStatus.UNAVAILABLE
    # t=1:  up (emit; different status, distinct debounce key)
    p.mkdir()
    e2 = probe.observe(path=p, now=_at(1))
    assert e2 is not None and e2.status is LibraryStatus.OK
    # t=2:  down (transition observed, but debounced — already
    #             emitted UNAVAILABLE within the 5-min window)
    p.rmdir()
    e3 = probe.observe(path=p, now=_at(2))
    assert e3 is None
    # t=3:  up (transition observed, debounced)
    p.mkdir()
    e4 = probe.observe(path=p, now=_at(3))
    assert e4 is None
    # t=301: up→down (5-min window elapsed since e1) → emit
    p.rmdir()
    e5 = probe.observe(path=p, now=_at(301))
    assert e5 is not None and e5.status is LibraryStatus.UNAVAILABLE


# ---------------------------------------------------------------------------
# T028 — per-library cadence
# ---------------------------------------------------------------------------


def test_per_library_cadence(tmp_path: Path) -> None:
    """Two libraries with different ``heartbeat_seconds`` fire on
    their own schedule; the loop only probes a library when its
    cadence has elapsed since its last run."""
    p1 = tmp_path / "lib1"
    p2 = tmp_path / "lib2"
    p1.mkdir()
    p2.mkdir()

    snap1 = _snapshot(library_id=1, path=p1)
    snap2 = _snapshot(library_id=2, path=p2)

    probes: dict[int, HeartbeatProbe] = {}
    last_run: dict[int, datetime] = {}
    cadence = {1: 30, 2: 60}  # lib1 every 30s, lib2 every 60s
    deb = _debouncer()

    # First pass at t=0: both fire (no prior run).
    run_heartbeat_pass(
        snapshots=[snap1, snap2],
        probes=probes,
        last_run=last_run,
        cadence=cadence,
        now=_at(0),
        debouncer=deb,
    )
    assert last_run == {1: _at(0), 2: _at(0)}

    # t=31: lib1 due (30s elapsed); lib2 not due (only 31s of 60s).
    run_heartbeat_pass(
        snapshots=[snap1, snap2],
        probes=probes,
        last_run=last_run,
        cadence=cadence,
        now=_at(31),
        debouncer=deb,
    )
    assert last_run == {1: _at(31), 2: _at(0)}

    # t=61: both due (lib1 at 31+30=61, lib2 at 0+60=60).
    run_heartbeat_pass(
        snapshots=[snap1, snap2],
        probes=probes,
        last_run=last_run,
        cadence=cadence,
        now=_at(61),
        debouncer=deb,
    )
    assert last_run == {1: _at(61), 2: _at(61)}


def test_run_heartbeat_pass_emits_events_on_transition(tmp_path: Path) -> None:
    p = tmp_path / "lib"  # missing
    snap = _snapshot(library_id=1, path=p)

    events = run_heartbeat_pass(
        snapshots=[snap],
        probes={},
        last_run={},
        cadence={1: 30},
        now=_at(0),
    )
    assert len(events) == 1
    assert events[0].library_id == 1
    assert events[0].status is LibraryStatus.UNAVAILABLE


def test_run_heartbeat_pass_inherits_initial_status_from_snapshot(
    tmp_path: Path,
) -> None:
    """Probe initial_status is read from the snapshot so the very
    first pass doesn't re-emit on a still-unavailable path."""
    p = tmp_path / "still-missing"
    snap = _snapshot(
        library_id=1, path=p, status=LibraryStatus.UNAVAILABLE
    )
    events = run_heartbeat_pass(
        snapshots=[snap],
        probes={},
        last_run={},
        cadence={1: 30},
        now=_at(0),
    )
    assert events == []


# ---------------------------------------------------------------------------
# Path-stat error path (PermissionError on stat)
# ---------------------------------------------------------------------------


def test_permission_error_on_stat_treated_as_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = tmp_path / "blocked"
    p.mkdir()

    def fake_is_dir(_self: object) -> bool:
        raise PermissionError("revoked")

    monkeypatch.setattr(Path, "is_dir", fake_is_dir)

    deb = _debouncer()
    probe = HeartbeatProbe(library_id=1, debouncer=deb)
    event = probe.observe(path=p, now=_at(0))
    assert event is not None
    assert event.status is LibraryStatus.UNAVAILABLE
    assert event.error is not None and "PermissionError" in event.error
