"""Manual-import listing tests (spec 009 T067)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.domain.models import Dump, Game, Platform, Release, UnidentifiedDump
from romarr.libraries.manual_import import list_candidates
from romarr.tasks.models import Job


@pytest.mark.asyncio
async def test_listing_no_db_modification(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """T067 — listing 50 files writes nothing to the database.

    Drops 50 fixture files into a folder; calls
    :func:`list_candidates`; asserts the catalogue tables stay
    untouched (no Game / Release / Dump / UnidentifiedDump /
    JobRun rows created).
    """
    folder = tmp_path / "downloads" / "manual"
    folder.mkdir(parents=True)
    for i in range(50):
        (folder / f"Sonic the Hedgehog {i:02d} (USA).md").write_bytes(
            b"\x00" * 4096
        )

    before = {
        "game": (
            await async_session.execute(select(func.count()).select_from(Game))
        ).scalar_one(),
        "release": (
            await async_session.execute(select(func.count()).select_from(Release))
        ).scalar_one(),
        "dump": (
            await async_session.execute(select(func.count()).select_from(Dump))
        ).scalar_one(),
        "unidentified": (
            await async_session.execute(
                select(func.count()).select_from(UnidentifiedDump)
            )
        ).scalar_one(),
        "job": (
            await async_session.execute(select(func.count()).select_from(Job))
        ).scalar_one(),
    }

    listings = await list_candidates(
        session=async_session,
        folder=folder,
        accepted_extensions={".md"},
    )

    after = {
        "game": (
            await async_session.execute(select(func.count()).select_from(Game))
        ).scalar_one(),
        "release": (
            await async_session.execute(select(func.count()).select_from(Release))
        ).scalar_one(),
        "dump": (
            await async_session.execute(select(func.count()).select_from(Dump))
        ).scalar_one(),
        "unidentified": (
            await async_session.execute(
                select(func.count()).select_from(UnidentifiedDump)
            )
        ).scalar_one(),
        "job": (
            await async_session.execute(select(func.count()).select_from(Job))
        ).scalar_one(),
    }
    assert before == after
    assert len(listings) == 50
    # Spot-check parsed metadata surfaced.
    first = listings[0]
    assert first.parsed_title == "Sonic the Hedgehog 00"
    assert first.parsed_convention == "no-intro"


@pytest.mark.asyncio
async def test_listing_surfaces_suggested_game(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """When the parsed title resolves to exactly one Game in
    DB, the listing carries ``suggested_game_id``."""
    platform = Platform(slug="megadrive-manual", name="Mega Drive")
    async_session.add(platform)
    await async_session.flush()
    game = Game(
        platform_id=platform.id,
        slug="sonic-manual",
        title="Sonic the Hedgehog",
    )
    async_session.add(game)
    await async_session.commit()

    folder = tmp_path / "drop"
    folder.mkdir()
    (folder / "Sonic the Hedgehog (USA).md").write_bytes(b"\x00" * 4096)

    listings = await list_candidates(
        session=async_session,
        folder=folder,
        accepted_extensions={".md"},
    )
    assert len(listings) == 1
    assert listings[0].suggested_game_id == game.id


@pytest.mark.asyncio
async def test_listing_filters_by_extension(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """Files outside the accepted-extension allow-list are
    silently skipped."""
    folder = tmp_path / "mixed"
    folder.mkdir()
    (folder / "rom.md").write_bytes(b"\x00" * 1024)
    (folder / "notes.txt").write_bytes(b"reminder")
    (folder / "thumb.png").write_bytes(b"\x89PNG")

    listings = await list_candidates(
        session=async_session,
        folder=folder,
        accepted_extensions={".md"},
    )
    assert [str(listing.path.name) for listing in listings] == ["rom.md"]


@pytest.mark.asyncio
async def test_listing_missing_folder_returns_empty(
    async_session: AsyncSession, tmp_path: Path
) -> None:
    """A non-existent folder yields an empty list — operators
    can pre-flight-check without crashing."""
    listings = await list_candidates(
        session=async_session,
        folder=tmp_path / "nope",
        accepted_extensions={".md"},
    )
    assert listings == []
