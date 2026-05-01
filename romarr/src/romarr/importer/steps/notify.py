"""Notify step (FR-031 / FR-032 / pipeline step 13).

After a successful import, the orchestrator emits one or two
events on the in-process pub/sub channel:

  * ``OnImport`` (FR-031) — fires for every successful import,
    including coalesced no-ops.
  * ``OnUpgrade`` (FR-032) — fires **in addition to** ``OnImport``
    when the new Dump replaced an existing one for the same
    Release. The consumer can render this as a distinct
    notification ("you upgraded Sonic to a verified release")
    while the search engine's ``cutoff_met`` re-evaluation kicks
    off.

The channel implementation is a tiny in-process
:class:`ImporterEventBus`. The consumer wiring (notification
fan-out to Apprise / WebSocket / library exporters) lives with
spec 011's notification subsystem. We ship the producer here so
the importer's tests can verify the events get out the door.

Failure events (``OnFail``, ``OnHealthIssue``) live in the
HARDENING slice when the orchestrator end-to-end lands and can
emit them on every step's failure path.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path
    from uuid import UUID


type _EventCallback = Callable[[Any], Awaitable[None]]


@dataclass(frozen=True)
class OnImportEvent:
    """Payload of the ``OnImport`` event. Carries everything a
    notification consumer needs to render the message without
    touching the DB."""

    correlation_id: UUID
    library_id: int | None
    game_id: int
    release_id: int
    dump_id: int
    dump_path: Path
    imported_via: str
    coalesced: bool = False
    warning: str | None = None


@dataclass(frozen=True)
class OnUpgradeEvent:
    """Payload of the ``OnUpgrade`` event. Fires alongside
    ``OnImport`` when the new Dump replaced an existing one for
    the same Release."""

    correlation_id: UUID
    library_id: int | None
    game_id: int
    release_id: int
    old_dump_id: int
    new_dump_id: int
    dump_path: Path


class ImporterEventBus:
    """In-process publish/subscribe channel for importer events.

    Subscribers register an async callback per event name; the
    bus dispatches every published payload to every matching
    subscriber sequentially. Subscriber failures are surfaced
    immediately rather than swallowed — the consumer is
    responsible for its own error handling.

    The bus is intentionally simple: no buffering, no threading,
    no priority. Spec 011 builds the durable notification
    subsystem on top of this primitive.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[_EventCallback]] = defaultdict(list)

    def subscribe(
        self,
        event_name: str,
        callback: _EventCallback,
    ) -> None:
        """Register ``callback`` as a subscriber to ``event_name``."""
        self._subscribers[event_name].append(callback)

    async def emit(self, event_name: str, payload: Any) -> None:
        """Publish ``payload`` to every subscriber of
        ``event_name``. Awaits each callback in turn so subscribe
        order is honoured."""
        for callback in self._subscribers.get(event_name, ()):
            await callback(payload)


async def emit_import_events(
    *,
    bus: ImporterEventBus,
    correlation_id: UUID,
    library_id: int | None,
    game_id: int,
    release_id: int,
    dump_id: int,
    dump_path: Path,
    imported_via: str,
    coalesced: bool = False,
    warning: str | None = None,
    upgraded_from_dump_id: int | None = None,
) -> None:
    """Emit ``OnImport`` (always) and, when
    ``upgraded_from_dump_id`` is set, ``OnUpgrade`` (FR-032).

    The orchestrator passes ``upgraded_from_dump_id`` when the
    DBUPDATE step retired a prior Dump for the Release; the
    notification consumer can then render an "upgrade"-flavoured
    message.
    """
    on_import = OnImportEvent(
        correlation_id=correlation_id,
        library_id=library_id,
        game_id=game_id,
        release_id=release_id,
        dump_id=dump_id,
        dump_path=dump_path,
        imported_via=imported_via,
        coalesced=coalesced,
        warning=warning,
    )
    await bus.emit("OnImport", on_import)

    if upgraded_from_dump_id is not None:
        on_upgrade = OnUpgradeEvent(
            correlation_id=correlation_id,
            library_id=library_id,
            game_id=game_id,
            release_id=release_id,
            old_dump_id=upgraded_from_dump_id,
            new_dump_id=dump_id,
            dump_path=dump_path,
        )
        await bus.emit("OnUpgrade", on_upgrade)


__all__ = [
    "ImporterEventBus",
    "OnImportEvent",
    "OnUpgradeEvent",
    "emit_import_events",
]
