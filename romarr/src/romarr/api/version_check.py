"""GitHub release version checker.

Exposes ``check_latest_release()`` — fetches the ``latest`` release from
the configured GitHub repo, compares against the running version, and
caches the result in-process for one hour so a full-page-load Settings
UI doesn't hammer the GitHub API (60 req/h unauthenticated).

The comparison uses tuple-of-ints on the semver core, tolerating a
leading ``v``. Pre-release / build metadata (``-rc.1``, ``+meta``) is
stripped before comparison so ``0.14.31`` vs ``0.14.31-rc.1`` compares
equal — deployed pre-releases don't nag operators about "updates" that
are the same version.

Failure modes are quiet: GitHub 429 / timeout / DNS failure → returns
``latest=None`` and ``error`` string, never raises. The UI shows the
current version alone in that case.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

_LOG = logging.getLogger(__name__)

_CACHE_TTL = timedelta(hours=1)
_REQUEST_TIMEOUT = 5.0

_SEMVER_CORE_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)")


@dataclass(frozen=True)
class VersionInfo:
    current: str
    latest: str | None
    update_available: bool
    release_url: str | None
    published_at: str | None
    error: str | None = None


def _semver_tuple(version: str) -> tuple[int, int, int] | None:
    """Parse ``0.14.31`` / ``v0.14.31`` / ``0.14.31-rc.1`` → (0, 14, 31).

    Returns None for non-semver strings so unknown formats fall back to
    string equality (safest — never claims an update when comparison is
    ambiguous).
    """
    m = _SEMVER_CORE_RE.match(version.strip())
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def _is_update_available(current: str, latest: str) -> bool:
    cur = _semver_tuple(current)
    lat = _semver_tuple(latest)
    if cur is None or lat is None:
        return current.lstrip("v") != latest.lstrip("v")
    return lat > cur


_cache: dict[str, tuple[datetime, VersionInfo]] = {}


async def check_latest_release(
    *,
    current_version: str,
    github_repo: str,
    force: bool = False,
) -> VersionInfo:
    """Return :class:`VersionInfo` for ``github_repo`` vs ``current_version``.

    ``github_repo`` is ``owner/repo`` (e.g. ``sharkhunterr/romarr``). Set
    ``force=True`` to bypass the 1-hour in-process cache — the operator's
    "Check for updates now" button should pass this.
    """
    cache_key = f"{github_repo}::{current_version}"
    now = datetime.now(UTC)
    if not force:
        cached = _cache.get(cache_key)
        if cached is not None and now - cached[0] < _CACHE_TTL:
            return cached[1]

    url = f"https://api.github.com/repos/{github_repo}/releases/latest"
    try:
        async with httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT,
            headers={"Accept": "application/vnd.github+json"},
        ) as client:
            resp = await client.get(url)
    except (httpx.HTTPError, asyncio.TimeoutError) as exc:
        info = VersionInfo(
            current=current_version,
            latest=None,
            update_available=False,
            release_url=None,
            published_at=None,
            error=f"github fetch failed: {exc}",
        )
        _cache[cache_key] = (now, info)
        return info

    if resp.status_code == 404:
        info = VersionInfo(
            current=current_version,
            latest=None,
            update_available=False,
            release_url=f"https://github.com/{github_repo}/releases",
            published_at=None,
            error="no published release yet",
        )
        _cache[cache_key] = (now, info)
        return info

    if resp.status_code >= 400:
        info = VersionInfo(
            current=current_version,
            latest=None,
            update_available=False,
            release_url=f"https://github.com/{github_repo}/releases",
            published_at=None,
            error=f"github HTTP {resp.status_code}",
        )
        _cache[cache_key] = (now, info)
        return info

    try:
        payload: dict[str, Any] = resp.json()
    except ValueError as exc:
        info = VersionInfo(
            current=current_version,
            latest=None,
            update_available=False,
            release_url=None,
            published_at=None,
            error=f"github body not JSON: {exc}",
        )
        _cache[cache_key] = (now, info)
        return info

    tag = str(payload.get("tag_name") or "").strip()
    if not tag:
        info = VersionInfo(
            current=current_version,
            latest=None,
            update_available=False,
            release_url=payload.get("html_url"),
            published_at=None,
            error="latest release has no tag_name",
        )
        _cache[cache_key] = (now, info)
        return info

    latest = tag.lstrip("v")
    info = VersionInfo(
        current=current_version,
        latest=latest,
        update_available=_is_update_available(current_version, latest),
        release_url=payload.get("html_url")
        or f"https://github.com/{github_repo}/releases/tag/{tag}",
        published_at=payload.get("published_at"),
        error=None,
    )
    _cache[cache_key] = (now, info)
    return info


__all__ = ["VersionInfo", "check_latest_release"]
