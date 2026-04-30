"""LaunchBox XML renderer + atomic-write tests (T064, T065)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from lxml import etree

from romarr.libraries.exporters.launchbox import (
    LaunchBoxGame,
    render_launchbox_xml,
    write_launchbox_atomic,
)


def _parse(body: bytes) -> etree._Element:
    return etree.fromstring(body)


# ---------------------------------------------------------------------------
# Renderer happy path
# ---------------------------------------------------------------------------


def test_emits_per_platform_well_formed_xml() -> None:
    games = [
        LaunchBoxGame(
            title="Sonic the Hedgehog",
            platform_name="Sega Genesis",
            application_path="./Sonic the Hedgehog (USA).md",
            notes="Blast processing.",
            developer="Sonic Team",
            publisher="Sega",
            release_date=datetime(1991, 6, 23, tzinfo=UTC),
            genres=("Platformer",),
            play_mode="Single Player",
            rating=0.85,
        ),
    ]
    root = _parse(render_launchbox_xml(games))
    assert root.tag == "LaunchBox"
    game_el = root.find("Game")
    assert game_el is not None
    assert game_el.findtext("Title") == "Sonic the Hedgehog"
    assert game_el.findtext("Platform") == "Sega Genesis"
    assert game_el.findtext("ApplicationPath") == "./Sonic the Hedgehog (USA).md"
    assert game_el.findtext("Notes") == "Blast processing."
    assert game_el.findtext("Developer") == "Sonic Team"
    assert game_el.findtext("Publisher") == "Sega"
    assert game_el.findtext("Genre") == "Platformer"
    assert game_el.findtext("PlayMode") == "Single Player"
    assert game_el.findtext("ReleaseDate") == "1991-06-23T00:00:00"
    # 0.85 → 0..5 scale → 4.25
    assert game_el.findtext("CommunityStarRating") == "4.25"


def test_minimal_game_omits_optional_elements() -> None:
    games = [
        LaunchBoxGame(
            title="Bare",
            platform_name="Mega Drive",
            application_path="./bare.md",
        ),
    ]
    game_el = _parse(render_launchbox_xml(games)).find("Game")
    assert game_el is not None
    assert game_el.find("Notes") is None
    assert game_el.find("Developer") is None
    assert game_el.find("Genre") is None
    assert game_el.find("ReleaseDate") is None
    assert game_el.find("CommunityStarRating") is None


# ---------------------------------------------------------------------------
# T064 — per-platform default mode (path layout test)
# ---------------------------------------------------------------------------


def test_per_platform_default_writes_to_platform_subdir(tmp_path: Path) -> None:
    """When ``exporter_launchbox_per_platform=True``, the orchestrator
    targets ``<library>/<platform_slug>/`` and the writer drops
    ``launchbox-export.xml`` there."""
    target_dir = tmp_path / "library" / "megadrive"

    games = [
        LaunchBoxGame(
            title="Sonic",
            platform_name="Mega Drive",
            application_path="./sonic.md",
        ),
    ]
    assert write_launchbox_atomic(target_dir, render_launchbox_xml(games)) is True

    target = target_dir / "launchbox-export.xml"
    assert target.exists()
    body = target.read_bytes()
    assert b"<LaunchBox>" in body
    assert b"<Title>Sonic</Title>" in body
    # Per-output advisory lock got its own filename so it can co-exist
    # with ES-DE / Pegasus locks under the same directory.
    assert (target_dir / ".launchbox-export.xml.lock").exists()


# ---------------------------------------------------------------------------
# T065 — global mode (per_platform=False)
# ---------------------------------------------------------------------------


def test_global_when_per_platform_disabled(tmp_path: Path) -> None:
    """When ``exporter_launchbox_per_platform=False``, the orchestrator
    targets ``<library>/`` directly. The writer doesn't care about
    the mode — it just writes to whatever ``target_dir`` it gets."""
    library_root = tmp_path / "library"

    games = [
        LaunchBoxGame(
            title="Sonic",
            platform_name="Mega Drive",
            application_path="./megadrive/sonic.md",
        ),
        LaunchBoxGame(
            title="Final Fantasy VII",
            platform_name="Sony PlayStation",
            application_path="./psx/ff7.bin",
        ),
    ]
    assert write_launchbox_atomic(library_root, render_launchbox_xml(games)) is True

    target = library_root / "launchbox-export.xml"
    assert target.exists()
    root = _parse(target.read_bytes())
    titles = [g.findtext("Title") for g in root.findall("Game")]
    platforms = [g.findtext("Platform") for g in root.findall("Game")]
    assert titles == ["Sonic", "Final Fantasy VII"]
    assert platforms == ["Mega Drive", "Sony PlayStation"]


# ---------------------------------------------------------------------------
# Atomic rewrite via shared helper
# ---------------------------------------------------------------------------


def test_atomic_rewrite_preserves_prior_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_launchbox_atomic(tmp_path, render_launchbox_xml([]))
    target = tmp_path / "launchbox-export.xml"
    prior = target.read_bytes()

    def fail_replace(_src: object, _dst: object) -> None:
        raise OSError("simulated rename failure")

    monkeypatch.setattr(
        "romarr.libraries.exporters._atomic.os.replace", fail_replace
    )
    with pytest.raises(OSError):
        write_launchbox_atomic(
            tmp_path,
            render_launchbox_xml(
                [
                    LaunchBoxGame(
                        title="Sonic",
                        platform_name="Mega Drive",
                        application_path="./sonic.md",
                    )
                ]
            ),
        )

    assert target.read_bytes() == prior
    assert not (tmp_path / "launchbox-export.xml.tmp").exists()
