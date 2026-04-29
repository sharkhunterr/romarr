"""Spec 002 — Metadata Aggregation schema + seed data.

Creates three tables:
  - ``metadata_provider_config`` — per-provider toggle, encrypted
    credentials, rate-limit knobs (FR-019, FR-021, FR-004a).
  - ``metadata_cache``           — TTL-bounded raw provider responses
    keyed on ``(provider, provider_game_id)`` (FR-016a).
  - ``field_priority``           — ranked per-(field, provider)
    preference list consumed by the aggregator (FR-008).

Seeds two configuration sets verbatim from
``specs/002-metadata-aggregation/data-model.md``:
  - one ``metadata_provider_config`` row per known provider, all with
    ``enabled=false`` and provider-specific ``priority_global`` +
    rate-limit defaults.
  - the canonical RomM-aligned ``field_priority`` defaults (Article IX).

Idempotent — re-running the seed (e.g. after a stamp + upgrade) does
not duplicate rows; conflicts on the natural keys are skipped.

The Game column ``needs_metadata_refresh`` already lives in 0001 (the
foundation pre-provisioned every metadata-target column on Game so
this layer ships purely additive).

Revision ID: 0002_metadata_layer
Revises: 0010_auth_multiuser
Create Date: 2026-04-29
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

# Revision identifiers used by Alembic.
revision = "0002_metadata_layer"
down_revision = "0010_auth_multiuser"
branch_labels = None
depends_on = None


_KNOWN_PROVIDERS = (
    "igdb",
    "screenscraper",
    "mobygames",
    "launchbox",
    "steamgriddb",
    "retroachievements",
    "howlongtobeat",
    "hasheous",
    "playmatch",
)
_PROVIDER_CHECK = "provider_name IN (" + ",".join(f"'{p}'" for p in _KNOWN_PROVIDERS) + ")"


# Mirror of data-model.md "Initial seed" + clarification deltas.
_PROVIDER_SEED: tuple[dict[str, object], ...] = (
    {"provider_name": "igdb", "priority_global": 10, "rate_limit_rps": 4, "rate_limit_burst": 8},
    {"provider_name": "screenscraper", "priority_global": 20, "rate_limit_rps": 2, "rate_limit_burst": 4},
    {"provider_name": "mobygames", "priority_global": 30, "rate_limit_rps": 1, "rate_limit_burst": 2},
    {"provider_name": "launchbox", "priority_global": 40, "rate_limit_rps": 5, "rate_limit_burst": 10},
    {"provider_name": "hasheous", "priority_global": 50, "rate_limit_rps": 5, "rate_limit_burst": 10},
    {"provider_name": "playmatch", "priority_global": 60, "rate_limit_rps": 5, "rate_limit_burst": 10},
    {"provider_name": "retroachievements", "priority_global": 70, "rate_limit_rps": 5, "rate_limit_burst": 10},
    {"provider_name": "howlongtobeat", "priority_global": 80, "rate_limit_rps": 5, "rate_limit_burst": 10},
    {"provider_name": "steamgriddb", "priority_global": 90, "rate_limit_rps": 5, "rate_limit_burst": 10},
)

# Mirror of data-model.md "Default seed" for field_priority.
_FIELD_PRIORITY_SEED: tuple[tuple[str, int, str], ...] = (
    ("title", 1, "igdb"),
    ("title", 2, "screenscraper"),
    ("title", 3, "mobygames"),
    ("title", 4, "launchbox"),
    ("summary", 1, "igdb"),
    ("summary", 2, "mobygames"),
    ("summary", 3, "screenscraper"),
    ("cover", 1, "igdb"),
    ("cover", 2, "screenscraper"),
    ("cover", 3, "steamgriddb"),
    ("cover", 4, "launchbox"),
    ("genres", 1, "igdb"),
    ("genres", 2, "mobygames"),
    ("genres", 3, "launchbox"),
    ("release_date", 1, "mobygames"),
    ("release_date", 2, "igdb"),
    ("release_date", 3, "screenscraper"),
    ("developer", 1, "mobygames"),
    ("developer", 2, "igdb"),
    ("publisher", 1, "mobygames"),
    ("publisher", 2, "igdb"),
    ("rating", 1, "igdb"),
    ("themes", 1, "igdb"),
    ("themes", 2, "mobygames"),
    ("franchises", 1, "igdb"),
    ("franchises", 2, "mobygames"),
    ("players_min", 1, "mobygames"),
    ("players_min", 2, "igdb"),
    ("players_max", 1, "mobygames"),
    ("players_max", 2, "igdb"),
    ("age_rating", 1, "igdb"),
    ("age_rating", 2, "mobygames"),
    ("achievements_count", 1, "retroachievements"),
    ("hltb_main", 1, "howlongtobeat"),
)


def upgrade() -> None:
    op.create_table(
        "metadata_provider_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider_name", sa.String(32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("config_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("priority_global", sa.Integer(), nullable=False, server_default="100"),
        sa.Column(
            "cache_ttl_seconds",
            sa.Integer(),
            nullable=False,
            server_default=str(2_592_000),
        ),
        sa.Column("rate_limit_rps", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("rate_limit_burst", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("last_health_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_health_check_ok", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider_name", name="uq_metadata_provider_config_name"),
        sa.CheckConstraint(_PROVIDER_CHECK, name="ck_metadata_provider_config_name"),
    )

    op.create_table(
        "metadata_cache",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider_name", sa.String(32), nullable=False),
        sa.Column("provider_game_id", sa.String(128), nullable=False),
        sa.Column(
            "game_id",
            sa.Integer(),
            sa.ForeignKey("game.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "provider_name",
            "provider_game_id",
            name="uq_metadata_cache_provider_game",
        ),
        sa.CheckConstraint(_PROVIDER_CHECK, name="ck_metadata_cache_provider_name"),
    )
    op.create_index(
        "idx_metadata_cache_game_provider",
        "metadata_cache",
        ["game_id", "provider_name"],
    )
    op.create_index(
        "idx_metadata_cache_expires_at",
        "metadata_cache",
        ["expires_at"],
    )

    op.create_table(
        "field_priority",
        sa.Column("field_name", sa.String(64), nullable=False),
        sa.Column("provider_name", sa.String(32), nullable=False),
        sa.Column("priority_order", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("field_name", "provider_name", name="pk_field_priority"),
        sa.UniqueConstraint(
            "field_name",
            "priority_order",
            name="uq_field_priority_field_order",
        ),
        sa.CheckConstraint(_PROVIDER_CHECK, name="ck_field_priority_provider_name"),
    )

    _seed_provider_config()
    _seed_field_priority()


def downgrade() -> None:
    op.drop_table("field_priority")
    op.drop_index("idx_metadata_cache_expires_at", table_name="metadata_cache")
    op.drop_index("idx_metadata_cache_game_provider", table_name="metadata_cache")
    op.drop_table("metadata_cache")
    op.drop_table("metadata_provider_config")


# ---------------------------------------------------------------------------
# Seeders (idempotent)
# ---------------------------------------------------------------------------


def _seed_provider_config() -> None:
    bind = op.get_bind()
    now = datetime.now(UTC)
    existing = {
        row[0]
        for row in bind.execute(
            sa.text("SELECT provider_name FROM metadata_provider_config")
        ).fetchall()
    }
    new_rows = [row for row in _PROVIDER_SEED if row["provider_name"] not in existing]
    if not new_rows:
        return
    table = sa.table(
        "metadata_provider_config",
        sa.column("provider_name", sa.String(32)),
        sa.column("enabled", sa.Boolean()),
        sa.column("priority_global", sa.Integer()),
        sa.column("cache_ttl_seconds", sa.Integer()),
        sa.column("rate_limit_rps", sa.Integer()),
        sa.column("rate_limit_burst", sa.Integer()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        table,
        [
            {
                "provider_name": row["provider_name"],
                "enabled": False,
                "priority_global": row["priority_global"],
                "cache_ttl_seconds": 2_592_000,
                "rate_limit_rps": row["rate_limit_rps"],
                "rate_limit_burst": row["rate_limit_burst"],
                "created_at": now,
                "updated_at": now,
            }
            for row in new_rows
        ],
    )


def _seed_field_priority() -> None:
    bind = op.get_bind()
    now = datetime.now(UTC)
    existing = {
        (row[0], row[1])
        for row in bind.execute(
            sa.text("SELECT field_name, provider_name FROM field_priority")
        ).fetchall()
    }
    new_rows = [
        (field, order, provider)
        for field, order, provider in _FIELD_PRIORITY_SEED
        if (field, provider) not in existing
    ]
    if not new_rows:
        return
    table = sa.table(
        "field_priority",
        sa.column("field_name", sa.String(64)),
        sa.column("provider_name", sa.String(32)),
        sa.column("priority_order", sa.Integer()),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        table,
        [
            {
                "field_name": field,
                "provider_name": provider,
                "priority_order": order,
                "updated_at": now,
            }
            for field, order, provider in new_rows
        ],
    )
