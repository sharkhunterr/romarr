"""Per-library path-availability heartbeat (spec 009 — Phase 4 HEART).

Per FR-028 the system runs a per-library heartbeat that stats
``library.path`` and transitions ``library.status`` between
``'ok'`` and ``'unavailable'``. Per FR-029 transitions emit a
:class:`HeartbeatEvent` (``OnHealthIssue`` on the failure
direction, recovery on the inverse), with a 5-minute debounce per
``(library_id, status)`` so a flapping mountpoint doesn't
generate an event storm.

The probe is **pure**: it owns a single library's last-known
status and the shared debouncer, and accepts an injected ``now``
so tests don't need freezegun. The loop driver
(:func:`run_heartbeat_pass`) is also pure: it returns the list of
events the caller persists / forwards on a notification bus, and
mutates only the bookkeeping dicts the caller passes in.

The lifespan-integrated async loop that wires this into the
FastAPI app, persists ``library.status``, and forwards events on
the notification bus lands once the notification subsystem (spec
011) provides the bus.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from romarr.libraries._debounce import WindowedDebouncer
from romarr.libraries.types import LibraryStatus

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime
    from pathlib import Path

    from romarr.libraries.types import LibrarySnapshot


_DEFAULT_DEBOUNCE = timedelta(minutes=5)
"""FR-029: ``Repeated transitions MUST NOT emit duplicate events
within a 5-minute window``. Per-status, not per-library — a
flap-down at t=0, flap-up at t=10s, flap-down at t=20s emits one
``unavailable`` event (the first) and one ``ok`` event (the t=10s
recovery)."""


# ---------------------------------------------------------------------------
# Event type


@dataclass(frozen=True)
class HeartbeatEvent:
    """Result of one transition the heartbeat loop wants to surface
    on the notification bus.

    ``error`` is populated when the probe could not stat the path
    (the operator notification renders this in the email/webhook).
    Recovery events leave it ``None``.
    """

    library_id: int
    status: LibraryStatus
    observed_at: datetime
    is_recovery: bool
    error: str | None = None


# ---------------------------------------------------------------------------
# Single-library probe


def _stat_status(path: Path) -> tuple[LibraryStatus, str | None]:
    """Pure-ish wrapper around :meth:`Path.is_dir` — returns OK only
    when the path exists AND is a directory. Returns the inferred
    status plus a short operator-facing error string when
    unavailable, ``None`` on OK."""
    try:
        if path.is_dir():
            return LibraryStatus.OK, None
    except OSError as exc:
        return LibraryStatus.UNAVAILABLE, f"{exc.__class__.__name__}: {exc}"
    if not path.exists():
        return LibraryStatus.UNAVAILABLE, "path does not exist"
    return LibraryStatus.UNAVAILABLE, "path is not a directory"


@dataclass
class HeartbeatProbe:
    """Single-library state machine.

    ``initial_status`` is read from the library row's ``status``
    column when the loop boots. It anchors the transition logic so
    the very first observation only fires an event when the
    observed status differs from the persisted one.

    The debouncer is shared across every probe in the loop so the
    5-minute window is enforced per-``(library_id, status)`` rather
    than per-process.
    """

    library_id: int
    debouncer: WindowedDebouncer[tuple[int, LibraryStatus]]
    initial_status: LibraryStatus = LibraryStatus.OK
    _last_status: LibraryStatus | None = None

    def __post_init__(self) -> None:
        self._last_status = self.initial_status

    def observe(self, *, path: Path, now: datetime) -> HeartbeatEvent | None:
        """Stat ``path``; on a status transition that survives the
        5-minute debounce, return the :class:`HeartbeatEvent` the
        loop should forward on the notification bus.

        Returns ``None`` when:
          * the observed status equals the last-seen status (no
            transition); or
          * the debounce window suppresses the emission.

        ``self._last_status`` is updated regardless so we don't
        keep re-emitting on a single sustained outage.
        """
        new_status, error = _stat_status(path)
        if new_status == self._last_status:
            return None

        prior = self._last_status
        self._last_status = new_status

        if not self.debouncer.should_emit(
            key=(self.library_id, new_status), now=now
        ):
            return None

        return HeartbeatEvent(
            library_id=self.library_id,
            status=new_status,
            observed_at=now,
            is_recovery=(
                prior == LibraryStatus.UNAVAILABLE
                and new_status == LibraryStatus.OK
            ),
            error=error,
        )


# ---------------------------------------------------------------------------
# Loop driver


def run_heartbeat_pass(
    *,
    snapshots: Sequence[LibrarySnapshot],
    probes: dict[int, HeartbeatProbe],
    last_run: dict[int, datetime],
    cadence: dict[int, int],
    now: datetime,
    debouncer: WindowedDebouncer[tuple[int, LibraryStatus]] | None = None,
) -> list[HeartbeatEvent]:
    """Run one sweep across every library snapshot.

    ``probes`` and ``last_run`` are mutable bookkeeping dicts the
    caller carries between passes; this function inserts new
    probes for previously-unseen libraries and updates the
    last-run timestamp every time it actually fires a probe.

    A library only fires when ``now - last_run[id] >= cadence[id]``
    (or when it has never fired before). Per-library cadence
    matches the value the operator configured on the library row
    (``library.heartbeat_seconds``), defaulting to 30s if absent
    from the cadence map.

    Returns the events emitted on this pass — one per library that
    transitioned and survived the debounce.
    """
    if debouncer is None:
        debouncer = WindowedDebouncer(window=_DEFAULT_DEBOUNCE)

    events: list[HeartbeatEvent] = []
    for snap in snapshots:
        cadence_s = cadence.get(snap.id, 30)
        last = last_run.get(snap.id)
        if last is not None and (now - last).total_seconds() < cadence_s:
            continue

        probe = probes.get(snap.id)
        if probe is None:
            probe = HeartbeatProbe(
                library_id=snap.id,
                debouncer=debouncer,
                initial_status=snap.status,
            )
            probes[snap.id] = probe

        last_run[snap.id] = now
        event = probe.observe(path=snap.path, now=now)
        if event is not None:
            events.append(event)

    return events


__all__ = [
    "HeartbeatEvent",
    "HeartbeatProbe",
    "run_heartbeat_pass",
]
