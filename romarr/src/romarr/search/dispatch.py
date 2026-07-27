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
    TorrentBytes,
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
            if url.startswith("magnet:"):
                source = TorrentMagnet(magnet_uri=url)
            elif getattr(client, "preserves_source_url", False):
                # The client demands the raw indexer URL (e.g.
                # ``grabarr_direct`` needs the Torznab token URL to
                # hit Grabarr's ``/resolve``). Do NOT convert.
                source = TorrentUrl(url=url)
            else:
                # Resolve the URL ourselves so the download client
                # doesn't have to. Two failure modes we work around:
                #
                #   1. The indexer redirects to a magnet URI
                #      (Grabarr's typical torrent-mode response —
                #      Location: magnet:xxx with 302). Torrent
                #      clients invoked via ``add_torrent_url`` don't
                #      follow HTTP→magnet redirects; Deluge in
                #      particular hangs waiting for a .torrent
                #      binary and eventually reports "User timeout
                #      caused connection failure".
                #   2. The indexer generates the .torrent on demand
                #      and takes 30-90 s (Grabarr's active_seed
                #      mode). Clients' internal HTTP fetch caps at
                #      ~30 s and reports the same timeout as (1).
                #
                # Any resolution failure falls back to the URL form
                # so the pre-proxy behaviour is preserved for
                # indexers we never had trouble with.
                source = await _resolve_torrent_source(url)
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


_TORRENT_BYTES_CAP = 10 * 1024 * 1024  # 10 MiB — .torrent metadata files are ~10-500 KiB
_TORRENT_FETCH_TIMEOUT = 90.0  # seconds; Grabarr active_seed can take 30-60 s


async def _resolve_torrent_source(
    url: str,
) -> TorrentBytes | TorrentMagnet | TorrentUrl:
    """Fetch ``url`` and return the shape the download client can act on.

    Three outcomes :

      * The response is a redirect (301 / 302 / 303 / 307 / 308) whose
        ``Location`` is a ``magnet:`` URI → return
        :class:`TorrentMagnet` so the client adds the hash directly
        (no HTTP fetch on its side).
      * The response body is a ``.torrent`` bencoded blob → return
        :class:`TorrentBytes` and let the client add it from memory.
      * Anything else (network error, oversized body, unexpected
        content-type) → fall back to :class:`TorrentUrl` and let the
        client try the URL directly. Matches the pre-proxy behaviour.
    """
    import httpx

    try:
        async with httpx.AsyncClient(
            timeout=_TORRENT_FETCH_TIMEOUT,
            follow_redirects=False,  # We MUST see a magnet Location.
        ) as client:
            resp = await client.get(url)
    except Exception:  # noqa: BLE001 — fall through to the URL form
        return TorrentUrl(url=url)

    # 30x with magnet Location → hand the client a real magnet URI.
    if resp.status_code in (301, 302, 303, 307, 308):
        location = resp.headers.get("location", "")
        if location.startswith("magnet:"):
            return TorrentMagnet(magnet_uri=location)
        # HTTP → HTTP redirect: give up and let the client follow it.
        return TorrentUrl(url=url)

    # 2xx with a plausibly-torrent body → push bytes.
    if 200 <= resp.status_code < 300:
        body = resp.content
        if len(body) > _TORRENT_BYTES_CAP:
            return TorrentUrl(url=url)
        # ``.torrent`` bencoded files always start with ``d`` (dict).
        # A short sanity check filters HTML error pages that fooled a
        # 200 status code.
        if body.startswith(b"d"):
            return TorrentBytes(data=body)
        return TorrentUrl(url=url)

    # Any other status → let the client try (it may know something
    # we don't, or at least the operator gets a clearer 4xx/5xx).
    return TorrentUrl(url=url)


__all__ = ["DispatchOutcome", "DispatchStatus", "dispatch_winner"]
