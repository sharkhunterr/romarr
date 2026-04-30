"""Pegasus metadata.txt renderer + atomic-write tests (T061, T062)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from romarr.libraries.exporters.pegasus import (
    PegasusCollection,
    PegasusGame,
    render_metadata_txt,
    write_metadata_atomic,
)


def _collection() -> PegasusCollection:
    return PegasusCollection(
        name="Sega Mega Drive",
        shortname="megadrive",
        extensions=("md", "gen", "smd"),
    )


# ---------------------------------------------------------------------------
# T061 — well-formed text
# ---------------------------------------------------------------------------


def test_emits_well_formed_text() -> None:
    games = [
        PegasusGame(
            title="Sonic the Hedgehog",
            rom_path="./Sonic the Hedgehog (USA).md",
            description="Blast processing.",
            developer="Sonic Team",
            publisher="Sega",
            genres=("Platformer",),
            release_date=datetime(1991, 6, 23, tzinfo=UTC),
            players_min=1,
            players_max=1,
            rating=0.85,
            cover_relative="./media/covers/sonic.png",
        ),
        PegasusGame(
            title="Streets of Rage",
            rom_path="./Streets of Rage (USA).md",
            players_min=1,
            players_max=2,
        ),
    ]
    body = render_metadata_txt(_collection(), games).decode("utf-8")

    # Header block.
    assert body.startswith("collection: Sega Mega Drive\n")
    assert "shortname: megadrive\n" in body
    assert "extensions: md, gen, smd\n" in body

    # First game block.
    assert "game: Sonic the Hedgehog\n" in body
    assert "file: ./Sonic the Hedgehog (USA).md\n" in body
    assert "description: Blast processing.\n" in body
    assert "developer: Sonic Team\n" in body
    assert "publisher: Sega\n" in body
    assert "genre: Platformer\n" in body
    assert "release: 1991-06-23\n" in body
    assert "players: 1\n" in body
    assert "rating: 85%\n" in body
    assert "assets.boxFront: ./media/covers/sonic.png\n" in body

    # Second game: minimal — no description, no rating, no assets.
    assert "game: Streets of Rage\n" in body
    streets_block = body.split("game: Streets of Rage")[1]
    assert "description:" not in streets_block
    assert "rating:" not in streets_block
    assert "assets.boxFront:" not in streets_block
    assert "players: 1-2\n" in streets_block


def test_render_is_deterministic() -> None:
    games = [
        PegasusGame(title="A", rom_path="./a.md"),
        PegasusGame(title="B", rom_path="./b.md"),
    ]
    assert render_metadata_txt(_collection(), games) == render_metadata_txt(
        _collection(), games
    )


# ---------------------------------------------------------------------------
# T062 — atomic rewrite with the shared helper
# ---------------------------------------------------------------------------


def test_atomic_rewrite_preserves_prior_file_on_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    games = [PegasusGame(title="Sonic", rom_path="./sonic.md")]
    assert write_metadata_atomic(tmp_path, render_metadata_txt(_collection(), games)) is True

    target = tmp_path / "metadata.txt"
    prior = target.read_bytes()

    def fail_replace(_src: object, _dst: object) -> None:
        raise OSError("simulated rename failure")

    monkeypatch.setattr(
        "romarr.libraries.exporters._atomic.os.replace", fail_replace
    )
    with pytest.raises(OSError):
        write_metadata_atomic(
            tmp_path,
            render_metadata_txt(
                _collection(),
                [PegasusGame(title="Streets of Rage", rom_path="./sor.md")],
            ),
        )

    assert target.read_bytes() == prior
    assert not (tmp_path / "metadata.txt.tmp").exists()


def test_per_output_lock_uses_metadata_filename(tmp_path: Path) -> None:
    """Pegasus and ES-DE write to the same target_dir but use
    different per-output lock files, so they never block each
    other."""
    write_metadata_atomic(tmp_path, render_metadata_txt(_collection(), []))
    assert (tmp_path / ".metadata.txt.lock").exists()
    # Confirm the gamelist lock isn't aliased.
    assert not (tmp_path / ".gamelist.xml.lock").exists()
