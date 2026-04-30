"""Pre-loaded library state consumed by the pure pipeline.

Per the plan's preload pattern: the round orchestrator reads
profiles, custom formats, blocklist, monitored games / releases,
DAT lookup, and platform-format size bounds ONCE per round, then
hands them to the pipeline as frozen value objects. The pipeline
itself never re-reads the database — that's the FR-016 purity
invariant the consumer specs depend on.

Why standalone Pydantic models (not the SQLAlchemy rows)? Two
reasons:

  1. ``frozen=True`` means evaluators can rely on inputs not
     mutating mid-call. SQLAlchemy rows are NOT frozen — they're
     attribute-settable, and a stray ``setattr`` mid-pipeline
     would silently change the answer.
  2. The pipeline tests need to construct fake state without
     spinning up a session. Pydantic ``BaseModel(...)`` is one
     line; building a complete SQLAlchemy graph is a session
     fixture per test.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from romarr.domain.enums import DumpStatus, NamingConvention
from romarr.indexers.types import SearchResult

_FROZEN = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class MonitoredGame(BaseModel):
    """Slim projection of a Game row that the search pipeline reads."""

    model_config = _FROZEN

    id: int
    platform_id: int
    title: str
    sort_title: str = ""
    alt_names: tuple[str, ...] = ()
    year: int | None = None
    publisher: str = ""
    monitored: bool = True


class MonitoredRelease(BaseModel):
    """Slim projection of a Release row that the search pipeline reads."""

    model_config = _FROZEN

    id: int
    game_id: int
    region: str = ""
    revision: str = ""
    languages: tuple[str, ...] = ()
    dump_status: DumpStatus = DumpStatus.UNKNOWN
    naming_convention: NamingConvention = NamingConvention.UNKNOWN
    file_format: str = ""
    monitored: bool = True


class PlatformFormatBounds(BaseModel):
    """Per-format size bounds for one platform.

    ``None`` on either bound means "no limit" — releases are accepted
    in that direction. Both ``None`` is acceptable too (no bounds
    declared on the platform pack); the pipeline skips the size gate.
    """

    model_config = _FROZEN

    platform_id: int
    extension: str
    min_size_bytes: int | None = None
    max_size_bytes: int | None = None


class BlocklistEntry(BaseModel):
    """One blocklist row in pipeline-friendly shape."""

    model_config = _FROZEN

    indexer_id: int | None = None
    indexer_guid: str = ""
    hash_sha1: str = ""
    hash_crc32: str = ""
    reason: str


_DatOutcome = Literal["verified", "hack", "none"]
"""DAT-match boost-or-flag outcome consumed by the pipeline."""


# Callable signature: a pure function that maps (sha1, crc32) → outcome.
# The orchestrator wires this against the foundation's DAT lookup
# helper before calling the pipeline.
DatLookup = Callable[[str | None, str | None], _DatOutcome]


class IndexerMeta(BaseModel):
    """Per-indexer metadata the pipeline + tie-breaker consult."""

    model_config = _FROZEN

    id: int
    priority: int = 25
    min_seeders: int = 1


class LibraryState(BaseModel):
    """Frozen snapshot of everything the pipeline reads about state.

    Built once per search round; handed to the pipeline by reference.
    The orchestrator is responsible for keeping the snapshot's lifetime
    scoped to a single round so concurrent rounds don't see each
    other's preload.
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    monitored_games: tuple[MonitoredGame, ...] = ()
    monitored_releases: tuple[MonitoredRelease, ...] = ()
    platform_format_bounds: tuple[PlatformFormatBounds, ...] = ()
    blocklist: tuple[BlocklistEntry, ...] = Field(default_factory=tuple)
    indexer_meta: tuple[IndexerMeta, ...] = ()


__all__ = [
    "BlocklistEntry",
    "DatLookup",
    "IndexerMeta",
    "LibraryState",
    "MonitoredGame",
    "MonitoredRelease",
    "PlatformFormatBounds",
    "SearchResult",
]
