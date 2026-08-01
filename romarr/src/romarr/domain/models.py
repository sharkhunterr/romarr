"""SQLAlchemy 2.0 ORM models for the foundation domain.

Nine tables per spec 001 FR-001:
- ``platform``, ``platform_format``, ``platform_naming_token``
- ``game``, ``release``, ``dump``
- ``dat_entry``, ``unidentified_dump``, ``platform_pack``

Conventions:
- Surrogate ``id`` primary keys (INTEGER) everywhere.
- Timezone-aware UTC timestamps via :class:`TimestampMixin`.
- ``JSON`` columns are driver-agnostic (no JSONB at MVP) so the same
  models work against SQLite and PostgreSQL.
- Cascade rules per FR-005, FR-002, and the Edge Cases:
  * Platform delete is RESTRICTED when Games attached.
  * Game delete cascades to Releases and Dumps.
  * Dump path is globally unique.
"""

from __future__ import annotations

# SQLAlchemy 2.0 introspects Mapped[...] annotations at class-creation
# time, so types referenced in those annotations MUST be importable at
# runtime — they cannot live behind TYPE_CHECKING.
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from romarr.domain.base import Base, TimestampMixin
from romarr.domain.enums import DumpStatus, NamingConvention


class Platform(Base, TimestampMixin):
    """A console or handheld system.

    Slugs are kebab-case, globally unique (FR-007). Platform Packs (spec
    003) populate this table; spec 001's migration seeds five MVP
    platforms (FR-009).
    """

    __tablename__ = "platform"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(32), nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String(64), nullable=True)
    release_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parent_platform_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("platform.id", ondelete="SET NULL"),
        nullable=True,
    )

    # External metadata provider IDs (filled in by Platform Packs).
    igdb_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    screenscraper_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mobygames_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    launchbox_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retroachievements_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Newznab category IDs for indexer searches (spec 004 consumes).
    newznab_category_ids: Mapped[list[int]] = mapped_column(
        JSON, nullable=False, default=list
    )

    # Slice 401 — operator-facing alias strings used by the
    # title-match (manual search) and filename-parser (importer)
    # paths so a release titled "Final Fantasy VII (PSX)" /
    # "(PS1)" / "(PlayStation)" all bind to the same Platform
    # row. Empty list when no aliases are configured; the slug +
    # short_name + name are always considered alongside.
    aliases: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )

    # Pack provenance (spec 003 populates).
    pack_source: Mapped[str] = mapped_column(
        String(16), nullable=False, default="builtin"
    )
    pack_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Migration 0043 — FK to the specific ``pack_sources`` row that
    # produced this platform (community-source provenance). Null for
    # legacy builtin rows or rows created before 0043.
    pack_source_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("pack_sources.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Free-form metadata (icon URL, theme color, etc.).
    extra_meta: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    # Relationships
    formats: Mapped[list[PlatformFormat]] = relationship(
        back_populates="platform",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    naming_tokens: Mapped[list[PlatformNamingToken]] = relationship(
        back_populates="platform",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    games: Mapped[list[Game]] = relationship(back_populates="platform")

    __table_args__ = (
        CheckConstraint(
            "pack_source IN ('builtin', 'community', 'user')",
            name="ck_platform_pack_source",
        ),
    )


class PlatformFormat(Base, TimestampMixin):
    """A file extension recognised for a Platform.

    Multiple formats per platform are common (e.g., NES has ``.nes`` +
    ``.fds`` + ``.unif``). Per-format size bounds let the search engine
    reject re-encodes that fall outside the expected range (FR per
    spec 007).
    """

    __tablename__ = "platform_format"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("platform.id", ondelete="CASCADE"),
        nullable=False,
    )
    extension: Mapped[str] = mapped_column(String(16), nullable=False)
    format_type: Mapped[str] = mapped_column(String(16), nullable=False)
    min_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    max_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    pack_source: Mapped[str] = mapped_column(
        String(16), nullable=False, default="builtin"
    )

    platform: Mapped[Platform] = relationship(back_populates="formats")

    __table_args__ = (
        UniqueConstraint("platform_id", "extension", name="uq_platform_format"),
        CheckConstraint(
            "format_type IN ('cartridge', 'disc', 'compressed', 'archive', 'package')",
            name="ck_platform_format_type",
        ),
        CheckConstraint(
            "pack_source IN ('builtin', 'community', 'user')",
            name="ck_platform_format_pack_source",
        ),
    )


class PlatformNamingToken(Base, TimestampMixin):
    """Regex pattern + meaning for per-platform filename interpretation.

    Pack-defined regex patterns are subject to the adversarial-input
    50 ms time-bound check at validation (spec 003 FR-005a, spec 001
    Q1 surfaces it for the foundation parsers too).
    """

    __tablename__ = "platform_naming_token"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("platform.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    pattern: Mapped[str] = mapped_column(String(512), nullable=False)
    meaning: Mapped[str] = mapped_column(String(64), nullable=False)
    convention: Mapped[NamingConvention] = mapped_column(
        String(16), nullable=False, default=NamingConvention.NO_INTRO
    )
    pack_source: Mapped[str] = mapped_column(
        String(16), nullable=False, default="builtin"
    )

    platform: Mapped[Platform] = relationship(back_populates="naming_tokens")

    __table_args__ = (
        UniqueConstraint("platform_id", "name", name="uq_platform_naming_token"),
        CheckConstraint(
            "pack_source IN ('builtin', 'community', 'user')",
            name="ck_platform_naming_token_pack_source",
        ),
    )


class Game(Base, TimestampMixin):
    """A title bound to exactly one Platform (FR-002).

    *Sonic the Hedgehog* on Mega Drive and *Sonic the Hedgehog* on Game
    Boy Advance are TWO DISTINCT Games even though they share a title
    (Acceptance Scenario 1.2 of User Story 1).
    """

    __tablename__ = "game"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("platform.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    slug: Mapped[str] = mapped_column(String(192), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    summary: Mapped[str | None] = mapped_column(String, nullable=True)
    cover_path: Mapped[str | None] = mapped_column(String, nullable=True)

    # Metadata aggregation outputs (spec 002 populates / mutates these).
    igdb_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mobygames_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    screenscraper_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    launchbox_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retroachievements_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    release_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    developer: Mapped[str | None] = mapped_column(String(128), nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(128), nullable=True)
    rating: Mapped[float | None] = mapped_column(nullable=True)
    age_rating: Mapped[str | None] = mapped_column(String(16), nullable=True)
    players_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    players_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hltb_main: Mapped[int | None] = mapped_column(Integer, nullable=True)
    achievements_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    genres: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    themes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    franchises: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    tags: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)

    # Per-field locks — the constitutional anti-RomM-#1770 mechanism.
    locked_fields: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    custom_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    monitored: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    needs_metadata_refresh: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    # Operator-owned free-text notes (spec 014 slice 149). Never
    # touched by the spec-002 aggregator — distinct from
    # ``summary``, which is provider-owned.
    notes: Mapped[str | None] = mapped_column(String, nullable=True)

    # Slice 385 — Sonarr-style library binding. The operator picks
    # a library at add-time; the importer reads this back when
    # auto-creating a Release for a manual grab so the file lands
    # under the right root with that library's profile cascade.
    # Nullable for backward compat with rows added before this
    # column existed; the importer falls back to platform routing
    # when unset.
    library_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("library.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Relationships
    platform: Mapped[Platform] = relationship(back_populates="games")
    releases: Mapped[list[Release]] = relationship(
        back_populates="game",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint("platform_id", "slug", name="uq_game_platform_slug"),
        Index("idx_game_title", "title"),
    )


class Release(Base, TimestampMixin):
    """A region/revision/dump-status variant of a Game.

    Per FR-003 every cutoff/upgrade decision operates per-Release, not
    per-Game. Multi-disc sets self-reference via ``parent_release_id``
    (FR-004) — disc 1 is the parent with ``disc_total > 1``; discs 2..N
    point to the parent via ``parent_release_id``.
    """

    __tablename__ = "release"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("game.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Release identity
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    original_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    regions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    languages: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    revision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    dump_status: Mapped[DumpStatus] = mapped_column(
        String(16), nullable=False, default=DumpStatus.UNKNOWN
    )
    naming_convention: Mapped[NamingConvention] = mapped_column(
        String(16), nullable=False, default=NamingConvention.UNKNOWN
    )
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    # Multi-disc support
    disc_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    disc_total: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    parent_release_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("release.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Lifecycle
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="wanted")
    monitored: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    cutoff_met: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Library binding (spec 009): nullable so a Release can survive a
    # library force-delete (FR-026 — set NULL, do not cascade). The
    # FK target is added by Alembic ``0009_libraries`` so this column
    # is harmless on any DB whose head is < 0009.
    library_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("library.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Relationships
    game: Mapped[Game] = relationship(back_populates="releases")
    parent_release: Mapped[Release | None] = relationship(
        remote_side="Release.id",
        back_populates="child_releases",
    )
    child_releases: Mapped[list[Release]] = relationship(
        back_populates="parent_release",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    dumps: Mapped[list[Dump]] = relationship(
        back_populates="release",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        # FR-004: disc_number > 1 implies parent_release_id IS NOT NULL
        CheckConstraint(
            "(disc_number = 1) OR (parent_release_id IS NOT NULL)",
            name="ck_release_multidisc_parent",
        ),
        CheckConstraint(
            "status IN ('wanted', 'imported', 'cutoff_met')",
            name="ck_release_status",
        ),
        CheckConstraint("disc_number >= 1", name="ck_release_disc_number_positive"),
        CheckConstraint("disc_total >= 1", name="ck_release_disc_total_positive"),
    )


class Dump(Base, TimestampMixin):
    """The actual file on disk for a Release, with hashes.

    Per FR-005 ``path`` is globally unique; per FR-014 the hasher
    computes CRC32, MD5, and SHA-1 in a single pass. SHA-256 is
    optional and disabled by default.
    """

    __tablename__ = "dump"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    release_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("release.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # File location and metadata
    path: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    original_filename: Mapped[str] = mapped_column(String, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    format: Mapped[str] = mapped_column(String(16), nullable=False)

    # Hashes — always populated from a single streaming pass.
    crc32: Mapped[str] = mapped_column(String(8), nullable=False)
    md5: Mapped[str] = mapped_column(String(32), nullable=False)
    sha1: Mapped[str] = mapped_column(String(40), nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # DAT verification (FR-010)
    dat_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dat_source: Mapped[str | None] = mapped_column(String(16), nullable=True)
    dat_entry_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("dat_entry.id", ondelete="SET NULL"), nullable=True
    )

    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    imported_by: Mapped[str] = mapped_column(String(32), nullable=False, default="system")
    imported_via: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # Relationships
    release: Mapped[Release] = relationship(back_populates="dumps")
    dat_entry: Mapped[DatEntry | None] = relationship(back_populates="dumps")

    __table_args__ = (
        Index("idx_dump_sha1", "sha1"),
        Index("idx_dump_crc32", "crc32"),
        Index("idx_dump_md5", "md5"),
    )


class DatEntry(Base, TimestampMixin):
    """A canonical record from an authoritative DAT database.

    Per FR-006 a DAT entry must carry at least one of CRC32, MD5, or
    SHA-1. The cross-DAT precedence resolver (spec 001 Q1, FR-020a)
    consults entries in fixed order **No-Intro > Redump > TOSEC** when
    a single hash matches multiple DATs.
    """

    __tablename__ = "dat_entry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("platform.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # At least one MUST be present (FR-006); enforced at the API layer.
    crc32: Mapped[str | None] = mapped_column(String(8), nullable=True, index=True)
    md5: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    sha1: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)

    status: Mapped[DumpStatus] = mapped_column(
        String(16), nullable=False, default=DumpStatus.VERIFIED
    )

    # ``contents_hash`` of the source DAT bundle — used for idempotent
    # ingestion (FR-019).
    dat_contents_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    dumps: Mapped[list[Dump]] = relationship(back_populates="dat_entry")

    __table_args__ = (
        CheckConstraint(
            "(crc32 IS NOT NULL) OR (md5 IS NOT NULL) OR (sha1 IS NOT NULL)",
            name="ck_dat_entry_at_least_one_hash",
        ),
        CheckConstraint(
            "source IN ('no-intro', 'redump', 'tosec', 'goodtools', "
            "'hasheous', 'playmatch', 'custom')",
            name="ck_dat_entry_source",
        ),
        UniqueConstraint(
            "platform_id", "source", "sha1",
            name="uq_dat_entry_platform_source_sha1",
        ),
    )


class DatSource(Base, TimestampMixin):
    """A persistent DAT source URL + per-platform binding.

    Slice 443 — pre-slice the only DAT-related table was ``dat_entry``
    (the parsed entries cache). The list of URLs to fetch lived in
    code / settings only; ``DatUpdateRunner`` accepted
    ``DatSourceSpec`` triples passed in by the caller, with no
    persistence layer. This row holds the URL + binding so:

    - the bootstrap helper can seed recommended URLs at first boot
      from the ``identification/dat/recommended.py`` catalog;
    - operators can add custom URLs via ``POST /api/v3/dat-source``;
    - the scheduled DAT-update task refreshes every enabled row;
    - the Settings → DAT Sources UI shows last-refresh status +
      entry-count per source so operators see at a glance what's
      loaded and when it last succeeded.

    ``source`` is the DAT-authority literal that pairs with each
    fetched entry's ``DatEntry.source`` (no-intro / redump / tosec
    / …) — same CHECK literals on both tables.
    """

    __tablename__ = "dat_source"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    platform_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("platform.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1", index=True
    )
    last_refresh_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_refresh_status: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )
    last_refresh_error: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    last_entry_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "source", "platform_id", name="uq_dat_source_source_platform"
        ),
        CheckConstraint(
            "source IN ('no-intro','redump','tosec','goodtools','hasheous',"
            "'playmatch','custom')",
            name="ck_dat_source_source",
        ),
        CheckConstraint(
            "last_refresh_status IS NULL "
            "OR last_refresh_status IN ('ok','failed','running')",
            name="ck_dat_source_status",
        ),
    )


class UnidentifiedDump(Base, TimestampMixin):
    """Files the pipeline could not match with confidence ≥ 0.5 (FR-029).

    Spec 008 (Importer) extends this row with ``rejection_reason``,
    ``library_id`` FK, and ``suggested_game_id`` FK. The foundation
    spec ships only the columns it needs; later migrations append.
    """

    __tablename__ = "unidentified_dump"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    path: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Attempted hashes (all may be NULL on a hash failure path).
    crc32: Mapped[str | None] = mapped_column(String(8), nullable=True)
    md5: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sha1: Mapped[str | None] = mapped_column(String(40), nullable=True)

    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)

    # Hint surfaces for manual triage (populated when known).
    suggested_platform_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("platform.id", ondelete="SET NULL"), nullable=True
    )

    # Spec 008 (Importer) extensions. The columns are added by Alembic
    # ``0008_import_pipeline``; the FK on ``library_id`` is gated on
    # whether the ``library`` table already exists (per data-model.md's
    # Forward Dependency section). The ``suggested_game_id`` FK lands
    # unconditionally — the ``game`` table ships in foundation.
    rejection_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    library_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    suggested_game_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("game.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint("attempt_count >= 0", name="ck_unidentified_dump_attempts"),
    )


class PlatformPack(Base, TimestampMixin):
    """A versioned bundle of platform definitions.

    Spec 003 owns the bulk of pack ingestion (validation, audit log,
    `parsing_strategies` table). The foundation spec creates only the
    `platform_pack` row table itself so DAT-imports and hash-matches
    can refer to a `pack_version`.
    """

    __tablename__ = "platform_pack"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pack_version: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    author: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String, nullable=True)

    # Idempotency key (FR-008)
    contents_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    pack_source: Mapped[str] = mapped_column(
        String(16), nullable=False, default="builtin"
    )

    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    applied_by: Mapped[str] = mapped_column(String(32), nullable=False, default="system")

    __table_args__ = (
        CheckConstraint(
            "pack_source IN ('builtin', 'community', 'user')",
            name="ck_platform_pack_source",
        ),
        CheckConstraint("schema_version >= 1", name="ck_platform_pack_schema_version"),
    )


class RomPack(Base, TimestampMixin):
    """A downloadable archive holding many ROMs — a "content pack".

    Slice 460. Distinct from :class:`PlatformPack` (which carries
    *platform metadata*): a RomPack is actual ROM content — a
    No-Intro full set, an archive.org romset, a curated starter
    bundle. The ingest task downloads the archive, extracts it
    recursively, and runs every ROM through the importer; a
    :class:`RomPackItem` row tracks each file's outcome.

    Two ``source_kind`` values:
    - ``url`` — operator pasted a direct-download URL (mirrors the
      ``dat_source`` pattern);
    - ``grab`` — the pack came through the grab pipeline / a
      download client, flagged multi-ROM (slice 463).
    """

    __tablename__ = "rom_pack"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_kind: Mapped[str] = mapped_column(
        String(8), nullable=False, default="url"
    )
    # ``url`` source: the direct-download URL. NULL for grab-sourced.
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    # ``grab`` source: the download-client pair the archive came
    # from. NULL for url-sourced.
    download_client_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    download_client_native_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    # Optional platform hint — multi-platform packs leave it NULL
    # and rely on per-ROM DAT identification to scatter across
    # platforms.
    platform_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("platform.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Operator-configurable size ceiling for the download, in
    # bytes. NULL = use the global default. Guards against a
    # mistyped URL pulling a 200 GB blob.
    max_size_bytes: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    # Slice 466 — scope of the import:
    #   ``all`` — every ROM is imported (DAT match drives the Game
    #     name; non-DAT fall back to a metadata-provider lookup
    #     by filename + platform, then to manual triage).
    #   ``dat_verified`` — only DAT-matched ROMs are imported;
    #     non-DAT files are skipped (no rom_pack_item row).
    import_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="all"
    )
    # Slice 472 — fallback policy when a ROM has no DAT match AND
    # the metadata-provider lookup also fails (mode 'all' only):
    #   ``triage`` — leave it ``unmatched`` for manual resolution.
    #   ``park``   — auto-park into ``unidentified_dump``.
    #   ``delete`` — drop the extracted file outright.
    unknown_action: Mapped[str] = mapped_column(
        String(12), nullable=False, default="triage"
    )

    # Lifecycle: pending → downloading → extracting → importing →
    # awaiting_triage (if any unmatched) → done | failed.
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )
    # Where the archive landed on disk (cleared once extracted +
    # the archive itself is purged).
    downloaded_path: Mapped[str | None] = mapped_column(
        String(2048), nullable=True
    )
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Per-pack telemetry, surfaced on the Content Packs settings
    # page so the operator sees the outcome at a glance.
    total_files: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    imported_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    unmatched_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    parked_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    failed_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    last_error: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    last_ingest_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    items: Mapped[list[RomPackItem]] = relationship(
        back_populates="rom_pack",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint(
            "source_kind IN ('url', 'grab')",
            name="ck_rom_pack_source_kind",
        ),
        CheckConstraint(
            "status IN ('pending','downloading','extracting','importing',"
            "'awaiting_triage','done','failed')",
            name="ck_rom_pack_status",
        ),
        CheckConstraint(
            "(source_kind = 'url' AND url IS NOT NULL) "
            "OR (source_kind = 'grab' AND download_client_native_id IS NOT NULL)",
            name="ck_rom_pack_source_fields",
        ),
        CheckConstraint(
            "import_mode IN ('all', 'dat_verified')",
            name="ck_rom_pack_import_mode",
        ),
        CheckConstraint(
            "unknown_action IN ('triage', 'park', 'delete')",
            name="ck_rom_pack_unknown_action",
        ),
    )


class RomPackItem(Base, TimestampMixin):
    """One ROM file extracted from a :class:`RomPack`.

    Slice 460. The ingest task creates one row per extracted ROM
    and records what the importer did with it:

    - ``imported`` — DAT-matched (or auto-created) and placed in a
      Library; ``game_id`` / ``dump_id`` point at the result;
    - ``unmatched`` — no DAT entry matched the hash; awaits the
      operator's triage-modal decision (slice 462);
    - ``parked`` — operator (or auto-policy) sent it to
      ``unidentified_dump``;
    - ``deleted`` — operator discarded it from the triage modal;
    - ``failed`` — the per-file import raised.
    """

    __tablename__ = "rom_pack_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rom_pack_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("rom_pack.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(String, nullable=False)
    extracted_path: Mapped[str | None] = mapped_column(
        String(2048), nullable=True
    )
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    crc32: Mapped[str | None] = mapped_column(String(8), nullable=True)
    md5: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sha1: Mapped[str | None] = mapped_column(String(40), nullable=True)

    status: Mapped[str] = mapped_column(
        String(12), nullable=False, default="unmatched", index=True
    )
    # The DAT entry / Game / Dump the importer resolved, when it
    # did. All NULL for an ``unmatched`` row.
    dat_entry_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("dat_entry.id", ondelete="SET NULL"), nullable=True
    )
    game_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("game.id", ondelete="SET NULL"), nullable=True
    )
    dump_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("dump.id", ondelete="SET NULL"), nullable=True
    )
    error_msg: Mapped[str | None] = mapped_column(String(500), nullable=True)

    rom_pack: Mapped[RomPack] = relationship(back_populates="items")

    __table_args__ = (
        CheckConstraint(
            "status IN ('imported','unmatched','parked','deleted','failed')",
            name="ck_rom_pack_item_status",
        ),
    )


class RomPackConfig(Base, TimestampMixin):
    """Global defaults for the ROM-pack subsystem — a singleton row.

    Slice 464. Holds operator-tunable defaults that aren't worth a
    per-pack column: where url-sourced archives stream to disk,
    and the size ceiling a pack inherits when it doesn't pin its
    own ``max_size_bytes``. Exactly one row exists (``id = 1``);
    the API get-or-creates it.
    """

    __tablename__ = "rom_pack_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Where url-sourced pack archives stream to + extract under.
    # grab-sourced packs ignore this — their archive is wherever
    # the download client dropped it.
    download_dir: Mapped[str] = mapped_column(
        String(2048), nullable=False, default="/downloads/rom_packs"
    )
    # Default per-pack download ceiling in bytes; a pack's own
    # ``max_size_bytes`` overrides it. NULL = the hard-coded
    # 50 GiB fallback in the ingest pipeline.
    default_max_size_bytes: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )

    __table_args__ = (
        CheckConstraint("id = 1", name="ck_rom_pack_config_singleton"),
    )
