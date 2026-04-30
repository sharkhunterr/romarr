"""Same-GUID dedup tests (T022)."""

from __future__ import annotations

from collections.abc import Callable

from romarr.indexers import dedup_by_guid, parse_search
from romarr.indexers.types import SearchResult


def test_same_guid_collapsed_with_union_categories(
    torznab_response: Callable[[str], bytes],
) -> None:
    """T022: two items sharing a GUID collapse to one with category union."""
    results = parse_search(
        torznab_response("torznab_search/duplicate_guid_two_categories.xml"),
        indexer_id=1,
    )
    assert len(results) == 1
    survivor = results[0]
    assert set(survivor.categories) == {1060, 7010}


def test_dedup_preserves_first_occurrence_order() -> None:
    a = SearchResult(
        indexer_id=1, guid="a", title="A", link="http://a", categories=[100]
    )
    b = SearchResult(
        indexer_id=1, guid="b", title="B", link="http://b", categories=[200]
    )
    a_dup = SearchResult(
        indexer_id=1, guid="a", title="A2", link="http://a2", categories=[300]
    )
    out = dedup_by_guid([a, b, a_dup])
    assert [r.guid for r in out] == ["a", "b"]
    # ``a``'s categories now include 100 + 300 (the duplicate).
    assert set(out[0].categories) == {100, 300}
    # ``b`` is untouched.
    assert out[1].categories == [200]


def test_dedup_idempotent_on_unique_input() -> None:
    items = [
        SearchResult(indexer_id=1, guid=g, title=g, link="http://x")
        for g in ("a", "b", "c")
    ]
    assert [r.guid for r in dedup_by_guid(items)] == ["a", "b", "c"]
