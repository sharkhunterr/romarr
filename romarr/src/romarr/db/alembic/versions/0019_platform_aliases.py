"""Slice 401 — RomM-aligned platform slugs + per-platform aliases.

Two additive changes:

  1. ``platform.aliases`` — JSON list of operator-facing
     nickname strings the title-match / filename-parser uses to
     identify the platform. Lets the importer + manual search
     match a release titled "Final Fantasy VII (PSX)" or "(PS1)"
     or "(PlayStation)" against the same Platform row.

  2. Three slug renames to align with RomM's canonical folder
     names so a parallel RomM scan finds the same on-disk
     layout: ``megadrive → genesis``, ``gamecube → ngc``,
     ``dreamcast → dc``. The FK refs are on ``platform.id``
     which is stable across rename, so no further migration
     work is needed.

Revision ID: 0019_platform_aliases
Revises: 0018_game_library_id
Create Date: 2026-05-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0019_platform_aliases"
down_revision = "0018_game_library_id"
branch_labels = None
depends_on = None


_SLUG_RENAMES = [
    ("megadrive", "genesis"),
    ("gamecube", "ngc"),
    ("dreamcast", "dc"),
]


def upgrade() -> None:
    # 1. Add the JSON column. SQLite stores it as TEXT.
    with op.batch_alter_table("platform") as batch:
        batch.add_column(
            sa.Column(
                "aliases",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )
    # 2. RomM-canonical slug renames. Skipped silently when the
    #    legacy slug isn't present (fresh install with the new
    #    pack already seeded).
    bind = op.get_bind()
    for old, new in _SLUG_RENAMES:
        bind.execute(
            sa.text(
                "UPDATE platform SET slug = :new WHERE slug = :old"
            ),
            {"old": old, "new": new},
        )


def downgrade() -> None:
    bind = op.get_bind()
    for old, new in _SLUG_RENAMES:
        bind.execute(
            sa.text(
                "UPDATE platform SET slug = :old WHERE slug = :new"
            ),
            {"old": old, "new": new},
        )
    with op.batch_alter_table("platform") as batch:
        batch.drop_column("aliases")
