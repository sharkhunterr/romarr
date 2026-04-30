"""No-Intro naming corpus (T040 — ≥10 fixtures, SC-004).

The canonical No-Intro template renders to a structure like::

    {Title} ({Region}) [({Languages})] [({Revision})] [[{Tags}]].{Extension}

Optional groups vanish via the bracket-drop post-process when the
inner token is empty.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from romarr.profiles.naming import NamingTemplateEngine

_TEMPLATE = (
    "{{ Game.Title }} ({{ Release.Region }})"
    "{% if Release.Languages %} ({{ Release.Languages }}){% endif %}"
    "{% if Release.Revision %} ({{ Release.Revision }}){% endif %}"
    "{% if Release.Tags %} [{{ Release.Tags }}]{% endif %}"
    ".{{ Dump.Extension }}"
)


_CORPUS: list[dict[str, object]] = [
    {
        "id": "minimal-usa",
        "tokens": {"release_Region": "USA"},
        "expected": "Sonic the Hedgehog (USA).md",
    },
    {
        "id": "with-revision",
        "tokens": {"release_Region": "USA", "release_Revision": "Rev A"},
        "expected": "Sonic the Hedgehog (USA) (Rev A).md",
    },
    {
        "id": "with-languages",
        "tokens": {"release_Region": "USA", "release_Languages": "en, fr"},
        "expected": "Sonic the Hedgehog (USA) (en, fr).md",
    },
    {
        "id": "with-tags",
        "tokens": {"release_Region": "USA", "release_Tags": "[!]"},
        "expected": "Sonic the Hedgehog (USA) [[!]].md",
    },
    {
        "id": "all-fields",
        "tokens": {
            "release_Region": "USA",
            "release_Languages": "en",
            "release_Revision": "Rev B",
            "release_Tags": "[!]",
        },
        "expected": "Sonic the Hedgehog (USA) (en) (Rev B) [[!]].md",
    },
    {
        "id": "world-region",
        "tokens": {"release_Region": "World"},
        "expected": "Sonic the Hedgehog (World).md",
    },
    {
        "id": "japan",
        "tokens": {"release_Region": "JPN", "release_Languages": "ja"},
        "expected": "Sonic the Hedgehog (JPN) (ja).md",
    },
    {
        "id": "multi-translation",
        "tokens": {
            "release_Region": "EUR",
            "release_Languages": "en, fr, de",
            "release_Tags": "[T+Fr] [T+En]",
        },
        "expected": "Sonic the Hedgehog (EUR) (en, fr, de) [[T+Fr] [T+En]].md",
    },
    {
        "id": "revision-only-no-langs",
        "tokens": {"release_Region": "USA", "release_Revision": "Rev 0"},
        "expected": "Sonic the Hedgehog (USA) (Rev 0).md",
    },
    {
        "id": "tags-only",
        "tokens": {"release_Region": "USA", "release_Tags": "[hM03]"},
        "expected": "Sonic the Hedgehog (USA) [[hM03]].md",
    },
    {
        "id": "alt-extension",
        "tokens": {"release_Region": "USA", "dump_Extension": "7z"},
        "expected": "Sonic the Hedgehog (USA).7z",
    },
    {
        "id": "title-with-illegal-chars",
        "tokens": {
            "game_Title": "Star Wars: Knights of the Old Republic",
            "release_Region": "USA",
        },
        "expected": "Star Wars_ Knights of the Old Republic (USA).md",
    },
]


@pytest.mark.parametrize("row", _CORPUS, ids=[str(r["id"]) for r in _CORPUS])
def test_no_intro_template_renders_corpus(
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
