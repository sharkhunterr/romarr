"""TOSEC naming corpus (T042 — ≥10 fixtures, SC-004).

The canonical TOSEC template stamps year + publisher + region.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from romarr.profiles.naming import NamingTemplateEngine

_TEMPLATE = (
    "{{ Game.Title }} ({{ Game.Year }})({{ Game.Publisher }})"
    "({{ Release.Region }}).{{ Dump.Extension }}"
)


_CORPUS: list[dict[str, object]] = [
    {
        "id": "sonic-1991",
        "tokens": {"release_Region": "USA"},
        "expected": "Sonic the Hedgehog (1991)(Sega)(USA).md",
    },
    {
        "id": "sonic-1992-jpn",
        "tokens": {
            "game_Year": "1992",
            "release_Region": "JPN",
        },
        "expected": "Sonic the Hedgehog (1992)(Sega)(JPN).md",
    },
    {
        "id": "alt-publisher",
        "tokens": {
            "game_Publisher": "Sonic Team",
            "release_Region": "USA",
        },
        "expected": "Sonic the Hedgehog (1991)(Sonic Team)(USA).md",
    },
    {
        "id": "ff-square",
        "tokens": {
            "game_Title": "Final Fantasy",
            "game_Year": "1987",
            "game_Publisher": "Square",
            "release_Region": "JPN",
            "dump_Extension": "nes",
        },
        "expected": "Final Fantasy (1987)(Square)(JPN).nes",
    },
    {
        "id": "alt-extension",
        "tokens": {
            "release_Region": "EUR",
            "dump_Extension": "smd",
        },
        "expected": "Sonic the Hedgehog (1991)(Sega)(EUR).smd",
    },
    {
        "id": "world-region",
        "tokens": {"release_Region": "World"},
        "expected": "Sonic the Hedgehog (1991)(Sega)(World).md",
    },
    {
        "id": "kor",
        "tokens": {"release_Region": "KOR"},
        "expected": "Sonic the Hedgehog (1991)(Sega)(KOR).md",
    },
    {
        "id": "long-title",
        "tokens": {
            "game_Title": "The Legend of Zelda: A Link to the Past",
            "game_Year": "1991",
            "game_Publisher": "Nintendo",
            "release_Region": "USA",
        },
        "expected": "The Legend of Zelda_ A Link to the Past (1991)(Nintendo)(USA).md",
    },
    {
        "id": "all-numbers-year",
        "tokens": {"game_Year": "2003", "release_Region": "USA"},
        "expected": "Sonic the Hedgehog (2003)(Sega)(USA).md",
    },
    {
        "id": "publisher-with-amp",
        "tokens": {
            "game_Publisher": "Bandai & Namco",
            "release_Region": "JPN",
        },
        "expected": "Sonic the Hedgehog (1991)(Bandai & Namco)(JPN).md",
    },
    {
        "id": "minimal",
        "tokens": {
            "game_Title": "X",
            "game_Year": "1990",
            "game_Publisher": "Y",
            "release_Region": "USA",
            "dump_Extension": "rom",
        },
        "expected": "X (1990)(Y)(USA).rom",
    },
]


@pytest.mark.parametrize("row", _CORPUS, ids=[str(r["id"]) for r in _CORPUS])
def test_tosec_template_renders_corpus(
    engine: NamingTemplateEngine,
    make_tokens: Callable[..., tuple[object, object, object, object]],
    row: dict[str, object],
) -> None:
    overrides = row["tokens"]
    assert isinstance(overrides, dict)
    game, release, dump, platform = make_tokens(**overrides)
    rendered = engine.render(
        _TEMPLATE,
        game=game,
        release=release,
        dump=dump,
        platform=platform,
    )
    assert rendered == row["expected"], row["id"]


def test_corpus_has_at_least_10_rows() -> None:
    assert len(_CORPUS) >= 10
