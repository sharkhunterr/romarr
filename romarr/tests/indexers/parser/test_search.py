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


def test_grabarr_collection_attr_sets_naming_convention(
    torznab_response: Callable[[str], bytes],
) -> None:
    """The Minerva ``<torznab:attr name="collection">`` carries the dump
    authority (No-Intro / Redump / TOSEC-ISO / …) — Romarr maps it onto
    :class:`NamingConvention` so the profile scorer's
    ``no-intro-convention`` / ``redump-convention`` custom formats fire.
    Non-authority collections (RetroAchievements / IA / MAME) leave the
    convention as ``UNKNOWN`` so the filename parser keeps a shot.
    An explicit ``naming_convention`` attr always wins over a derived
    one to preserve forward-compat with future indexers that emit both.
    """
    from romarr.domain.enums import NamingConvention

    results = parse_search(
        torznab_response("torznab_search/grabarr_collection_no_intro.xml"),
        indexer_id=7,
    )
    by_guid = {r.guid: r for r in results}

    # 1. No-Intro → NO_INTRO, provenance recorded.
    ni = by_guid["guid-collection-no-intro"]
    assert ni.naming_convention == NamingConvention.NO_INTRO
    assert ni.naming_convention_provenance == FieldProvenance.TORZNAB

    # 2. TOSEC-ISO and TOSEC-PIX both collapse to canonical TOSEC.
    tosec = by_guid["guid-collection-tosec-iso"]
    assert tosec.naming_convention == NamingConvention.TOSEC

    # 3. RetroAchievements is not a naming authority — convention stays
    #    unset (None) so a downstream filename parser keeps a vote.
    ra = by_guid["guid-collection-ra"]
    assert ra.naming_convention is None
    assert ra.naming_convention_provenance is None

    # 4. Explicit naming_convention attr beats a derived one (collection
    #    is opportunistic; an explicit field is intentional).
    explicit = by_guid["guid-precedence-wins"]
    assert explicit.naming_convention == NamingConvention.REDUMP
