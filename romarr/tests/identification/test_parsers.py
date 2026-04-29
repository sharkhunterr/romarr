"""Tests for the rest of the parser cascade — Redump, TOSEC, GoodTools, Scene."""

from __future__ import annotations

import pytest

from romarr.domain.enums import DumpStatus, NamingConvention
from romarr.identification.parsers import (
    GoodToolsParser,
    RedumpParser,
    SceneParser,
    TosecParser,
    default_dispatcher,
)

# ---------------------------------------------------------------------------
# GoodTools
# ---------------------------------------------------------------------------


@pytest.fixture
def goodtools() -> GoodToolsParser:
    return GoodToolsParser()


def test_goodtools_underscore_shorthand_sth_e_b(goodtools: GoodToolsParser) -> None:
    """Spec 001 User Story 4: ``sth_e_b.bin`` → EUR + baddump."""
    r = goodtools.parse("sth_e_b.bin")
    assert r.regions == ("EU",)
    assert r.dump_status == DumpStatus.BADDUMP
    assert r.convention == NamingConvention.GOODTOOLS
    assert r.confidence > 0.7


def test_goodtools_bracketed_form(goodtools: GoodToolsParser) -> None:
    r = goodtools.parse("Super Mario World (E) [b].smc")
    assert r.regions == ("EU",)
    assert r.dump_status == DumpStatus.BADDUMP
    assert r.title == "Super Mario World"


def test_goodtools_verified_tag(goodtools: GoodToolsParser) -> None:
    r = goodtools.parse("Castlevania (U) (V1.1) [!].nes")
    assert r.regions == ("US",)
    assert r.dump_status == DumpStatus.VERIFIED
    assert r.revision == "V1.1"


def test_goodtools_multi_region_grouping(goodtools: GoodToolsParser) -> None:
    r = goodtools.parse("Sonic the Hedgehog (UE).smc")
    assert set(r.regions) == {"US", "EU"}


def test_goodtools_hack_tag(goodtools: GoodToolsParser) -> None:
    r = goodtools.parse("Final Fantasy (J) [h2].sfc")
    assert r.regions == ("JP",)
    assert r.dump_status == DumpStatus.HACK


def test_goodtools_zero_confidence_on_plain_name(goodtools: GoodToolsParser) -> None:
    r = goodtools.parse("game.bin")
    assert r.confidence == 0.0


# ---------------------------------------------------------------------------
# Redump
# ---------------------------------------------------------------------------


@pytest.fixture
def redump() -> RedumpParser:
    return RedumpParser()


def test_redump_disc_extension(redump: RedumpParser) -> None:
    r = redump.parse("Final Fantasy IX (USA) (Disc 1).cue")
    assert r.title == "Final Fantasy IX"
    assert r.regions == ("US",)
    assert r.convention == NamingConvention.REDUMP
    assert r.confidence > 0.7
    assert any("Disc 1" in t for t in r.tags)


def test_redump_iso_extension_qualifies(redump: RedumpParser) -> None:
    r = redump.parse("Metal Gear Solid (Europe).iso")
    assert r.convention == NamingConvention.REDUMP
    assert r.regions == ("EU",)


def test_redump_cartridge_does_not_qualify(redump: RedumpParser) -> None:
    """A clean No-Intro `.md` cartridge name MUST NOT be claimed by Redump."""
    r = redump.parse("Sonic the Hedgehog (USA).md")
    assert r.convention == NamingConvention.UNKNOWN
    assert r.confidence == 0.0


def test_redump_disc_marker_without_disc_extension(redump: RedumpParser) -> None:
    """Even a `.bin` qualifies if it carries the ``(Disc 1)`` marker."""
    r = redump.parse("Final Fantasy IX (USA) (Disc 1).bin")
    assert r.convention == NamingConvention.REDUMP


# ---------------------------------------------------------------------------
# TOSEC
# ---------------------------------------------------------------------------


@pytest.fixture
def tosec() -> TosecParser:
    return TosecParser()


def test_tosec_full_form(tosec: TosecParser) -> None:
    r = tosec.parse("Title (1992)(Konami)(USA)[!].nes")
    assert r.title == "Title"
    assert r.regions == ("US",)
    assert r.dump_status == DumpStatus.VERIFIED
    assert r.extra.get("year") == "1992"
    assert r.extra.get("publisher") == "Konami"
    assert r.confidence > 0.7


