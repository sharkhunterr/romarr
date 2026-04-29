"""Shared types for the hash-match cascade."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from romarr.domain.enums import DumpStatus


class BackendName(StrEnum):
    """Identifier of a hash-match backend."""

    LOCAL = "local"
    HASHEOUS = "hasheous"
    PLAYMATCH = "playmatch"


@dataclass(frozen=True, slots=True)
class RemoteHashEntry:
    """One match record returned by a remote backend.

    Shape matches the DB-side ``DatEntry`` enough that the merger and
    the cross-DAT precedence resolver can treat local + remote
    matches uniformly. Remote entries don't have a database id, so
    callers wanting to persist them route through :class:`DatManager`.
    """

    source: str
    name: str
    crc32: str | None = None
    md5: str | None = None
    sha1: str | None = None
    size_bytes: int | None = None
    status: DumpStatus = DumpStatus.VERIFIED


@dataclass(frozen=True, slots=True)
class HashLookupResult:
    """Outcome of a single backend's lookup.

    ``error`` is populated only on failure; on circuit-open the
    backend short-circuits with ``error="circuit_open"``.
    """

    backend: BackendName
    entries: tuple[RemoteHashEntry, ...] = ()
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None
