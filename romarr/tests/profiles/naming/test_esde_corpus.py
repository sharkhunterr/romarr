"""ES-DE naming corpus (T043 — ≥10 fixtures, SC-004).

The canonical ES-DE template puts the platform slug as a subfolder
prefix and uses ``SortTitle`` for natural ordering.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from romarr.profiles.naming import NamingTemplateEngine

_TEMPLATE = (
    "{{ Platform.Slug }}/{{ Game.SortTitle }} - "
    "{{ Release.Region }}.{{ Dump.Extension }}"
)


_CORPUS: list[dict[str, object]] = [
    {
        "id": "megadrive-usa",
        "tokens": {"release_Region": "USA"},
        "expected": "megadrive/Sonic the Hedgehog - USA.md",
    },
    {
        "id": "snes-usa",
        "tokens": {
            "platform_Slug": "snes",
            "game_Title": "Super Mario World",
            "game_SortTitle": "Super Mario World",
            "release_Region": "USA",
            "dump_Extension": "sfc",
        },
        "expected": "snes/Super Mario World - USA.sfc",
    },
    {
        "id": "gba-eur",
        "tokens": {
            "platform_Slug": "gba",
            "game_Title": "Pokemon Ruby",
            "game_SortTitle": "Pokemon Ruby",
            "release_Region": "EUR",
            "dump_Extension": "gba",
        },
        "expected": "gba/Pokemon Ruby - EUR.gba",
    },
    {
        "id": "n64-jpn",
        "tokens": {
            "platform_Slug": "n64",
            "game_Title": "The Legend of Zelda: Ocarina of Time",
            "game_SortTitle": "Legend of Zelda - Ocarina of Time",
            "release_Region": "JPN",
            "dump_Extension": "z64",
        },
        "expected": "n64/Legend of Zelda - Ocarina of Time - JPN.z64",
    },
    {
        "id": "ps1-world",
        "tokens": {
            "platform_Slug": "ps1",
            "game_Title": "Final Fantasy VII",
            "game_SortTitle": "Final Fantasy VII",
            "release_Region": "World",
            "dump_Extension": "chd",
        },
        "expected": "ps1/Final Fantasy VII - World.chd",
    },
    {
        "id": "nes-jpn",
        "tokens": {
            "platform_Slug": "nes",
            "game_Title": "Castlevania",
            "game_SortTitle": "Castlevania",
            "release_Region": "JPN",
            "dump_Extension": "nes",
        },
        "expected": "nes/Castlevania - JPN.nes",
    },
    {
        "id": "sortable-the-prefix",
        "tokens": {
            "game_Title": "The Legend of Zelda",
            "game_SortTitle": "Legend of Zelda, The",
            "release_Region": "USA",
        },
        "expected": "megadrive/Legend of Zelda, The - USA.md",
    },
    {
        "id": "title-with-illegal-char",
        "tokens": {
            "game_SortTitle": "Star Wars: Knights",
            "release_Region": "USA",
        },
        "expected": "megadrive/Star Wars_ Knights - USA.md",
    },
    {
        "id": "kor",
        "tokens": {"release_Region": "KOR"},
        "expected": "megadrive/Sonic the Hedgehog - KOR.md",
    },
    {
        "id": "world-plus-eur",
        "tokens": {"release_Region": "World+EUR"},
        "expected": "megadrive/Sonic the Hedgehog - World+EUR.md",
    },
    {
        "id": "minimal",
        "tokens": {
            "platform_Slug": "x",
            "game_SortTitle": "y",
            "release_Region": "USA",
            "dump_Extension": "rom",
        },
        "expected": "x/y - USA.rom",
    },
]


@pytest.mark.parametrize("row", _CORPUS, ids=[str(r["id"]) for r in _CORPUS])
def test_esde_template_renders_corpus(
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
