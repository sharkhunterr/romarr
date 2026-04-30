"""ES-DE gamelist.xml renderer tests (T053, T054, T059)."""

from __future__ import annotations

from datetime import UTC, datetime

from lxml import etree

from romarr.libraries.exporters.esde import EsdeGame, render_gamelist_xml


def _parse(xml_bytes: bytes) -> etree._Element:
    return etree.fromstring(xml_bytes)


# ---------------------------------------------------------------------------
# T053 — well-formed XML
# ---------------------------------------------------------------------------


def test_emits_well_formed_xml() -> None:
    games = [
        EsdeGame(
            slug="sonic",
            title="Sonic the Hedgehog",
            rom_path="./Sonic the Hedgehog (USA).md",
            summary="Blast processing.",
            developer="Sonic Team",
            publisher="Sega",
            genres=("Platformer",),
            rating=0.85,
            release_date=datetime(1991, 6, 23, tzinfo=UTC),
            players_min=1,
            players_max=1,
            cover_relative="./media/covers/sonic.png",
        ),
        EsdeGame(
            slug="streets-of-rage",
            title="Streets of Rage",
            rom_path="./Streets of Rage (USA).md",
            summary="Beat 'em up.",
            genres=("Beat 'em up",),
            players_min=1,
            players_max=2,
        ),
    ]
    xml = render_gamelist_xml(games)
    root = _parse(xml)
    assert root.tag == "gameList"
    assert len(root.findall("game")) == 2

    # First game has every field.
    first = root.findall("game")[0]
    assert first.findtext("name") == "Sonic the Hedgehog"
    assert first.findtext("path") == "./Sonic the Hedgehog (USA).md"
    assert first.findtext("desc") == "Blast processing."
    assert first.findtext("image") == "./media/covers/sonic.png"
    assert first.findtext("developer") == "Sonic Team"
    assert first.findtext("publisher") == "Sega"
    assert first.findtext("genre") == "Platformer"
    assert first.findtext("rating") == "0.85"
    assert first.findtext("releasedate") == "19910623T000000"
    assert first.findtext("players") == "1"

    # Second game has no cover, no rating, no developer — those
    # elements MUST be absent (FR-018a).
    second = root.findall("game")[1]
    assert second.find("image") is None
    assert second.find("rating") is None
    assert second.find("developer") is None
    assert second.findtext("players") == "1-2"


def test_xml_declaration_and_encoding() -> None:
    games = [EsdeGame(slug="s", title="S", rom_path="./s.md")]
    xml = render_gamelist_xml(games)
    assert xml.startswith(b"<?xml")
    assert b'encoding="UTF-8"' in xml or b"encoding='UTF-8'" in xml


# ---------------------------------------------------------------------------
# T054 — relative image path (FR-018)
# ---------------------------------------------------------------------------


def test_relative_image_path_is_emitted_as_given() -> None:
    """The renderer doesn't manipulate the path — it just emits what
    the orchestrator computed via the media-mirror helper."""
    games = [
        EsdeGame(
            slug="sonic",
            title="Sonic",
            rom_path="./sonic.md",
            cover_relative="./media/covers/sonic.png",
        ),
    ]
    xml = render_gamelist_xml(games)
    image_text = _parse(xml).findtext("game/image")
    assert image_text == "./media/covers/sonic.png"


# ---------------------------------------------------------------------------
# FR-018a — image / thumbnail / marquee omitted when missing
# ---------------------------------------------------------------------------


def test_no_cover_omits_image_element() -> None:
    games = [
        EsdeGame(slug="sonic", title="Sonic", rom_path="./sonic.md"),
    ]
    xml = render_gamelist_xml(games)
    game_el = _parse(xml).find("game")
    assert game_el is not None
    assert game_el.find("image") is None
    assert game_el.find("thumbnail") is None
    assert game_el.find("marquee") is None


def test_thumbnail_and_marquee_emitted_when_present() -> None:
    games = [
        EsdeGame(
            slug="sonic",
            title="Sonic",
            rom_path="./sonic.md",
            cover_relative="./media/covers/sonic.png",
            thumbnail_relative="./media/thumbs/sonic.png",
            marquee_relative="./media/marquees/sonic.png",
        ),
    ]
    xml = render_gamelist_xml(games)
    game_el = _parse(xml).find("game")
    assert game_el is not None
    assert game_el.findtext("thumbnail") == "./media/thumbs/sonic.png"
    assert game_el.findtext("marquee") == "./media/marquees/sonic.png"


# ---------------------------------------------------------------------------
# Determinism — same input ⇒ same output
# ---------------------------------------------------------------------------


def test_render_is_deterministic() -> None:
    games = [
        EsdeGame(slug="a", title="A", rom_path="./a.md"),
        EsdeGame(slug="b", title="B", rom_path="./b.md"),
    ]
    assert render_gamelist_xml(games) == render_gamelist_xml(games)
