"""Slice 455 — rename platform slug ``gameboy`` → ``gb``.

RomM's canonical slug for the original Game Boy is ``gb`` (the
GBC / GBA siblings are already ``gbc`` / ``gba``). Romarr seeded
``gameboy`` in 0001 and the builtin packs carried it forward —
the odd one out in the handheld family and a mismatch when an
operator runs Romarr alongside RomM on the same library tree.

This migration flips the ``platform`` row's slug and rewrites
any ``dump.path`` that points at the old ``/roms/gameboy/``
segment so the DB stays internally consistent. The matching
``builtin-2026.05.002.yaml`` pack + every metadata-provider
slug map are updated in the same slice; ``gameboy`` survives
as an alias on the pack so existing filename-parser hints and
operator muscle-memory still resolve.

NOTE: the physical on-disk folder rename
(``library/roms/gameboy`` → ``library/roms/gb``) is NOT done
here — Alembic migrations must not touch the filesystem. The
path rewrite below keeps the DB pointing at ``/roms/gb/``;
operators move the directory once, out-of-band, alongside
deploying this version.

Revision ID: 0028_platform_slug_gameboy_to_gb
Revises: 0027_queue_entry_content_path
Create Date: 2026-05-14
"""

from __future__ import annotations

from alembic import op


revision = "0028_platform_slug_gameboy_to_gb"
down_revision = "0027_queue_entry_content_path"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE platform SET slug = 'gb' WHERE slug = 'gameboy'"
    )
    # Keep dump paths consistent with the new slug-derived library
    # subtree. REPLACE is a no-op on rows that don't carry the
    # segment, so this is safe on every deployment.
    op.execute(
        "UPDATE dump "
        "SET path = REPLACE(path, '/roms/gameboy/', '/roms/gb/') "
        "WHERE path LIKE '%/roms/gameboy/%'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE dump "
        "SET path = REPLACE(path, '/roms/gb/', '/roms/gameboy/') "
        "WHERE path LIKE '%/roms/gb/%'"
    )
    op.execute(
        "UPDATE platform SET slug = 'gameboy' WHERE slug = 'gb'"
    )
