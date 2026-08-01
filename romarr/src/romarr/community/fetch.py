"""HTTP fetch helper for community pack manifests and item bodies.

Keeps the network policy in one place: HTTPS-only, size cap,
timeout cap, single retry, no auth by default (matching the "no
GitHub token" ADR from the design discussion).
"""

from __future__ import annotations

import logging
from urllib.parse import urljoin

import httpx

_LOG = logging.getLogger(__name__)

_TIMEOUT = 10.0
_MAX_BODY_BYTES = 2 * 1024 * 1024  # 2 MiB per item
_UA = "romarr-community-sync/1"


class FetchError(RuntimeError):
    """Raised when a manifest or item body cannot be fetched."""


async def fetch_json(url: str) -> dict:
    """GET ``url`` and return the parsed JSON body.

    HTTPS-only, timeout ``_TIMEOUT``, body size capped at
    ``_MAX_BODY_BYTES``. Raises :class:`FetchError` with an
    operator-readable message on any failure.
    """
    if not url.lower().startswith("https://"):
        raise FetchError(f"only https:// URLs are accepted (got {url!r})")
    headers = {"User-Agent": _UA, "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(
            timeout=_TIMEOUT, headers=headers, follow_redirects=True
        ) as client:
            resp = await client.get(url)
    except (httpx.HTTPError, TimeoutError) as exc:
        raise FetchError(f"network error fetching {url}: {exc}") from exc

    if resp.status_code == 404:
        raise FetchError(f"manifest not found at {url} (HTTP 404)")
    if resp.status_code >= 400:
        raise FetchError(f"HTTP {resp.status_code} fetching {url}")

    if len(resp.content) > _MAX_BODY_BYTES:
        raise FetchError(
            f"body too large ({len(resp.content)} B > {_MAX_BODY_BYTES} B) "
            f"at {url}"
        )

    try:
        return resp.json()
    except ValueError as exc:
        raise FetchError(f"invalid JSON at {url}: {exc}") from exc


async def fetch_text(url: str) -> str:
    """GET ``url`` and return the body text (used by item fetch)."""
    if not url.lower().startswith("https://"):
        raise FetchError(f"only https:// URLs are accepted (got {url!r})")
    headers = {"User-Agent": _UA}
    try:
        async with httpx.AsyncClient(
            timeout=_TIMEOUT, headers=headers, follow_redirects=True
        ) as client:
            resp = await client.get(url)
    except (httpx.HTTPError, TimeoutError) as exc:
        raise FetchError(f"network error fetching {url}: {exc}") from exc

    if resp.status_code >= 400:
        raise FetchError(f"HTTP {resp.status_code} fetching {url}")
    if len(resp.content) > _MAX_BODY_BYTES:
        raise FetchError(
            f"body too large ({len(resp.content)} B > {_MAX_BODY_BYTES} B) "
            f"at {url}"
        )
    return resp.text


def resolve_item_url(manifest_url: str, item_path: str) -> str:
    """Resolve a manifest ``items[].path`` against the manifest URL.

    Uses :func:`urllib.parse.urljoin` — an absolute item URL wins
    over the manifest base, a relative one is appended after the
    last path segment of the manifest.
    """
    return urljoin(manifest_url, item_path)


__all__ = ["FetchError", "fetch_json", "fetch_text", "resolve_item_url"]
