"""Redump naming corpus (T041 — ≥10 fixtures, SC-004).

The canonical Redump template is the simplest of the five: just
title + region + extension. Used predominantly for CD-based platforms.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from romarr.profiles.naming import NamingTemplateEngine

_TEMPLATE = "{{ Game.Title }} ({{ Release.Region }}).{{ Dump.Extension }}"


_CORPUS: list[dict[str, object]] = [
    {
        "id": "usa-md",
        "tokens": {"release_Region": "USA"},
        "expected": "Sonic the Hedgehog (USA).md",
    },
    {
        "id": "eur-cue",
        "tokens": {"release_Region": "EUR", "dump_Extension": "cue"},
        "expected": "Sonic the Hedgehog (EUR).cue",
    },
    {
        "id": "jpn-bin",
        "tokens": {"release_Region": "JPN", "dump_Extension": "bin"},
        "expected": "Sonic the Hedgehog (JPN).bin",
    },
    {
        "id": "world-chd",
        "tokens": {"release_Region": "World", "dump_Extension": "chd"},
        "expected": "Sonic the Hedgehog (World).chd",
    },
    {
        "id": "kor-iso",
        "tokens": {"release_Region": "KOR", "dump_Extension": "iso"},
        "expected": "Sonic the Hedgehog (KOR).iso",
    },
    {
        "id": "usa-zip",
        "tokens": {"release_Region": "USA", "dump_Extension": "zip"},
        "expected": "Sonic the Hedgehog (USA).zip",
    },
    {
        "id": "alt-title",
        "tokens": {"game_Title": "Final Fantasy VII", "release_Region": "USA"},
        "expected": "Final Fantasy VII (USA).md",
    },
    {
        "id": "title-with-colon",
        "tokens": {
            "game_Title": "Star Wars: Knights of the Old Republic",
            "release_Region": "USA",
        },
        "expected": "Star Wars_ Knights of the Old Republic (USA).md",
    },
    {
        "id": "long-title",
        "tokens": {
            "game_Title": (
                "Wizardry: Proving Grounds of the Mad Overlord"
            ),
            "release_Region": "USA",
        },
        "expected": "Wizardry_ Proving Grounds of the Mad Overlord (USA).md",
    },
    {
        "id": "no-extension",
        "tokens": {"release_Region": "USA", "dump_Extension": ""},
        "expected": "Sonic the Hedgehog (USA).",
    },
    {
        "id": "world-plus-eur",
        "tokens": {"release_Region": "World+EUR"},
        "expected": "Sonic the Hedgehog (World+EUR).md",
    },
]


@pytest.mark.parametrize("row", _CORPUS, ids=[str(r["id"]) for r in _CORPUS])
def test_redump_template_renders_corpus(
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
