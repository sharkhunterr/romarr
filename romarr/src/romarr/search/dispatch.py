"""Bridge from a winning :class:`Candidate` to the download-clients
routing module (Phase 7 — DISPATCH).

The search subsystem doesn't decide HOW to grab — it picks WHAT to
grab. Once a winner is chosen, this module hands the result to spec
005's :func:`route_release` to pick the right download client, then
calls the client's ``add_torrent`` / ``add_nzb`` based on the source
kind.

Outcome surface:

  * ``GRABBED`` — the chosen client accepted the source; returns the
    client-native id (qBit info-hash, SAB nzo_id).
  * ``NO_ELIGIBLE_CLIENT`` — no enabled client supports the source
    kind (FR-016 / SC-005). The caller records this on the
    ``search_history`` row's ``no_grab_reason``.
  * ``PENDING_RETRY`` — transient :class:`ConnectionError`; spec 005's
    stuck-grab retry policy owns the recovery, this module only
    records the state transition.
  * ``FAILED`` — non-transient failure (auth / version / unknown);
    surfaced as the row's ``no_grab_reason``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from romarr.downloaders.errors import (
    AuthError,
    NoEligibleClientError,
    VersionError,
)
from romarr.downloaders.errors import (
    ConnectionError as DownloaderConnError,
)
from romarr.downloaders.routing import (
    RoutingCandidate,
    consume_decision,
    route_release,
)
from romarr.downloaders.types import (
    NzbUrl,
    SourceKind,
    TorrentMagnet,
    TorrentUrl,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from romarr.downloaders.base import DownloadClient
    from romarr.search.types import Candidate


class DispatchStatus(StrEnum):
    GRABBED = "grabbed"
    NO_ELIGIBLE_CLIENT = "no_eligible_client"
    PENDING_RETRY = "pending_retry"
    FAILED = "failed"


@dataclass(frozen=True)
class DispatchOutcome:
    status: DispatchStatus
    client_id: int | None = None
    client_native_id: str | None = None
    reason: str | None = None


_ClientFactory = "Callable[[int], Awaitable[DownloadClient]]"


def _infer_source_kind(candidate: Candidate) -> SourceKind:
    """Heuristic: ``.torrent`` / ``magnet:`` URL → torrent;
    everything else (assumed ``.nzb``) → usenet.

    The pipeline carries the structured indexer protocol on the
    parent indexer row in the foundation; for MVP we sniff the URL.
    """
    url = (candidate.download_url or "").lower()
    if url.startswith("magnet:") or url.endswith(".torrent") or "torrent" in url:
        return SourceKind.TORRENT
    return SourceKind.USENET


async def dispatch_winner(
    *,
    candidate: Candidate,
    candidates: list[RoutingCandidate],
    indexer_pin: int | None = None,
    client_factory: Callable[[int], Awaitable[DownloadClient]],
    standard_tags: list[str] | None = None,
    source_kind: SourceKind | None = None,
) -> DispatchOutcome:
    """Pick a download client + hand the source to it.

    ``candidates`` is the list of currently-configured download
    clients (usually preloaded from the round); ``indexer_pin`` is
    the originating indexer's optional ``download_client_id``.

    ``source_kind`` overrides the URL-sniffing heuristic. Callers
    that know the originating indexer's protocol (Torznab → torrent,
    Newznab → usenet) should pass it explicitly — Prowlarr proxies
    every download through ``/{id}/download?apikey=…&link=…``,
    which exposes neither ``magnet:`` nor ``.torrent`` to the
    sniffer and used to default to USENET (= no eligible client
    when only a torrent client is configured).

    Returns a :class:`DispatchOutcome` the caller threads into the
    ``search_history`` row's ``no_grab_reason`` / ``score`` / etc.
    """
    if source_kind is None:
        source_kind = _infer_source_kind(candidate)
    decision = route_release(
        source_kind=source_kind,
        indexer_download_client_id=indexer_pin,
        candidates=candidates,
    )
    try:
        client_id = consume_decision(decision)
    except NoEligibleClientError as exc:
        return DispatchOutcome(
            status=DispatchStatus.NO_ELIGIBLE_CLIENT,
            reason=str(exc),
        )

    try:
        client = await client_factory(client_id)
    except Exception as exc:
        return DispatchOutcome(
            status=DispatchStatus.FAILED,
            client_id=client_id,
            reason=f"client construction failed: {exc}",
        )

    tags = list(standard_tags or [])
    try:
        if source_kind is SourceKind.TORRENT:
            url = candidate.download_url
            source = (
                TorrentMagnet(magnet_uri=url)
                if url.startswith("magnet:")
                else TorrentUrl(url=url)
            )
            native_id = await client.add_torrent(
                source, category="romarr", tags=tags
            )
        else:
            source_n = NzbUrl(url=candidate.download_url)
            native_id = await client.add_nzb(source_n, category="romarr")
    except DownloaderConnError as exc:
        return DispatchOutcome(
            status=DispatchStatus.PENDING_RETRY,
            client_id=client_id,
            reason=f"transient: {exc}",
        )
    except (AuthError, VersionError) as exc:
        return DispatchOutcome(
            status=DispatchStatus.FAILED,
            client_id=client_id,
            reason=f"non-transient: {exc}",
        )
    except Exception as exc:
        return DispatchOutcome(
            status=DispatchStatus.FAILED,
            client_id=client_id,
            reason=f"unexpected: {exc}",
        )

    return DispatchOutcome(
        status=DispatchStatus.GRABBED,
        client_id=client_id,
        client_native_id=native_id,
    )


__all__ = ["DispatchOutcome", "DispatchStatus", "dispatch_winner"]
