"""``t=caps`` parser tests (T016, T017)."""

from __future__ import annotations

from collections.abc import Callable

from romarr.indexers import parse_caps


def test_valid_full_caps(torznab_response: Callable[[str], bytes]) -> None:
    caps = parse_caps(torznab_response("torznab_caps/valid_full.xml"))
    assert caps.server == "Test Indexer"
    assert "search" in caps.searching
    assert caps.searching["search"]["available"] is True
    assert caps.searching["search"]["supportedParams"] == ["q", "cat", "limit"]
    # Categories include both top-level and subcat ids.
    for required in (1000, 1010, 1060, 1080, 7000, 7010):
        assert required in caps.categories


def test_no_search_block_returns_empty_searching(
    torznab_response: Callable[[str], bytes],
) -> None:
    caps = parse_caps(torznab_response("torznab_caps/no_search_block.xml"))
    assert caps.searching == {}
    assert 1000 in caps.categories


def test_caps_handles_minor_xml_noise() -> None:
    """A trailing newline / BOM doesn't blow up the parser."""
    body = b"\xef\xbb\xbf<?xml version='1.0'?><caps><server title='X'/></caps>\n"
    caps = parse_caps(body)
    assert caps.server == "X"