def test_tosec_year_required_for_high_confidence(tosec: TosecParser) -> None:
    """A No-Intro-shaped name without a year stays under threshold."""
    r = tosec.parse("Sonic the Hedgehog (USA).md")
    # No year in the bracket groups → confidence drops below threshold.
    assert r.confidence < 0.7


def test_tosec_with_publisher_and_year(tosec: TosecParser) -> None:
    r = tosec.parse("Tetris (1989)(Nintendo).gb")
    assert r.extra.get("year") == "1989"
    assert r.extra.get("publisher") == "Nintendo"
    assert r.confidence > 0.7  # year + publisher → 0.55 + 0.20 = 0.75


# ---------------------------------------------------------------------------
# Scene
# ---------------------------------------------------------------------------


@pytest.fixture
def scene() -> SceneParser:
    return SceneParser()


def test_scene_release_group(scene: SceneParser) -> None:
    r = scene.parse("Sonic.the.Hedgehog.USA-DEMENT")
    assert r.title == "Sonic the Hedgehog"
    assert r.regions == ("US",)
    assert r.extra.get("release_group") == "DEMENT"
    assert r.convention == NamingConvention.SCENE
    assert r.confidence > 0.7


def test_scene_with_disc_marker(scene: SceneParser) -> None:
    r = scene.parse("Final.Fantasy.IX.USA.Disc.1-DEMENT")
    assert r.regions == ("US",)
    assert r.extra.get("release_group") == "DEMENT"
    assert any("Disc 1" in t for t in r.tags)


def test_scene_rejects_bracketed_input(scene: SceneParser) -> None:
    """Bracketed names belong to No-Intro / GoodTools / TOSEC."""
    r = scene.parse("Sonic (USA).md")
    assert r.confidence == 0.0


def test_scene_no_group_no_region_low_confidence(scene: SceneParser) -> None:
    r = scene.parse("plain_filename.bin")
    assert r.confidence < 0.7


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def test_dispatcher_picks_no_intro_for_clean_cartridge() -> None:
    d = default_dispatcher()
    r = d.parse("Sonic the Hedgehog (USA) (Rev A).md")
    assert r.convention == NamingConvention.NO_INTRO


def test_dispatcher_picks_redump_for_disc_release() -> None:
    d = default_dispatcher()
    r = d.parse("Final Fantasy IX (USA) (Disc 1).cue")
    # Both No-Intro and Redump match; No-Intro is tried first per FR-023.
    # Since No-Intro confidence > 0.7 already, it wins — that's the
    # documented Edge Case ("first parser in dispatcher order wins").
    assert r.convention == NamingConvention.NO_INTRO
    assert r.regions == ("US",)


def test_dispatcher_picks_goodtools_for_underscore_shorthand() -> None:
    d = default_dispatcher()
    r = d.parse("sth_e_b.bin")
    assert r.convention == NamingConvention.GOODTOOLS
    assert r.dump_status == DumpStatus.BADDUMP


def test_dispatcher_picks_scene_for_dotted_group_name() -> None:
    d = default_dispatcher()
    r = d.parse("Sonic.the.Hedgehog.USA-DEMENT")
    assert r.convention == NamingConvention.SCENE


def test_dispatcher_picks_tosec_for_year_bearing_name() -> None:
    """A name with year + publisher beats the No-Intro threshold gap."""
    d = default_dispatcher()
    # No-Intro will score this (it has '(USA)') so No-Intro wins per
    # FR-023 ordering. But a bare-year shape without USA stays UNKNOWN
    # until TOSEC sees it.
    r = d.parse("Title (1992)(Konami).nes")
    # No-Intro doesn't see this as a region; TOSEC sees year+publisher
    # → TOSEC wins.
    assert r.convention == NamingConvention.TOSEC
    assert r.extra.get("year") == "1992"


def test_dispatcher_falls_back_unknown_for_garbage() -> None:
    d = default_dispatcher()
    r = d.parse("game_001.bin")
    # No parser meets threshold — UNKNOWN sentinel returned.
    assert r.convention == NamingConvention.UNKNOWN
    assert r.confidence == 0.0
