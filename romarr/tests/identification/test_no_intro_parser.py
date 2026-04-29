"""No-Intro filename parser tests — Acceptance Scenarios 4.x."""

from __future__ import annotations

import pytest

from romarr.domain.enums import DumpStatus, NamingConvention
from romarr.identification.parsers import (
    BaseFilenameParser,
    NoIntroParser,
    ParsedFilename,
    ParserDispatcher,
)


@pytest.fixture
def parser() -> NoIntroParser:
    return NoIntroParser()


def test_clean_usa_release(parser: NoIntroParser) -> None:
    r = parser.parse("Sonic the Hedgehog (USA).md")
    assert r.title == "Sonic the Hedgehog"
    assert r.regions == ("US",)
    assert r.languages == ()
    assert r.revision is None
    assert r.dump_status == DumpStatus.UNKNOWN
    assert r.convention == NamingConvention.NO_INTRO
    assert r.confidence > 0.7


def test_revision_extracted(parser: NoIntroParser) -> None:
    r = parser.parse("Super Mario World (USA) (Rev A).sfc")
    assert r.title == "Super Mario World"
    assert r.regions == ("US",)
    assert r.revision == "Rev A"
    assert r.confidence > 0.8


def test_multi_region_comma_split(parser: NoIntroParser) -> None:
    r = parser.parse("Sonic the Hedgehog (USA, Europe).md")
    assert r.regions == ("EU", "US")  # sorted dedup'd


def test_language_pills(parser: NoIntroParser) -> None:
    r = parser.parse("Castlevania (USA) (En,Fr,De).gba")
    assert r.regions == ("US",)
    assert r.languages == ("de", "en", "fr")


def test_bad_dump_tag_sets_dump_status(parser: NoIntroParser) -> None:
    r = parser.parse("Sonic (USA) [b].md")
    assert r.dump_status == DumpStatus.BADDUMP


def test_hack_tag_sets_dump_status(parser: NoIntroParser) -> None:
    r = parser.parse("Sonic the Hedgehog (USA) [h2].md")
    assert r.dump_status == DumpStatus.HACK


def test_verified_tag(parser: NoIntroParser) -> None:
    r = parser.parse("Sonic the Hedgehog (USA) [!].md")
    assert r.dump_status == DumpStatus.VERIFIED


def test_disc_marker_kept_as_tag(parser: NoIntroParser) -> None:
    r = parser.parse("Final Fantasy IX (USA) (Disc 1).cue")
    assert r.title == "Final Fantasy IX"
    assert r.regions == ("US",)
    assert "Disc 1" in r.tags


def test_japan_to_jp(parser: NoIntroParser) -> None:
    r = parser.parse("Akumajou Densetsu (Japan).nes")
    assert r.regions == ("JP",)


def test_world_to_ww(parser: NoIntroParser) -> None:
    r = parser.parse("Tetris (World).nes")
    assert r.regions == ("WW",)


def test_no_brackets_low_confidence(parser: NoIntroParser) -> None:
    r = parser.parse("game_001.bin")
    # Bare filename has no region/lang/rev/tag → confidence stays at base 0.5
    assert r.confidence <= 0.7
    assert r.title == "game_001"


def test_dispatcher_picks_no_intro_for_clean_input() -> None:
    dispatcher = ParserDispatcher([NoIntroParser()])
    r = dispatcher.parse("Sonic the Hedgehog (USA) (Rev A).md")
    assert r.convention == NamingConvention.NO_INTRO
    assert r.confidence > 0.7


def test_dispatcher_falls_back_to_unknown_when_no_parser_qualifies() -> None:
    """Below-threshold parses surface as ``UNKNOWN``."""

    class AlwaysLow(BaseFilenameParser):
        convention = NamingConvention.UNKNOWN

        def _parse_basename(self, stem: str) -> ParsedFilename:
            return ParsedFilename(title=stem, confidence=0.1)

    dispatcher = ParserDispatcher([AlwaysLow()])
    r = dispatcher.parse("anything.bin")
    assert r.convention == NamingConvention.UNKNOWN
    assert r.confidence == 0.0


def test_dispatcher_requires_at_least_one_parser() -> None:
    with pytest.raises(ValueError):
        ParserDispatcher([])
