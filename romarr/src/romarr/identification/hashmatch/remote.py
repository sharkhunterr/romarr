"""Hasheous + PlayMatch HTTP-backed cascade backends.

Both services expose simple JSON APIs keyed by hash. Both default
to anonymous public access (CL003 / FR-026a); the operator may set
``ROMARR_HASHEOUS_TOKEN`` / ``ROMARR_PLAYMATCH_TOKEN`` to send an
``Authorization: Bearer …`` header.

Endpoints used:
- Hasheous:  ``GET <base>/v1/lookup/{sha1}``
- PlayMatch: ``GET <base>/api/v1/match?sha1={sha1}``

The exact response shapes are conservative — both projects evolve and
the cascade is forgiving about extra keys (``extra='ignore'``-style
parsing). When either endpoint returns 404 the result is an empty
``entries`` tuple (no error).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from romarr.identification.hashmatch.types import (
    BackendName,
    HashLookupResult,
    RemoteHashEntry,
)

if TYPE_CHECKING:
    from romarr.config import Settings


class HasheousBackend:
    """Hasheous remote hash-match backend."""

    name = BackendName.HASHEOUS

    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.AsyncClient | None = None,
        timeout: float = 5.0,
    ) -> None:
        self._base_url = settings.hasheous_base_url.rstrip("/")
        self._token = settings.hasheous_token or None
        self._timeout = timeout
        self._client = client

    async def lookup_cross_refs(
        self,
        *,
        sha1: str | None = None,
        md5: str | None = None,
        crc32: str | None = None,
    ) -> dict[str, str | None]:
        """Slice 414 — Hasheous cross-reference lookup.

        Posts a ``/api/v1/Lookup/ByHash`` request with whatever
        hash the caller has and parses the response's
        ``metadata`` array for the IGDB / RetroAchievements /
        TheGamesDB / MobyGames immutable IDs. Returns a dict
        keyed on Romarr's metadata provider names:

            {
                "igdb": "1234",            # or None
                "retroachievements": "...",
                "mobygames": "...",
                "tgdb": "...",
            }

        Empty values when Hasheous doesn't know the hash (404)
        or the response doesn't carry that source. Mirrors
        RomM's ``HasheousHandler.lookup_rom`` shape.
        """
        if not (sha1 or md5 or crc32):
            return {}
        url = f"{self._base_url}/v1/Lookup/ByHash"
        body: dict[str, str] = {}
        if md5:
            body["mD5"] = md5.lower()
        if sha1:
            body["shA1"] = sha1.lower()
        if crc32:
            body["crc"] = crc32.lower()
        params = {
            "returnAllSources": "true",
            "returnFields": "Metadata",
        }
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._token:
            headers["X-API-Key"] = self._token

        try:
            if self._client is not None:
                response = await self._client.post(
                    url,
                    params=params,
                    json=body,
                    headers=headers,
                    timeout=self._timeout,
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(
                        url, params=params, json=body, headers=headers
                    )
        except httpx.HTTPError:
            return {}
        if response.status_code != 200:
            return {}
        try:
            payload = response.json()
        except ValueError:
            return {}
        if not isinstance(payload, dict):
            return {}
        metadata = payload.get("metadata") or []
        if not isinstance(metadata, list):
            return {}
        out: dict[str, str | None] = {
            "igdb": None,
            "retroachievements": None,
            "tgdb": None,
            "mobygames": None,
        }
        for meta in metadata:
            if not isinstance(meta, dict):
                continue
            source = str(meta.get("source") or "").lower()
            immutable_id = meta.get("immutableId")
            if immutable_id is None:
                continue
            if source == "igdb":
                out["igdb"] = str(immutable_id)
            elif source in ("retroachievements", "ra"):
                out["retroachievements"] = str(immutable_id)
            elif source in ("thegamesdb", "tgdb"):
                out["tgdb"] = str(immutable_id)
            elif source in ("mobygames", "moby"):
                out["mobygames"] = str(immutable_id)
        return out

    async def lookup_sha1(
        self, *, platform_id: int, sha1: str
    ) -> HashLookupResult:
        url = f"{self._base_url}/v1/lookup/{sha1.lower()}"
        headers: dict[str, str] = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        try:
            if self._client is not None:
                response = await self._client.get(
                    url, headers=headers, timeout=self._timeout
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            return HashLookupResult(
                backend=self.name, error=f"http_error:{type(exc).__name__}"
            )

        if response.status_code == 404:
            return HashLookupResult(backend=self.name)
        if response.status_code == 429:
            # FR-026a/FR-027: 429 counts as a circuit-breaker failure.
            return HashLookupResult(backend=self.name, error="rate_limited:429")
        if response.status_code >= 500:
            return HashLookupResult(
                backend=self.name, error=f"http_status:{response.status_code}"
            )
        if response.status_code != 200:
            return HashLookupResult(
                backend=self.name, error=f"http_status:{response.status_code}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            return HashLookupResult(
                backend=self.name, error=f"bad_json:{exc!s}"
            )

        return HashLookupResult(
            backend=self.name,
            entries=tuple(_parse_hasheous_entries(payload)),
        )


class PlayMatchBackend:
    """PlayMatch remote hash-match backend."""

    name = BackendName.PLAYMATCH

    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.AsyncClient | None = None,
        timeout: float = 5.0,
    ) -> None:
        self._base_url = settings.playmatch_base_url.rstrip("/")
        self._token = settings.playmatch_token or None
        self._timeout = timeout
        self._client = client

    async def lookup_sha1(
        self, *, platform_id: int, sha1: str
    ) -> HashLookupResult:
        url = f"{self._base_url}/api/v1/match"
        params = {"sha1": sha1.lower()}
        headers: dict[str, str] = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        try:
            if self._client is not None:
                response = await self._client.get(
                    url, params=params, headers=headers, timeout=self._timeout
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.get(url, params=params, headers=headers)
        except httpx.HTTPError as exc:
            return HashLookupResult(
                backend=self.name, error=f"http_error:{type(exc).__name__}"
            )

        if response.status_code == 404:
            return HashLookupResult(backend=self.name)
        if response.status_code == 429:
            return HashLookupResult(backend=self.name, error="rate_limited:429")
        if response.status_code >= 500:
            return HashLookupResult(
                backend=self.name, error=f"http_status:{response.status_code}"
            )
        if response.status_code != 200:
            return HashLookupResult(
                backend=self.name, error=f"http_status:{response.status_code}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            return HashLookupResult(
                backend=self.name, error=f"bad_json:{exc!s}"
            )

        return HashLookupResult(
            backend=self.name,
            entries=tuple(_parse_playmatch_entries(payload)),
        )


# ---------------------------------------------------------------------------
# Response parsers (conservative — extra keys ignored)
# ---------------------------------------------------------------------------


def _parse_hasheous_entries(payload: object) -> list[RemoteHashEntry]:
    """Parse a Hasheous JSON response into RemoteHashEntry records.

    Hasheous returns either a single object or a list of matches.
    """
    if isinstance(payload, dict):
        return [_remote_entry_from_dict(payload, default_source="hasheous")]
    if isinstance(payload, list):
        return [
            _remote_entry_from_dict(item, default_source="hasheous")
            for item in payload
            if isinstance(item, dict)
        ]
    return []


def _parse_playmatch_entries(payload: object) -> list[RemoteHashEntry]:
    """Parse a PlayMatch JSON response into RemoteHashEntry records."""
    if isinstance(payload, dict):
        # PlayMatch wraps results under ``matches`` typically.
        matches = payload.get("matches")
        if isinstance(matches, list):
            return [
                _remote_entry_from_dict(item, default_source="playmatch")
                for item in matches
                if isinstance(item, dict)
            ]
        return [_remote_entry_from_dict(payload, default_source="playmatch")]
    if isinstance(payload, list):
        return [
            _remote_entry_from_dict(item, default_source="playmatch")
            for item in payload
            if isinstance(item, dict)
        ]
    return []


def _remote_entry_from_dict(item: dict[str, object], *, default_source: str) -> RemoteHashEntry:
    """Translate a JSON dict into a :class:`RemoteHashEntry`.

    Best-effort extraction — missing keys yield ``None``. The
    ``source`` field falls back to ``default_source`` when the remote
    didn't supply one.
    """
    return RemoteHashEntry(
        source=str(item.get("source") or default_source),
        name=str(item.get("name") or item.get("game_name") or ""),
        crc32=_str_or_none(item.get("crc32") or item.get("crc")),
        md5=_str_or_none(item.get("md5")),
        sha1=_str_or_none(item.get("sha1")),
        size_bytes=_int_or_none(item.get("size_bytes") or item.get("size")),
    )


def _str_or_none(value: object) -> str | None:
    if value is None:
        return None
    return str(value).lower() or None


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):  # bool is an int subclass — guard explicitly
        return int(value)
    if isinstance(value, (int, float, str, bytes, bytearray)):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return None
