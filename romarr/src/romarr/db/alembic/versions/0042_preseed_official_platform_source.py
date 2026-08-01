"""Preseed the official platform-pack community source; disable builtin.

Aligns Romarr with the community-first model :

  * Inserts a canonical ``Romarr Official Platforms`` row into
    ``pack_sources`` pointing at
    https://raw.githubusercontent.com/sharkhunterr/romarr-plateform-pack/main/manifest.json
    — auto-checked + trusted at seed time so the app's first boot
    can apply it without operator intervention.
  * Flips ``platform_pack_config.builtin_enabled`` to false so the
    wheel-bundled YAML pack no longer auto-applies on boot. The
    resource stays on disk (still callable via the API) but the
    lifespan hook no longer walks it — the community source is now
    the sole boot-time seed path.

Idempotent on re-run : the source is upserted by unique name, the
config toggle is flipped only if the row already exists.

Revision ID: 0042_preseed_official_platform_source
Revises: 0041_custom_format_source_enabled
Create Date: 2026-08-01
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0042_preseed_official_platform_source"
down_revision: Union[str, Sequence[str], None] = (
    "0041_custom_format_source_enabled"
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_OFFICIAL_NAME = "Romarr Official Platforms"
_OFFICIAL_URL = (
    "https://raw.githubusercontent.com/sharkhunterr/"
    "romarr-plateform-pack/main/manifest.json"
)


def upgrade() -> None:
    # Insert the canonical source only if a row with that name is
    # not already present. SQLite friendly; portable elsewhere too.
    op.execute(
        f"""
        INSERT INTO pack_sources (
            name, url, kind, resource_type, enabled, auto_check,
            trust_status, last_applied_count, created_at, updated_at
        )
        SELECT
            '{_OFFICIAL_NAME}',
            '{_OFFICIAL_URL}',
            'raw',
            'platform_pack',
            1, 1, 'trusted', 0,
            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        WHERE NOT EXISTS (
            SELECT 1 FROM pack_sources WHERE name = '{_OFFICIAL_NAME}'
        )
        """
    )

    # Force builtin auto-apply OFF — the community source now owns
    # the boot-time seed path. Existing installs migrated from the
    # legacy builtin flow keep their existing platforms; the
    # official source's first apply is idempotent on
    # matching contents_hash.
    op.execute(
        """
        UPDATE platform_pack_config
        SET builtin_enabled = 0,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = 1
        """
    )


def downgrade() -> None:
    op.execute(
        f"DELETE FROM pack_sources WHERE name = '{_OFFICIAL_NAME}' "
        f"AND url = '{_OFFICIAL_URL}'"
    )
    op.execute(
        """
        UPDATE platform_pack_config
        SET builtin_enabled = 1,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = 1
        """
    )
