"""Property-based test for the parent-cycle detector (T060).

Hypothesis generates random parent_platform_slug graphs over a fixed
slug pool and verifies the validator's iterative DFS matches a
reference implementation built around :class:`graphlib.TopologicalSorter`.
The reference raises ``CycleError`` iff the graph has a cycle, which
gives us a black-box oracle independent of the validator's own DFS.
"""

from __future__ import annotations

from graphlib import CycleError, TopologicalSorter

from hypothesis import given, settings
from hypothesis import strategies as st

from romarr.platform_packs.validator import _find_cycle

# Fixed slug pool keeps the search space tractable. Cycles + DAGs both
# fit in a 5-node graph, and graphlib's sorter handles arbitrary node
# counts so a small pool is fine.
_SLUGS: tuple[str, ...] = ("a", "b", "c", "d", "e")


def _has_cycle_reference(parent_of: dict[str, str | None]) -> bool:
    """Reference oracle: graphlib raises CycleError iff there's a cycle."""
    sorter: TopologicalSorter[str] = TopologicalSorter()
    for slug in parent_of:
        sorter.add(slug)
    for child, parent in parent_of.items():
        if parent is not None and parent in parent_of:
            # Edge: child depends on parent (parent must come first).
            sorter.add(child, parent)
    try:
        list(sorter.static_order())
    except CycleError:
        return True
    return False


@settings(max_examples=200, deadline=None)
@given(
    # Each slug independently picks either None (no parent) or another
    # slug (possibly itself).
    parents=st.fixed_dictionaries(
        {slug: st.one_of(st.none(), st.sampled_from(_SLUGS)) for slug in _SLUGS},
    ),
)
def test_cycle_detector_matches_reference(
    parents: dict[str, str | None],
) -> None:
    """For every random graph, the validator's cycle detector and the
    reference must agree."""
    platforms = [
        {"slug": slug, "parent_platform_slug": parents[slug]} for slug in _SLUGS
    ]
    expected = _has_cycle_reference(parents)
    cycle = _find_cycle(platforms)
    detected = cycle is not None
    assert detected == expected, (
        f"validator and reference disagreed for parents={parents}; "
        f"reference={expected}, detector={detected}, cycle={cycle}"
    )
    if cycle is not None:
        # Every cycle member must point to the next one in the cycle
        # (modulo wrap-around). This catches degenerate "single-node
        # self-loop" detections too.
        for current, next_node in zip(cycle, [*cycle[1:], cycle[0]], strict=True):
            assert parents[current] == next_node, (
                f"cycle {cycle} member {current!r} should point at "
                f"{next_node!r}, got {parents[current]!r}"
            )
