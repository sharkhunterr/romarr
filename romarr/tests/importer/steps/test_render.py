"""Render-step tests (T056, T057, T058)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from romarr.importer.steps.render import render_destination
from romarr.profiles.naming.engine import NamingTemplateEngine
from romarr.profiles.naming.tokens import (
    DumpTokens,
    GameTokens,
    PlatformTokens,
    ReleaseTokens,
)


@dataclass(frozen=True)
class _NamingProfile:
    """Duck-typed match for the renderer's profile shape."""

    template: str
    platform_subfolder: bool = True
    multi_disc_subfolder: bool = True
    replace_illegal_chars: bool = True


def _engine() -> NamingTemplateEngine:
    return NamingTemplateEngine()


def _tokens() -> tuple[GameTokens, ReleaseTokens, DumpTokens, PlatformTokens]:
    game = GameTokens(
        Title="Sonic the Hedgehog",
        SortTitle="Sonic the Hedgehog",
        Year="1991",
        Publisher="Sega",
    )
    release = ReleaseTokens(Region="USA", Languages="en")
    dump = DumpTokens(Extension="md", Hash="abcd1234")
    platform = PlatformTokens(Slug="megadrive", Name="Sega Mega Drive")
    return game, release, dump, platform


# ---------------------------------------------------------------------------
# T056 — composes the spec-006 engine
# ---------------------------------------------------------------------------


def test_uses_spec_006_engine() -> None:
    profile = _NamingProfile(
        template="{{ Game.Title }} ({{ Release.Region }})",
    )
    game, release, dump, platform = _tokens()

    result = render_destination(
        engine=_engine(),
        profile=profile,
        library_root=Path("/var/lib/romarr/cartridges"),
        game=game,
        release=release,
        dump=dump,
        platform=platform,
    )
    assert result.basename == "Sonic the Hedgehog (USA)"
    assert result.extension == "md"
    assert result.path.name == "Sonic the Hedgehog (USA).md"


# ---------------------------------------------------------------------------
# T057 — platform subfolder included when configured
# ---------------------------------------------------------------------------


def test_platform_subfolder_when_enabled() -> None:
    profile = _NamingProfile(
        template="{{ Game.Title }} ({{ Release.Region }})",
        platform_subfolder=True,
    )
    game, release, dump, platform = _tokens()

    result = render_destination(
        engine=_engine(),
        profile=profile,
        library_root=Path("/var/lib/romarr/cartridges"),
        game=game,
        release=release,
        dump=dump,
        platform=platform,
    )
    expected = Path(
        "/var/lib/romarr/cartridges/megadrive/Sonic the Hedgehog (USA).md"
    )
    assert result.path == expected


def test_no_platform_subfolder_when_disabled() -> None:
    profile = _NamingProfile(
        template="{{ Game.Title }} ({{ Release.Region }})",
        platform_subfolder=False,
    )
    game, release, dump, platform = _tokens()

    result = render_destination(
        engine=_engine(),
        profile=profile,
        library_root=Path("/var/lib/romarr/cartridges"),
        game=game,
        release=release,
        dump=dump,
        platform=platform,
    )
    expected = Path(
        "/var/lib/romarr/cartridges/Sonic the Hedgehog (USA).md"
    )
    assert result.path == expected


# ---------------------------------------------------------------------------
# T058 — multi-disc subfolder groups every disc together
# ---------------------------------------------------------------------------


def test_multi_disc_subfolder_groups_discs() -> None:
    profile = _NamingProfile(
        template="{{ Game.Title }} ({{ Release.Region }}) (Disc 1)",
        multi_disc_subfolder=True,
    )
    game, release, dump, platform = _tokens()

    result = render_destination(
        engine=_engine(),
        profile=profile,
        library_root=Path("/var/lib/romarr/cd"),
        game=game,
        release=release,
        dump=dump,
        platform=platform,
        multi_disc_total=2,
    )
    expected = Path(
        "/var/lib/romarr/cd/megadrive/Sonic the Hedgehog/"
        "Sonic the Hedgehog (USA) (Disc 1).md"
    )
    assert result.path == expected


def test_no_multi_disc_subfolder_for_single_disc() -> None:
    profile = _NamingProfile(
        template="{{ Game.Title }}",
        multi_disc_subfolder=True,
    )
    game, release, dump, platform = _tokens()

    result = render_destination(
        engine=_engine(),
        profile=profile,
        library_root=Path("/var/lib/romarr/cd"),
        game=game,
        release=release,
        dump=dump,
        platform=platform,
        multi_disc_total=1,
    )
    # No game-named subfolder when multi_disc_total == 1.
    assert result.path == Path(
        "/var/lib/romarr/cd/megadrive/Sonic the Hedgehog.md"
    )


def test_render_is_deterministic() -> None:
    profile = _NamingProfile(
        template="{{ Game.Title }} ({{ Release.Region }})",
    )
    game, release, dump, platform = _tokens()
    a = render_destination(
        engine=_engine(),
        profile=profile,
        library_root=Path("/lib"),
        game=game,
        release=release,
        dump=dump,
        platform=platform,
    )
    b = render_destination(
        engine=_engine(),
        profile=profile,
        library_root=Path("/lib"),
        game=game,
        release=release,
        dump=dump,
        platform=platform,
    )
    assert a == b
