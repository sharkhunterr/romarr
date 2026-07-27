"""Pure-function routing for download clients.

Given a release's :class:`SourceKind`, the originating indexer's
optional ``download_client_id`` pin, and the list of currently
configured clients, deterministically pick which client to hand the
release to. No I/O — the registry / API layer fetches the candidates
and consumes the resulting :class:`RoutingDecision`.

Routing rules (FR-014, FR-015, FR-016):

  1. **Indexer override**. If the indexer pins a specific
     ``download_client_id`` AND that client is enabled AND it can
     accept the source kind, the pinned client wins outright —
     priority is ignored. This matches Sonarr/Radarr's
     per-indexer-pin behaviour.
  2. **Priority fallback**. Otherwise pick the eligible candidate
     with the lowest ``priority`` (1 = preferred, 100 = last). Ties
     break on the lower ``id`` so the choice is stable.
  3. **No-eligible-client**. If no candidate matches, return a
     :class:`RoutingDecision` with ``chosen_via='no_eligible_client'``.
     Callers feed the decision through :func:`consume_decision`,
     which raises :class:`NoEligibleClientError` so the grab is
     rejected with a structured error event (FR-016 / SC-005).

Source-form preference (FR-003a / CL002) lives in
:func:`select_torrent_form` / :func:`select_nzb_form`. The routing
function operates on :class:`SourceKind` only — picking *which*
form to send is a separate, post-routing concern.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from romarr.downloaders.errors import NoEligibleClientError
from romarr.downloaders.types import (
    NzbBytes,
    NzbSource,
    NzbUrl,
    RoutingDecision,
    SourceKind,
    TorrentBytes,
    TorrentMagnet,
    TorrentSource,
    TorrentUrl,
)


class RoutingCandidate(BaseModel):
    """Minimum slice of a configured download client that routing reads.

    Decoupled from the SQLAlchemy model so the caller can hand-build
    candidates in tests without spinning up a session, AND so the
    routing function stays trivially pure (no ORM lazy-loading
    side effects).
    """

    model_config = ConfigDict(extra="forbid")

    id: int
    priority: int = Field(ge=1, le=100)
    enabled: bool
    enable_for_torrents: bool
    enable_for_usenet: bool
    # Populated from ``DownloadClient.is_configured`` — True iff the
    # row carries the credential its type expects (password for
    # qBit/Deluge, api_key for SAB/Grabarr). Default True keeps
    # older callers that don't wire the field back-compatible.
    is_configured: bool = True

    def supports(self, source_kind: SourceKind) -> bool:
        if source_kind is SourceKind.TORRENT:
            return self.enable_for_torrents
        return self.enable_for_usenet


def _eligible(candidate: RoutingCandidate, source_kind: SourceKind) -> bool:
    # Skip clients missing their credentials — dispatching to one
    # produces confusing ``pending_retry`` errors when the actual
    # cause is "no password saved". The Test button is the operator
    # signal that a client is ready; is_configured=True mirrors it.
    return (
        candidate.enabled
        and candidate.is_configured
        and candidate.supports(source_kind)
    )


def route_release(
    *,
    source_kind: SourceKind,
    indexer_download_client_id: int | None,
    candidates: list[RoutingCandidate],
) -> RoutingDecision:
    """Deterministic routing decision for one release.

    See module docstring for the full rule set. Pure function — no
    side effects, no I/O. Safe to call from any context.
    """
    considered = [c.id for c in candidates]

    pinned: RoutingCandidate | None = None
    pin_rejection: str | None = None
    if indexer_download_client_id is not None:
        pinned = next(
            (c for c in candidates if c.id == indexer_download_client_id),
            None,
        )
        if pinned is None:
            pin_rejection = (
                f"indexer-pinned client {indexer_download_client_id} "
                "not found in candidates"
            )
        elif not pinned.enabled:
            pin_rejection = (
                f"indexer-pinned client {indexer_download_client_id} is disabled"
            )
        elif not pinned.supports(source_kind):
            pin_rejection = (
                f"indexer-pinned client {indexer_download_client_id} "
                f"does not support {source_kind.value} sources"
            )
        else:
            return RoutingDecision(
                chosen_client_id=pinned.id,
                chosen_via="indexer_override",
                source_kind=source_kind,
                candidates_considered=considered,
                rejection_reason=None,
            )

    eligible = [c for c in candidates if _eligible(c, source_kind)]
    if eligible:
        # priority asc, id asc — stable pick.
        eligible.sort(key=lambda c: (c.priority, c.id))
        return RoutingDecision(
            chosen_client_id=eligible[0].id,
            chosen_via="priority",
            source_kind=source_kind,
            candidates_considered=considered,
            rejection_reason=pin_rejection,
        )

    return RoutingDecision(
        chosen_client_id=None,
        chosen_via="no_eligible_client",
        source_kind=source_kind,
        candidates_considered=considered,
        rejection_reason=pin_rejection
        or (
            f"no enabled client supports {source_kind.value} sources"
        ),
    )


def consume_decision(decision: RoutingDecision) -> int:
    """Unwrap a chosen client id, raising if routing rejected the grab.

    Use this at the boundary where routing's "decision" must become
    an actual grab — it converts the ``no_eligible_client`` envelope
    into a :class:`NoEligibleClientError` (FR-016 / SC-005).
    """
    if decision.chosen_client_id is None:
        raise NoEligibleClientError(
            decision.rejection_reason or "no eligible download client"
        )
    return decision.chosen_client_id


# ---------------------------------------------------------------------------
# Source-form preference (FR-003a / CL002)
# ---------------------------------------------------------------------------


def select_torrent_form(forms: list[TorrentSource]) -> TorrentSource:
    """Pick the highest-preference torrent source form from a list.

    Order: ``.torrent`` URL > raw ``.torrent`` bytes > magnet URL.
    Callers pass every form the indexer published; this picks one.
    """
    if not forms:
        raise ValueError("at least one TorrentSource is required")
    for cls in (TorrentUrl, TorrentBytes, TorrentMagnet):
        for form in forms:
            if isinstance(form, cls):
                return form
    raise ValueError("no recognised TorrentSource form in input")  # pragma: no cover


def select_nzb_form(forms: list[NzbSource]) -> NzbSource:
    """Pick the highest-preference NZB source form.

    Order: ``.nzb`` URL > raw ``.nzb`` bytes.
    """
    if not forms:
        raise ValueError("at least one NzbSource is required")
    for cls in (NzbUrl, NzbBytes):
        for form in forms:
            if isinstance(form, cls):
                return form
    raise ValueError("no recognised NzbSource form in input")  # pragma: no cover


__all__ = [
    "RoutingCandidate",
    "consume_decision",
    "route_release",
    "select_nzb_form",
    "select_torrent_form",
]
