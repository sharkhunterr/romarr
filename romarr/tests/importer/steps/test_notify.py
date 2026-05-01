"""Notify step tests (T078, T079, FR-031 / FR-032)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from romarr.importer.steps.notify import (
    ImporterEventBus,
    OnImportEvent,
    OnUpgradeEvent,
    emit_import_events,
)


@pytest.fixture
def bus() -> ImporterEventBus:
    return ImporterEventBus()


# ---------------------------------------------------------------------------
# T078 — OnImport always fires on success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_import_emitted_on_success(bus: ImporterEventBus) -> None:
    captured: list[OnImportEvent] = []

    async def handler(event: Any) -> None:
        captured.append(event)

    bus.subscribe("OnImport", handler)

    await emit_import_events(
        bus=bus,
        correlation_id=uuid4(),
        library_id=42,
        game_id=1,
        release_id=100,
        dump_id=500,
        dump_path=Path("/library/megadrive/Sonic.md"),
        imported_via="manual",
    )

    assert len(captured) == 1
    event = captured[0]
    assert isinstance(event, OnImportEvent)
    assert event.game_id == 1
    assert event.release_id == 100
    assert event.dump_id == 500
    assert event.dump_path == Path("/library/megadrive/Sonic.md")
    assert event.imported_via == "manual"
    assert event.coalesced is False
    assert event.warning is None


@pytest.mark.asyncio
async def test_on_import_carries_coalesced_and_warning(
    bus: ImporterEventBus,
) -> None:
    """Coalesced imports + warnings flow through the payload so
    the consumer can render "5 callers, 1 imported, 4 coalesced"
    style notifications."""
    captured: list[OnImportEvent] = []
    bus.subscribe("OnImport", lambda e: _append(captured, e))

    await emit_import_events(
        bus=bus,
        correlation_id=uuid4(),
        library_id=42,
        game_id=1,
        release_id=100,
        dump_id=500,
        dump_path=Path("/library/megadrive/Sonic.md"),
        imported_via="webhook",
        coalesced=True,
        warning="dat_unverified",
    )

    assert captured[0].coalesced is True
    assert captured[0].warning == "dat_unverified"


# ---------------------------------------------------------------------------
# T079 — OnUpgrade fires alongside OnImport on Dump replacement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_upgrade_emitted_in_addition_to_on_import(
    bus: ImporterEventBus,
) -> None:
    on_imports: list[OnImportEvent] = []
    on_upgrades: list[OnUpgradeEvent] = []
    bus.subscribe("OnImport", lambda e: _append(on_imports, e))
    bus.subscribe("OnUpgrade", lambda e: _append(on_upgrades, e))

    await emit_import_events(
        bus=bus,
        correlation_id=uuid4(),
        library_id=42,
        game_id=1,
        release_id=100,
        dump_id=600,  # the new Dump
        dump_path=Path("/library/megadrive/Sonic.md"),
        imported_via="automatic",
        upgraded_from_dump_id=500,  # the retired Dump
    )

    assert len(on_imports) == 1
    assert len(on_upgrades) == 1
    upgrade = on_upgrades[0]
    assert isinstance(upgrade, OnUpgradeEvent)
    assert upgrade.old_dump_id == 500
    assert upgrade.new_dump_id == 600


@pytest.mark.asyncio
async def test_on_upgrade_not_emitted_when_no_prior_dump(
    bus: ImporterEventBus,
) -> None:
    """First-time imports (no retired Dump) emit ``OnImport`` only."""
    on_imports: list[OnImportEvent] = []
    on_upgrades: list[OnUpgradeEvent] = []
    bus.subscribe("OnImport", lambda e: _append(on_imports, e))
    bus.subscribe("OnUpgrade", lambda e: _append(on_upgrades, e))

    await emit_import_events(
        bus=bus,
        correlation_id=uuid4(),
        library_id=42,
        game_id=1,
        release_id=100,
        dump_id=500,
        dump_path=Path("/library/megadrive/Sonic.md"),
        imported_via="automatic",
    )

    assert len(on_imports) == 1
    assert on_upgrades == []


# ---------------------------------------------------------------------------
# Bus mechanics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multiple_subscribers_each_receive_event(
    bus: ImporterEventBus,
) -> None:
    received_a: list[OnImportEvent] = []
    received_b: list[OnImportEvent] = []
    bus.subscribe("OnImport", lambda e: _append(received_a, e))
    bus.subscribe("OnImport", lambda e: _append(received_b, e))

    await emit_import_events(
        bus=bus,
        correlation_id=uuid4(),
        library_id=None,
        game_id=1,
        release_id=100,
        dump_id=500,
        dump_path=Path("/x"),
        imported_via="manual",
    )

    assert len(received_a) == 1
    assert len(received_b) == 1


@pytest.mark.asyncio
async def test_no_subscribers_silently_no_op(bus: ImporterEventBus) -> None:
    """Emitting an event with zero subscribers must not raise —
    the importer's notify step always fires regardless of who's
    listening."""
    await emit_import_events(
        bus=bus,
        correlation_id=uuid4(),
        library_id=None,
        game_id=1,
        release_id=100,
        dump_id=500,
        dump_path=Path("/x"),
        imported_via="rss",
    )


@pytest.mark.asyncio
async def test_subscriber_failure_propagates(
    bus: ImporterEventBus,
) -> None:
    """A failing subscriber surfaces immediately; the bus does
    not swallow exceptions. The consumer is responsible for its
    own error handling — we don't want silent failures hiding
    real notification bugs."""

    class _FailingSubscriberError(RuntimeError):
        pass

    async def failing(_event: Any) -> None:
        raise _FailingSubscriberError("kaboom")

    bus.subscribe("OnImport", failing)

    with pytest.raises(_FailingSubscriberError):
        await emit_import_events(
            bus=bus,
            correlation_id=uuid4(),
            library_id=None,
            game_id=1,
            release_id=100,
            dump_id=500,
            dump_path=Path("/x"),
            imported_via="api",
        )


# ---------------------------------------------------------------------------
# Helper


async def _append(target: list[Any], event: Any) -> None:
    target.append(event)
