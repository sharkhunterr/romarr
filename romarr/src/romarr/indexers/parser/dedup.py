"""Same-GUID dedup (T026, FR-026, SC-008).

When an indexer returns multiple ``<item>`` rows with the same
``<guid>`` (typical when a release sits in multiple Newznab
categories), Romarr collapses them to one :class:`SearchResult`
whose ``categories`` list is the union of every duplicate's
categories. The first occurrence's other fields win.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from romarr.indexers.types import SearchResult


def dedup_by_guid(items: list[SearchResult]) -> list[SearchResult]:
    """Collapse same-GUID rows; pure function (no I/O, deterministic).

    Order of the first occurrence is preserved. The categories list
    on the survivor is the dedup-preserving union of all duplicates'
    categories.
    """
    out: list[SearchResult] = []
    by_guid: dict[str, int] = {}  # guid → index into ``out``
    for item in items:
        existing_idx = by_guid.get(item.guid)
        if existing_idx is None:
            by_guid[item.guid] = len(out)
            out.append(item)
            continue
        # Merge categories into the existing survivor.
        survivor = out[existing_idx]
        merged: list[int] = list(survivor.categories)
        seen = set(merged)
        for cat in item.categories:
            if cat not in seen:
                seen.add(cat)
                merged.append(cat)
        out[existing_idx] = survivor.model_copy(update={"categories": merged})
    return out


__all__ = ["dedup_by_guid"]
