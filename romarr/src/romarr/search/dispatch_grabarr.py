"""Dispatcher-side pre-resolve for Grabarr indexers (slice 426 / R2e).

When the originating indexer has ``implementation == 'grabarr'``,
the grab path runs through this module *before* hitting
:func:`romarr.search.dispatch.dispatch_winner`. We:

1. Fetch ``GET /romarr/{slug}/api/v1/resolve/{token}`` against the
   indexer's Grabarr deploy using the indexer's own apikey (the
   same key the search call used — Grabarr stores one apikey per
   profile and the resolve endpoint reuses it).
2. Branch on the resolve method:

   - ``http_direct``    — keep the candidate and the indexer's
     ``download_client_id`` pin intact. The dispatcher hands the
     Torznab download URL to the linked
     :class:`romarr.downloaders.implementations.grabarr_direct.GrabarrDirectClient`,
     which fetches ``/resolve`` again and streams the upstream
     URL (slice 425).
   - ``torrent_magnet`` — replace the candidate's
     ``download_url`` with the magnet URI, clear the indexer pin,
     and **filter every grabarr_direct row out of the routing
     candidates** so the routing engine picks the operator's qBit
     client by priority. This is the path that lets Vimm /
     AudioBookBay / PlanetEmu / Minerva results land in qBit
     without the BitTorrent-wrap detour Grabarr applies on its
     own Torznab ``/download`` route.

The double-fetch on the ``http_direct`` path (pre-resolve here +
re-resolve inside the client) is a known cost — both calls are
read-only and side-effect-free, so it's a few hundred extra ms on
grab, not a correctness issue. Caching across calls lands in R3
alongside the wizard slice.

See ``romarr/docs/grabarr-direct-protocol.md`` (v0.2.1) §
"How Romarr recognises a Grabarr release at grab time" for the
broader topology.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.downloaders.models import DownloadClient
from romarr.downloaders.routing import RoutingCandidate
from romarr.downloaders.types import ClientType
from romarr.indexers.models import Indexer
from romarr.metadata.encryption import decrypt
from romarr.search.types import Candidate

_log = logging.getLogger(__name__)

_TORZNAB_DOWNLOAD_RE = re.compile(
    r"^(?P<base>https?://[^/]+)"
    r"(?P<prefix>(?:/[^/]+)*?)"
    r"/torznab/(?P<slug>[^/]+)/download/(?P<token>[^/]+?)(?:\.torrent)?$"
)


@dataclass(frozen=True)
class GrabarrResolved:
    """Outcome of a successful Grabarr pre-resolve.

    Drives the dispatcher's routing branch decision *and* gives
    the post-grab telemetry layer something to record (the
    resolved upstream URL or magnet, source, checksums).

    Slice 442 — ``internal_file_path`` carries the specific file
    inside a meta-torrent the operator picked (e.g., Minerva's
    ``./No-Intro/.../Crash 3 (Europe).zip``). Romarr threads it
    into qBit's filePrio so the right file gets priority=1
    instead of token-overlap-scoring possibly preferring an
    unrelated release that happened to share parent-dir tokens.
    """

    method: str            # "http_direct" | "torrent_magnet"
    candidate: Candidate   # possibly mutated (magnet URL substituted)
    indexer_pin: int | None
    raw: dict[str, Any]    # the full resolve response — checksums etc.
    internal_file_path: str | None = None


class GrabarrPreResolveError(RuntimeError):
    """Raised when the pre-resolve HTTP call fails or returns a
    response Romarr can't act on. The grab path catches this and
    surfaces a structured failure ``DispatchOutcome``."""


async def maybe_pre_resolve(
    *,
    candidate: Candidate,
    indexer_row: Indexer | None,
    db: AsyncSession,
    timeout_seconds: float = 30.0,
) -> tuple[Candidate, int | None, GrabarrResolved | None]:
    """Pre-resolve for grabarr indexers; passthrough for everyone else.

    Returns the (possibly rewritten) candidate, the indexer pin to
    feed into ``dispatch_winner``, and an optional
    :class:`GrabarrResolved` snapshot when a grabarr indexer was
    hit. Callers that get ``None`` for the snapshot can dispatch
    exactly as before.
    """
    pin = indexer_row.download_client_id if indexer_row is not None else None
    if indexer_row is None or indexer_row.implementation != "grabarr":
        return candidate, pin, None

    if indexer_row.api_key_encrypted is None:
        raise GrabarrPreResolveError(
            f"grabarr indexer {indexer_row.id} has no apikey configured"
        )
    apikey = decrypt(indexer_row.api_key_encrypted).decode("utf-8")

    payload = await fetch_resolve(
        url=candidate.download_url,
        apikey=apikey,
        timeout_seconds=timeout_seconds,
    )
    method = payload.get("method")

    if method == "http_direct":
        snap = GrabarrResolved(
            method=method,
            candidate=candidate,
            indexer_pin=pin,
            raw=payload,
        )
        return candidate, pin, snap

    if method == "torrent_magnet":
        magnet = payload.get("magnet_uri")
        if not isinstance(magnet, str) or not magnet.startswith("magnet:"):
            raise GrabarrPreResolveError(
                f"resolve returned torrent_magnet without a usable magnet_uri "
                f"(got {magnet!r})"
            )
        # Pydantic models are frozen-ish; model_copy with ``update`` is the
        # supported clone-with-mutation path.
        rewritten = candidate.model_copy(update={"download_url": magnet})
        # Slice 442 — surface the adapter-supplied internal file
        # path so the qBit narrowing layer picks the exact file
        # the operator chose, not a token-overlap "best match"
        # that may include unrelated releases sitting in the
        # same meta-torrent folder.
        internal = payload.get("internal_file_path")
        if not isinstance(internal, str) or not internal:
            internal = None
        snap = GrabarrResolved(
            method=method,
            candidate=rewritten,
            indexer_pin=None,  # let routing pick by capability + priority
            raw=payload,
            internal_file_path=internal,
        )
        return rewritten, None, snap

    raise GrabarrPreResolveError(
        f"unsupported resolve method {method!r} — check Grabarr "
        "protocol_version (Romarr speaks 1)"
    )


async def fetch_resolve(
    *, url: str, apikey: str, timeout_seconds: float = 30.0
) -> dict[str, Any]:
    """Raw GET against the indexer's ``/resolve``. Stateless helper —
    no DB, no clients; the dispatcher uses this so it doesn't need
    to instantiate the full :class:`GrabarrDirectClient` just to
    learn the method."""
    m = _TORZNAB_DOWNLOAD_RE.match(url)
    if m is None:
        raise GrabarrPreResolveError(
            f"grabarr indexer download URL does not match the expected "
            f"shape: {url!r}"
        )
    base = m.group("base") + (m.group("prefix") or "")
    slug = m.group("slug")
    token = m.group("token")
    resolve_url = f"{base}/romarr/{slug}/api/v1/resolve/{token}"

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            resp = await client.get(
                resolve_url,
                headers={"Authorization": f"Bearer {apikey}"},
            )
    except httpx.HTTPError as exc:
        raise GrabarrPreResolveError(
            f"network failure reaching {resolve_url}: {exc}"
        ) from exc

    if resp.status_code == 401:
        raise GrabarrPreResolveError(
            "Grabarr rejected the apikey on /resolve — check the indexer's "
            "apikey vs the operator's profile"
        )
    if resp.status_code == 403:
        raise GrabarrPreResolveError(
            "Grabarr returned 403 on /resolve — the token belongs to a "
            "different profile than the indexer was registered for"
        )
    if resp.status_code == 404:
        raise GrabarrPreResolveError(
            "Grabarr returned 404 — the token has expired (default TTL "
            "24 h) or never existed; re-run the search and grab again"
        )
    if resp.status_code != 200:
        raise GrabarrPreResolveError(
            f"unexpected /resolve status {resp.status_code}: {resp.text[:200]}"
        )
    return resp.json()


async def filter_candidates_for_magnet(
    *, candidates: list[RoutingCandidate], db: AsyncSession
) -> list[RoutingCandidate]:
    """Drop every ``grabarr_direct`` row from the routing pool.

    Called only when the pre-resolve produced a magnet so the
    routing engine picks the operator's qBit (or other torrent
    client) by priority. The grabarr_direct row declares
    ``supports_torrents = True`` for the http_direct flow, but its
    ``add_torrent`` deliberately rejects magnet sources — silently
    leaving it in the pool would let routing pick it and produce a
    confusing late-stage ``ValueError`` instead of a clean
    ``no_eligible_client`` when qBit isn't configured.
    """
    grabarr_ids = set(
        (
            await db.execute(
                select(DownloadClient.id).where(
                    DownloadClient.type == ClientType.GRABARR_DIRECT.value
                )
            )
        )
        .scalars()
        .all()
    )
    if not grabarr_ids:
        return candidates
    return [c for c in candidates if c.id not in grabarr_ids]


__all__ = [
    "GrabarrPreResolveError",
    "GrabarrResolved",
    "fetch_resolve",
    "filter_candidates_for_magnet",
    "maybe_pre_resolve",
]
