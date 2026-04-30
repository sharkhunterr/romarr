"""RomM passthrough corpus (T044 — ≥10 fixtures, SC-004).

The RomM-friendly template prefixes the platform slug and passes
the original release filename through verbatim — RomM consumes the
file directly without re-naming.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from romarr.profiles.naming import NamingTemplateEngine

_TEMPLATE = "{{ Platform.Slug }}/{{ Release.OriginalName }}"


_CORPUS: list[dict[str, object]] = [
    {
        "id": "megadrive-no-intro",
        "tokens": {
            "release_OriginalName": "Sonic the Hedgehog (USA).md",
        },
        "expected": "megadrive/Sonic the Hedgehog (USA).md",
    },
    {
        "id": "snes",
        "tokens": {
            "platform_Slug": "snes",
            "release_OriginalName": "Super Mario World (USA).sfc",
        },
        "expected": "snes/Super Mario World (USA).sfc",
    },
    {
        "id": "gba",
        "tokens": {
            "platform_Slug": "gba",
            "release_OriginalName": "Pokemon Ruby (EUR).gba",
        },
        "expected": "gba/Pokemon Ruby (EUR).gba",
    },
    {
        "id": "n64",
        "tokens": {
            "platform_Slug": "n64",
            "release_OriginalName": "Zelda - Ocarina of Time (USA).z64",
        },
        "expected": "n64/Zelda - Ocarina of Time (USA).z64",
    },
    {
        "id": "ps1-chd",
        "tokens": {
            "platform_Slug": "ps1",
            "release_OriginalName": "Final Fantasy VII (USA).chd",
        },
        "expected": "ps1/Final Fantasy VII (USA).chd",
    },
    {
        "id": "preserves-tags",
        "tokens": {
            "release_OriginalName": "Sonic the Hedgehog (USA) [!].md",
        },
        "expected": "megadrive/Sonic the Hedgehog (USA) [!].md",
    },
    {
        "id": "preserves-revision",
        "tokens": {
            "release_OriginalName": "Sonic the Hedgehog (USA) (Rev A).md",
        },
        "expected": "megadrive/Sonic the Hedgehog (USA) (Rev A).md",
    },
    {
        "id": "compressed",
        "tokens": {
            "release_OriginalName": "Sonic the Hedgehog (USA).7z",
        },
        "expected": "megadrive/Sonic the Hedgehog (USA).7z",
    },
    {
        "id": "long-name",
        "tokens": {
            "release_OriginalName": (
                "The Legend of Zelda - A Link to the Past (USA) (Rev 1).sfc"
            ),
            "platform_Slug": "snes",
        },
        "expected": "snes/The Legend of Zelda - A Link to the Past (USA) (Rev 1).sfc",
    },
    {
        "id": "preserves-illegal-char-in-name",
        "tokens": {
            "release_OriginalName": "Star Wars: Knights of the Old Republic (USA).iso",
            "platform_Slug": "xbox",
        },
        "expected": "xbox/Star Wars_ Knights of the Old Republic (USA).iso",
    },
    {
        "id": "minimal",
        "tokens": {
            "platform_Slug": "x",
            "release_OriginalName": "y.rom",
        },
        "expected": "x/y.rom",
    },
]


@pytest.mark.parametrize("row", _CORPUS, ids=[str(r["id"]) for r in _CORPUS])
def test_romm_template_renders_corpus(
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
