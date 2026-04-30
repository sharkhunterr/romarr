"""``t=search`` parser tests (T018, T023)."""

from __future__ import annotations

from collections.abc import Callable

from hypothesis import given, settings
from hypothesis import strategies as st

from romarr.indexers import FieldProvenance, parse_search


def test_vanilla_no_extended_attrs_leaves_provenance_null(
    torznab_response: Callable[[str], bytes],
) -> None:
    results = parse_search(
        torznab_response("torznab_search/vanilla_no_extended.xml"),
        indexer_id=42,
    )
    assert len(results) == 1
    item = results[0]
    assert item.indexer_id == 42
    assert item.guid == "guid-vanilla-1"
    assert item.title.startswith("Sonic the Hedgehog")
    # No extended attrs → all *_provenance fields are None.
    assert item.region is None
    assert item.region_provenance is None
    assert item.languages == []
    assert item.languages_provenance is None
    assert item.size_bytes == 524288
    assert 1060 in item.categories


def test_publish_date_round_trip(
    torznab_response: Callable[[str], bytes],
) -> None:
    results = parse_search(
        torznab_response("torznab_search/vanilla_no_extended.xml"),
        indexer_id=1,
    )
    pub = results[0].publish_date
    assert pub is not None
    assert pub.year == 2025 and pub.month == 6 and pub.day == 1


@settings(max_examples=50, deadline=None)
@given(noise=st.binary(min_size=0, max_size=400))
def test_property_parser_tolerates_random_bytes(noise: bytes) -> None:
    """T023: feed random bytes; the parser may raise IndexerProtocolError
    but MUST NOT raise any other type. Returns a list when it succeeds."""
    from romarr.indexers.errors import IndexerProtocolError

    try:
        out = parse_search(noise, indexer_id=1)
    except IndexerProtocolError:
        return
    assert isinstance(out, list)


def test_torznab_extended_attrs_set_provenance(
    torznab_response: Callable[[str], bytes],
) -> None:
    results = parse_search(
        torznab_response("torznab_search/extended_torznab_namespace.xml"),
        indexer_id=2,
    )
    item = results[0]
    assert item.region == "US"
    assert item.region_provenance == FieldProvenance.TORZNAB
    assert item.languages == ["en", "fr"]
    assert item.languages_provenance == FieldProvenance.TORZNAB
    assert item.seeders == 42
    assert item.hash_sha1 == "abcdef1234567890abcdef1234567890abcdef12"
