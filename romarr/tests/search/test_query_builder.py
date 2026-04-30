"""Query builder tests (T012-T013)."""

from __future__ import annotations

from dataclasses import dataclass, field

from romarr.search.query_builder import build_queries
from romarr.search.types import Query


@dataclass
class _Game:
    title: str
    alt_names: tuple[str, ...] = field(default_factory=tuple)


@dataclass
class _Platform:
    short_name: str = ""
    manufacturer: str = ""


# ---------------------------------------------------------------------------
# T012 — canonical + alt names + platform variants
# ---------------------------------------------------------------------------


def test_canonical_plus_alts() -> None:
    """A Game with two alt names yields:
    canonical + 2 alts + canonical+platform_short + canonical+manufacturer = 5.
    """
    game = _Game(
        title="Sonic the Hedgehog",
        alt_names=("Sonic 1", "Sonik"),
    )
    platform = _Platform(short_name="MD", manufacturer="Sega")
    queries = build_queries(game, platform)
    labels = [q.label for q in queries]
    assert labels == [
        "canonical",
        "alt_name",
        "alt_name",
        "with_platform",
        "with_manufacturer",
    ]
    texts = [q.text for q in queries]
    assert texts == [
        "Sonic the Hedgehog",
        "Sonic 1",
        "Sonik",
        "Sonic the Hedgehog MD",
        "Sonic the Hedgehog Sega",
    ]


def test_no_alts() -> None:
    """A Game with no alt names yields canonical + 2 platform variants = 3."""
    game = _Game(title="Mortal Kombat")
    platform = _Platform(short_name="GEN", manufacturer="Sega")
    queries = build_queries(game, platform)
    assert [q.label for q in queries] == [
        "canonical",
        "with_platform",
        "with_manufacturer",
    ]


def test_dedup_when_alt_equals_canonical() -> None:
    """An alt name identical to the canonical title is dropped."""
    game = _Game(
        title="Sonic the Hedgehog",
        alt_names=("Sonic the Hedgehog", "Alt 2"),
    )
    platform = _Platform(short_name="MD", manufacturer="Sega")
    queries = build_queries(game, platform)
    assert len(queries) == 4  # canonical + 1 alt + 2 platform variants


def test_skips_empty_platform_fields() -> None:
    """When platform has no manufacturer, no manufacturer query is emitted."""
    game = _Game(title="Sonic the Hedgehog")
    platform = _Platform(short_name="MD", manufacturer="")
    queries = build_queries(game, platform)
    assert [q.label for q in queries] == ["canonical", "with_platform"]


def test_returns_query_instances() -> None:
    """Sanity check: every entry is a Pydantic Query instance."""
    game = _Game(title="x")
    platform = _Platform(short_name="MD")
    for q in build_queries(game, platform):
        assert isinstance(q, Query)
