"""HashMatchCascade — parallel local + Hasheous + PlayMatch lookups.

FR-026: query the three backends in parallel.
FR-027: each backend is guarded by its own circuit breaker.
FR-028: when both remotes are down, the local DAT cache continues to serve.
CL001 / FR-020a: when a single hash matches multiple sources, apply the
fixed authority order **No-Intro > Redump > TOSEC > GoodTools >
Hasheous > PlayMatch > custom**.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

from romarr.identification.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
)
from romarr.identification.dat.manager import DAT_AUTHORITY_ORDER
from romarr.identification.hashmatch.types import (
    BackendName,
    HashLookupResult,
    RemoteHashEntry,
)


class _Backend(Protocol):
    """Structural type every cascade backend conforms to."""

    name: BackendName

    async def lookup_sha1(
        self, *, platform_id: int, sha1: str
    ) -> HashLookupResult: ...


@dataclass(frozen=True, slots=True)
class CascadeMatch:
    """Merged outcome of a cascade query.

    ``winner`` is the highest-authority entry across all backends per
    CL001. ``losers`` contains every other matching entry. ``backend_status``
    maps each backend to its outcome string for diagnostics:
    ``"ok"`` / ``"empty"`` / ``"<error>"`` / ``"circuit_open"``.
    """

    winner: RemoteHashEntry | None
    losers: tuple[RemoteHashEntry, ...]
    backend_status: dict[BackendName, str]


class HashMatchCascade:
    """Coordinates the three hash-match backends in parallel."""

    def __init__(
        self,
        backends: list[_Backend],
        *,
        breakers: dict[BackendName, CircuitBreaker] | None = None,
    ) -> None:
        if not backends:
            raise ValueError("HashMatchCascade requires at least one backend")
        self._backends = list(backends)
        self._breakers: dict[BackendName, CircuitBreaker] = dict(breakers or {})
        for backend in self._backends:
            self._breakers.setdefault(
                backend.name, CircuitBreaker(name=str(backend.name))
            )

    async def lookup_sha1(
        self, *, platform_id: int, sha1: str
    ) -> CascadeMatch:
        """Query every backend in parallel and merge by FR-020a authority."""
        sha1 = sha1.lower()
        tasks = [
            self._call_backend(backend, platform_id=platform_id, sha1=sha1)
            for backend in self._backends
        ]
        results = await asyncio.gather(*tasks)

        backend_status: dict[BackendName, str] = {}
        all_entries: list[RemoteHashEntry] = []

        for backend, result in zip(self._backends, results, strict=True):
            if isinstance(result, BaseException):
                # Should not happen — _call_backend swallows exceptions
                # and returns a HashLookupResult.
                backend_status[backend.name] = f"unhandled:{type(result).__name__}"
                continue
            if not result.ok:
                backend_status[backend.name] = result.error or "error"
                continue
            backend_status[backend.name] = "ok" if result.entries else "empty"
            all_entries.extend(result.entries)

        winner, losers = _resolve_authority(all_entries)
        return CascadeMatch(
            winner=winner,
            losers=losers,
            backend_status=backend_status,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _call_backend(
        self,
        backend: _Backend,
        *,
        platform_id: int,
        sha1: str,
    ) -> HashLookupResult:
        """Run a backend through its circuit breaker.

        Always returns a :class:`HashLookupResult` — exceptions from
        the breaker (CircuitOpenError) or the backend are translated
        into a structured ``error`` field so the caller can present
        them uniformly.
        """
        breaker = self._breakers[backend.name]

        async def _fn() -> HashLookupResult:
            return await backend.lookup_sha1(platform_id=platform_id, sha1=sha1)

        try:
            result = await breaker.call(_fn)
        except CircuitOpenError:
            return HashLookupResult(backend=backend.name, error="circuit_open")
        except Exception as exc:
            return HashLookupResult(
                backend=backend.name, error=f"backend_error:{type(exc).__name__}"
            )

        # Treat backend-level errors as circuit-breaker failures so a
        # repeatedly-failing service trips the breaker.
        if not result.ok:
            breaker.record_failure()
        return result


# ---------------------------------------------------------------------------
# Authority resolver (CL001 / FR-020a)
# ---------------------------------------------------------------------------


_AUTHORITY_RANK: dict[str, int] = {
    src: idx for idx, src in enumerate(DAT_AUTHORITY_ORDER)
}


def _resolve_authority(
    entries: list[RemoteHashEntry],
) -> tuple[RemoteHashEntry | None, tuple[RemoteHashEntry, ...]]:
    """Pick the highest-authority entry across every backend.

    Sort key: authority rank from ``DAT_AUTHORITY_ORDER``; ties broken
    by ``name`` (deterministic) so the same input always selects the
    same winner.
    """
    if not entries:
        return None, ()

    # Drop duplicates (same source + same SHA-1 from local + remote
    # both reporting it). We dedupe by ``(source, sha1, name)``.
    seen: dict[tuple[str, str | None, str], RemoteHashEntry] = {}
    for entry in entries:
        key = (entry.source, entry.sha1, entry.name)
        if key not in seen:
            seen[key] = entry

    sorted_entries = sorted(
        seen.values(),
        key=lambda e: (_AUTHORITY_RANK.get(e.source, 999), e.name),
    )
    return sorted_entries[0], tuple(sorted_entries[1:])
