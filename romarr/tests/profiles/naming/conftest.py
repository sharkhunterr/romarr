"""Module-local fixtures for naming-engine tests."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from romarr.profiles.naming import (
    DumpTokens,
    GameTokens,
    NamingTemplateEngine,
    PlatformTokens,
    ReleaseTokens,
)


@pytest.fixture
def engine() -> NamingTemplateEngine:
    return NamingTemplateEngine()


@pytest.fixture
def make_tokens() -> Callable[..., tuple[GameTokens, ReleaseTokens, DumpTokens, PlatformTokens]]:
    """Build a fresh (Game, Release, Dump, Platform) namespace tuple.

    Override any field via kwargs prefixed by ``game_`` / ``release_`` /
    ``dump_`` / ``platform_``.
    """

    def _build(**overrides: object) -> tuple[GameTokens, ReleaseTokens, DumpTokens, PlatformTokens]:
        game_kwargs = {
            "Title": "Sonic the Hedgehog",
            "SortTitle": "Sonic the Hedgehog",
            "Year": "1991",
            "Publisher": "Sega",
        }
        release_kwargs = {
            "Region": "USA",
            "Languages": "",
            "Revision": "",
            "Tags": "",
            "OriginalName": "Sonic the Hedgehog (USA).md",
        }
        dump_kwargs = {"Extension": "md", "Hash": "abc123"}
        platform_kwargs = {"Slug": "megadrive", "Name": "Mega Drive"}

        for key, value in overrides.items():
            if key.startswith("game_"):
                game_kwargs[key.removeprefix("game_")] = value  # type: ignore[assignment]
            elif key.startswith("release_"):
                release_kwargs[key.removeprefix("release_")] = value  # type: ignore[assignment]
            elif key.startswith("dump_"):
                dump_kwargs[key.removeprefix("dump_")] = value  # type: ignore[assignment]
            elif key.startswith("platform_"):
                platform_kwargs[key.removeprefix("platform_")] = value  # type: ignore[assignment]
            else:
                raise KeyError(
                    f"unknown override prefix: {key!r}. "
                    f"Use game_/release_/dump_/platform_ prefixes."
                )

        return (
            GameTokens(**game_kwargs),
            ReleaseTokens(**release_kwargs),
            DumpTokens(**dump_kwargs),
            PlatformTokens(**platform_kwargs),
        )

    return _build
