"""CI smoke test for the default naming templates (T080).

Reads ``src/romarr/profiles/seeders/naming.json`` and asserts that
every shipped non-``custom`` template:

  1. parses cleanly through the sandbox engine (no syntax error,
     no unknown token, no forbidden filter); and
  2. renders to a non-empty string against a canonical fixture
     release without raising.

A typo in the seed JSON now fails the build instead of slipping
into a release.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from romarr.profiles.naming import (
    DumpTokens,
    GameTokens,
    NamingTemplateEngine,
    PlatformTokens,
    ReleaseTokens,
)
from romarr.profiles.seeders import SEED_DIR

_NAMING_JSON = SEED_DIR / "naming.json"


def _canonical_fixture() -> tuple[GameTokens, ReleaseTokens, DumpTokens, PlatformTokens]:
    return (
        GameTokens(
            Title="Sonic the Hedgehog",
            SortTitle="Sonic the Hedgehog",
            Year="1991",
            Publisher="Sega",
        ),
        ReleaseTokens(
            Region="USA",
            Languages="en",
            Revision="Rev A",
            Tags="[!]",
            OriginalName="Sonic the Hedgehog (USA).md",
        ),
        DumpTokens(Extension="md", Hash="abc123"),
        PlatformTokens(Slug="megadrive", Name="Mega Drive"),
    )


_SEEDED_PROFILES: list[dict[str, object]] = json.loads(_NAMING_JSON.read_text())


@pytest.mark.parametrize(
    "profile", _SEEDED_PROFILES, ids=[str(p["seed_key"]) for p in _SEEDED_PROFILES]
)
def test_seeded_template_parses_cleanly(profile: dict[str, object]) -> None:
    engine = NamingTemplateEngine()
    template = profile["template"]
    assert isinstance(template, str)
    engine.validate(template)


@pytest.mark.parametrize(
    "profile", _SEEDED_PROFILES, ids=[str(p["seed_key"]) for p in _SEEDED_PROFILES]
)
def test_seeded_template_renders_non_empty(profile: dict[str, object]) -> None:
    engine = NamingTemplateEngine()
    game, release, dump, platform = _canonical_fixture()
    template = profile["template"]
    assert isinstance(template, str)
    rendered = engine.render(
        template,
        game=game,
        release=release,
        dump=dump,
        platform=platform,
    )
    assert rendered  # non-empty
    assert "(USA)" in rendered or "USA" in rendered or "OriginalName" in template


def test_naming_json_has_three_seeded_profiles() -> None:
    assert len(_SEEDED_PROFILES) == 3
    seed_keys = {str(p["seed_key"]) for p in _SEEDED_PROFILES}
    assert seed_keys == {"no-intro-standard", "es-de-compatible", "romm-passthrough"}


def test_seed_dir_is_resolvable() -> None:
    """SEED_DIR must point at a real directory under the package."""
    assert isinstance(SEED_DIR, Path)
    assert SEED_DIR.is_dir()
    assert (SEED_DIR / "naming.json").is_file()
