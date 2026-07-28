"""Add ``download_client.remote_path`` + ``local_path`` for Radarr-style path mapping.

When the download client reports content_path=/downloads/foo.zip but
Romarr's runtime sees the same volume mounted at /mnt/qbit/foo.zip,
the two columns let the reconciler + importer swap the prefix before
touching the filesystem. Both NULL = no remap (default). Only needed
when Romarr and the client live on different sides of a volume mount
(typical: Romarr native on the host + qBit in Docker).

Revision ID: 0039_download_client_path_mapping
Revises: 0038_platform_pack_config
Create Date: 2026-07-28
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0039_download_client_path_mapping"
down_revision: Union[str, Sequence[str], None] = "0038_platform_pack_config"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("download_client") as batch:
        batch.add_column(sa.Column("remote_path", sa.String(512), nullable=True))
        batch.add_column(sa.Column("local_path", sa.String(512), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("download_client") as batch:
        batch.drop_column("local_path")
        batch.drop_column("remote_path")
