"""Extended-attribute extraction tests (T019, T020, T021)."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from romarr.indexers import (
    DatSource,
    FieldProvenance,
    normalize_languages,
    normalize_region,
    parse_search,
)


def test_torznab_namespace_region_normalised(
    torznab_response: Callable[[str], bytes],
) -> None:
    results = parse_search(
        torznab_response("torznab_search/extended_torznab_namespace.xml"),
        indexer_id=1,
    )
    item = results[0]
    assert item.region == "US"
    assert item.region_provenance == FieldProvenance.TORZNAB


def test_grabarr_namespace_region_overrides_torznab(
    torznab_response: Callable[[str], bytes],
) -> None:
    """When both namespaces emit the same attr name, grabarr wins."""
    results = parse_search(
        torznab_response("torznab_search/extended_grabarr_namespace.xml"),
        indexer_id=1,
    )
    item = results[0]
    assert item.region == "EU"
    assert item.region_provenance == FieldProvenance.GRABARR
    # Other grabarr-only attributes round-trip too.
    assert item.dat_source == DatSource.NO_INTRO
    assert item.dat_source_provenance == FieldProvenance.GRABARR
    assert item.dump_tags == ["verified", "trainer"]


def test_unknown_region_value_dropped(
    torznab_response: Callable[[str], bytes],
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("WARNING"):
        results = parse_search(
            torznab_response("torznab_search/unknown_extended_value.xml"),
            indexer_id=1,
        )
    item = results[0]
    # The unknown ZZ region is dropped; field stays None.
    assert item.region is None
    assert item.region_provenance is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("USA", "US"),
        ("USA ", "US"),
        ("eur", "EU"),
        ("Europe", "EU"),
        ("Japan", "JP"),
        ("WORLD", "WW"),
        ("FR", "FR"),
        ("france", "FR"),
        ("Deutsch", None),  # not in our dictionary
        ("ZZ", None),
    ],
)
def test_normalize_region(raw: str, expected: str | None) -> None:
    assert normalize_region(raw) == expected


def test_normalize_languages_csv() -> None:
    assert normalize_languages("en, fr; ja") == ["en", "fr", "ja"]


def test_normalize_languages_dedupes() -> None:
    assert normalize_languages("en,en,en") == ["en"]


def test_normalize_languages_handles_unknown() -> None:
    """Unknown language codes are silently dropped."""
    assert normalize_languages("en, klingon, fr") == ["en", "fr"]


def test_normalize_languages_accepts_list() -> None:
    assert normalize_languages(["English", "francais"]) == ["en", "fr"]
