"""Structured error hierarchy for the search subsystem.

  - :class:`SearchError` — base.
  - :class:`NoEligibleCandidatesError` — every candidate was rejected
    by the pipeline. Manual searches surface this as HTTP 404; the
    background round handlers log and move on.
  - :class:`BlocklistedReleaseError` — a manual grab targets a
    blocklisted release; ``?force=true`` overrides.
  - :class:`OverCapWarning` — informational marker (NOT raised);
    the round orchestrator attaches it to the
    :class:`SearchRoundReport` when an indexer returns more than
    the FR-029 hard cap (default 200) and the surplus is dropped.
"""

from __future__ import annotations


class SearchError(RuntimeError):
    """Base for every search-side failure."""


class NoEligibleCandidatesError(SearchError):
    """Every candidate was rejected by the pipeline.

    Carries the per-candidate :class:`Rejection` list so the UI /
    history view can show the operator exactly why nothing was
    grabbable.
    """

    def __init__(self, *, query: str, rejections: int) -> None:
        super().__init__(
            f"no eligible candidates for query {query!r} "
            f"({rejections} rejected)"
        )
        self.query = query
        self.rejections = rejections


class BlocklistedReleaseError(SearchError):
    """A manual grab targets a release on the blocklist.

    Override with ``?force=true`` on the grab endpoint (FR-022 +
    SC-006). The exception's ``reason`` field carries the
    blocklist row's ``reason`` so the UI can show why it was
    blocked in the first place.
    """

    def __init__(self, *, indexer_guid: str, reason: str) -> None:
        super().__init__(
            f"release {indexer_guid!r} is blocklisted: {reason}"
        )
        self.indexer_guid = indexer_guid
        self.reason = reason


class OverCapWarning(Exception):  # noqa: N818 — informational, not raised
    """Marker — an indexer returned more than the FR-029 hard cap.

    Attached to the round report's ``overcap_indexers`` list rather
    than raised; the orchestrator silently truncates to 200 and
    surfaces the warning to the operator UI.
    """


__all__ = [
    "BlocklistedReleaseError",
    "NoEligibleCandidatesError",
    "OverCapWarning",
    "SearchError",
]
