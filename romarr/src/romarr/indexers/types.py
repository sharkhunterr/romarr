"""Value types for the indexer feature.

Pure-Python (no DB, no I/O); consumed by the parser, the client, and
the future Search-Decision spec.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Pydantic v2 introspects type annotations at runtime to build the
# model, so NamingConvention MUST be a live import.
from romarr.domain.enums import DumpStatus, NamingConvention  # noqa: TC001


class FieldProvenance(StrEnum):
    """Where a parsed metadata field came from."""

    TORZNAB = "torznab"  # standard ``torznab:attr`` namespace
    GRABARR = "grabarr"  # extended ``grabarr:*`` namespace
    FILENAME = "filename"  # foundation filename-parser fallback


class DatSource(StrEnum):
    """The DAT family a result claims to come from.

    Mirrors the foundation's stored values on ``Dump.dat_source``.
    Spec 001's CL001 cross-DAT-precedence ordering: No-Intro >
    Redump > TOSEC.
    """

    NO_INTRO = "no-intro"
    REDUMP = "redump"
    TOSEC = "tosec"
    GOODTOOLS = "goodtools"
    UNKNOWN = "unknown"


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ParsedTorznabAttr(_Base):
    """One attribute extracted from a ``<torznab:attr>`` /
    ``<grabarr:attr>`` element."""

    name: str
    value: str
    provenance: FieldProvenance


class IndexerCapabilities(_Base):
    """Parsed ``t=caps`` response."""

    server: str | None = None
    # ``searching`` mirrors the Newznab caps shape:
    # ``{searchType: {"available": bool, "supportedParams": [...]}}``.
    searching: dict[str, dict[str, Any]] = Field(default_factory=dict)
    categories: list[int] = Field(default_factory=list)
    extended_attrs_supported: list[str] = Field(default_factory=list)


class SearchResult(_Base):
    """Canonical Romarr-side projection of a single Newznab/Torznab item."""

    indexer_id: int
    guid: str
    title: str
    link: str
    size_bytes: int | None = None
    seeders: int | None = None
    peers: int | None = None
    files: int | None = None
    info_hash: str | None = None
    magnet_url: str | None = None
    categories: list[int] = Field(default_factory=list)
    publish_date: datetime | None = None

    region: str | None = None
    region_provenance: FieldProvenance | None = None
    languages: list[str] = Field(default_factory=list)
    languages_provenance: FieldProvenance | None = None
    revision: str | None = None
    revision_provenance: FieldProvenance | None = None
    dump_tags: list[str] = Field(default_factory=list)
    dump_tags_provenance: FieldProvenance | None = None
    dump_status: DumpStatus | None = None
    dump_status_provenance: FieldProvenance | None = None
    hash_sha1: str | None = None
    hash_sha1_provenance: FieldProvenance | None = None
    hash_crc32: str | None = None
    hash_crc32_provenance: FieldProvenance | None = None
    naming_convention: NamingConvention | None = None
    naming_convention_provenance: FieldProvenance | None = None
    dat_source: DatSource | None = None
    dat_source_provenance: FieldProvenance | None = None
    file_format: str | None = None
    file_format_provenance: FieldProvenance | None = None


class RssResult(_Base):
    """Outcome of one ``t=rss`` poll."""

    indexer_id: int
    items: list[SearchResult] = Field(default_factory=list)
    fetched_at: datetime
    elapsed_ms: int


HealthCategory = Literal[
    "protocol",
    "auth",
    "rate_limit",
    "circuit_open",
    "connectivity",
    "parser",
]


class IndexerHealthIssue(_Base):
    """Something went wrong with one indexer.

    Consumed by the Notifications spec's health producer; tells the
    operator UI which indexer is unhealthy and why."""

    indexer_id: int
    indexer_name: str
    category: HealthCategory
    message: str
    occurred_at: datetime
