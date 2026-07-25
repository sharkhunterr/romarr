"""Fetch platform-pack YAML bodies from remote HTTP/GitHub sources.

Two URL shapes supported :

  * **raw** — the URL points directly at a YAML file. Any HTTPS
    URL that ends in ``.yaml`` / ``.yml`` qualifies. Fetched as-is.

  * **github_dir** — the URL points at a GitHub directory. Two
    intake shapes accepted, both normalised to the GitHub REST
    contents API before walking :

    - ``https://github.com/{owner}/{repo}/tree/{branch}/{path…}``
    - ``https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={branch}``

    The walker lists the directory, filters to ``*.yaml`` / ``*.yml``
    entries and fetches each child via its ``download_url``.

Kept dependency-light : `httpx` only, no `PyGithub`. Public
repositories only for the MVP (no auth token) — private repos can
land later behind an ``auth_token`` column on ``pack_sources``.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx

_TIMEOUT_SECONDS = 15.0
_MAX_YAML_BYTES = 2 * 1024 * 1024  # 2 MiB per pack — packs are text/YAML
_MAX_DIR_ENTRIES = 200

_TREE_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/tree/"
    r"(?P<branch>[^/]+)/(?P<path>.+?)/?$"
)
_YAML_SUFFIXES = (".yaml", ".yml")

_logger = logging.getLogger(__name__)


class RemotePackError(RuntimeError):
    """A single-URL fetch or directory walk failed."""


@dataclass(frozen=True, slots=True)
class RemotePackYaml:
    """One YAML body pulled from a remote source."""

    filename: str
    """Human-facing name — the leaf path or the URL basename."""
    source_url: str
    """The exact URL the body came from (stamped into the audit trail)."""
    body: bytes


def classify_url(url: str) -> str:
    """Return ``"raw"`` or ``"github_dir"`` for ``url``.

    Priority : anything that looks like a GitHub ``/tree/`` link or
    the REST contents endpoint is a directory ; otherwise if it ends
    in a YAML suffix it's raw. Anything else defaults to ``raw`` and
    the sync will surface an HTTP-content-type error at fetch time.
    """
    lower = url.lower().split("?", 1)[0].split("#", 1)[0]
    if _TREE_RE.match(url):
        return "github_dir"
    if "api.github.com/repos/" in lower and "/contents/" in lower:
        return "github_dir"
    if lower.endswith(_YAML_SUFFIXES):
        return "raw"
    # Ambiguous — default raw; the fetcher will error if the response
    # isn't valid YAML, and the operator can flip ``kind`` manually.
    return "raw"


def _tree_url_to_contents_api(url: str) -> str:
    """Rewrite ``github.com/.../tree/{branch}/{path}`` → REST contents."""
    m = _TREE_RE.match(url)
    if not m:
        raise RemotePackError(f"not a github tree URL: {url!r}")
    owner, repo, branch, path = (
        m.group("owner"),
        m.group("repo"),
        m.group("branch"),
        m.group("path"),
    )
    return (
        f"https://api.github.com/repos/{owner}/{repo}/contents/"
        f"{path}?ref={branch}"
    )


async def _fetch_raw(client: httpx.AsyncClient, url: str) -> bytes:
    resp = await client.get(url)
    if resp.status_code >= 400:
        raise RemotePackError(
            f"HTTP {resp.status_code} fetching {url!r}: "
            f"{resp.text[:200] if resp.text else resp.reason_phrase}"
        )
    body = resp.content
    if len(body) > _MAX_YAML_BYTES:
        raise RemotePackError(
            f"{url!r} exceeds max pack size ({len(body)} > {_MAX_YAML_BYTES} B)"
        )
    return body


async def fetch_from_source(url: str, kind: str) -> list[RemotePackYaml]:
    """Pull the YAML bodies advertised by a ``PackSource`` row.

    Returns one entry per YAML found. Raises :class:`RemotePackError`
    on hard failures (network, HTTP 4xx/5xx, malformed listing). The
    caller decides whether a failure marks the whole source
    ``error`` or just skips the affected file.
    """
    headers = {
        "Accept": "application/vnd.github+json, text/plain, */*",
        "User-Agent": "romarr-pack-source-fetcher/1",
    }
    async with httpx.AsyncClient(
        timeout=_TIMEOUT_SECONDS, headers=headers, follow_redirects=True
    ) as client:
        if kind == "raw":
            body = await _fetch_raw(client, url)
            filename = url.rstrip("/").rsplit("/", 1)[-1] or "pack.yaml"
            return [RemotePackYaml(filename=filename, source_url=url, body=body)]

        if kind != "github_dir":
            raise RemotePackError(f"unknown source kind {kind!r}")

        api_url = (
            _tree_url_to_contents_api(url) if _TREE_RE.match(url) else url
        )
        listing_resp = await client.get(api_url)
        if listing_resp.status_code >= 400:
            raise RemotePackError(
                f"HTTP {listing_resp.status_code} listing {api_url!r}: "
                f"{listing_resp.text[:200]}"
            )
        try:
            entries: list[dict[str, Any]] = listing_resp.json()
        except ValueError as e:
            raise RemotePackError(
                f"listing {api_url!r} returned non-JSON: {e}"
            ) from e
        if not isinstance(entries, list):
            raise RemotePackError(
                f"listing {api_url!r} not a directory (got a single-file response)"
            )
        if len(entries) > _MAX_DIR_ENTRIES:
            raise RemotePackError(
                f"directory {api_url!r} lists {len(entries)} entries "
                f"(max {_MAX_DIR_ENTRIES}) — refusing to walk"
            )

        yamls: list[RemotePackYaml] = []
        for entry in entries:
            if entry.get("type") != "file":
                continue
            name = entry.get("name", "")
            if not name.lower().endswith(_YAML_SUFFIXES):
                continue
            download = entry.get("download_url")
            if not download:
                _logger.warning(
                    "pack source listing entry %r missing download_url", name
                )
                continue
            try:
                body = await _fetch_raw(client, download)
            except RemotePackError as e:
                # Skip the bad file, keep walking — the caller will
                # report `partial` if any file failed.
                _logger.warning("skipping %r during walk: %s", name, e)
                continue
            yamls.append(
                RemotePackYaml(filename=name, source_url=download, body=body)
            )
        return yamls


__all__ = [
    "RemotePackError",
    "RemotePackYaml",
    "classify_url",
    "fetch_from_source",
]
