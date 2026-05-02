"""Tests for the ReleaseFacts builder (slice 82)."""

from __future__ import annotations

import pytest

from romarr.identification.merger import MergedIdentification
from romarr.identification.parsers.base import (
    DumpStatus,
    NamingConvention,
)
from romarr.importer._release_facts import build_release_facts
from romarr.profiles.types import ReleaseFacts


def _merged(
    *,
    title: str | None = "Sonic the Hedgehog",
    regions: tuple[str, ...] = ("USA",),
    languages: tuple[str, ...] = ("en",),
    revision: str | None = "Rev 1",
    dump_status: DumpStatus = DumpStatus.VERIFIED,
    naming_convention: NamingConvention = NamingConvention.NO_INTRO,
) -> MergedIdentification:
    return MergedIdentification(
        title=title,
        platform_slug="megadrive",
        regions=regions,
        languages=languages,
        revision=revision,
        dump_status=dump_status,
        naming_convention=naming_convention,
        serial=None,
        confidence=0.95,
        contributing_sources=(),
        conflicts=(),
        extra={},
    )


def test_build_release_facts_passthrough_minimum() -> None:
    facts = build_release_facts(
        merged=_merged(),
        file_format="md",
        dat_verified=True,
    )
    assert isinstance(facts, ReleaseFacts)
    assert facts.title == "Sonic the Hedgehog"
    assert facts.regions == ("USA",)
    assert facts.languages == ("en",)
    assert facts.revision == "Rev 1"
    assert facts.dump_status == DumpStatus.VERIFIED
    assert facts.naming_convention == NamingConvention.NO_INTRO
    assert facts.file_format == "md"
    assert facts.dat_verified is True
    # Optional fields default to None / empty.
    assert facts.release_size is None
    assert facts.indexer_source is None
    assert facts.release_group is None
    assert facts.tags == ()


def test_build_release_facts_none_title_becomes_empty() -> None:
    """An unidentified file may have no title; the gate works
    with empty title — Custom Formats that key on title just
    don't match."""
    facts = build_release_facts(
        merged=_merged(title=None),
        file_format="bin",
        dat_verified=False,
    )
    assert facts.title == ""


def test_build_release_facts_passthrough_optional_signals() -> None:
    facts = build_release_facts(
        merged=_merged(),
        file_format="zip",
        dat_verified=False,
        release_size=12_345_678,
        indexer_source="torznab",
        release_group="SNESTeam",
        tags=("imported", "rev-checked"),
    )
    assert facts.release_size == 12_345_678
    assert facts.indexer_source == "torznab"
    assert facts.release_group == "SNESTeam"
    assert facts.tags == ("imported", "rev-checked")


def test_build_release_facts_unknown_dump_status_passes_through() -> None:
    """Unidentified path: dump_status defaults to UNKNOWN.
    The dump-profile gate handles UNKNOWN by rejecting unless
    the operator opts in."""
    facts = build_release_facts(
        merged=_merged(dump_status=DumpStatus.UNKNOWN),
        file_format="raw",
        dat_verified=False,
    )
    assert facts.dump_status == DumpStatus.UNKNOWN


def test_build_release_facts_is_frozen() -> None:
    """ReleaseFacts is frozen — the gate can rely on inputs
    not mutating mid-evaluation."""
    facts = build_release_facts(
        merged=_merged(),
        file_format="md",
        dat_verified=True,
    )
    with pytest.raises(Exception):  # pydantic ValidationError or AttributeError
        facts.title = "tampered"  # type: ignore[misc]
