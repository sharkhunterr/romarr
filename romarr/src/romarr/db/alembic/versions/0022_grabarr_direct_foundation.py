"""Slice 422 — widen check constraints for the Grabarr-direct foundation.

Adds the literals the new integration needs **without** wiring any of
the surrounding behaviour:

- ``download_client.type`` accepts ``'grabarr_direct'`` (the new
  client kind that resolves a Grabarr result and either streams it
  via httpx or delegates the magnet to qBit).
- ``indexer.implementation`` accepts ``'grabarr'`` (the indexer kind
  whose grab path goes through ``/romarr/api/v1/resolve`` instead of
  Newznab/Torznab ``/download``).

This migration is intentionally inert: the stub client ships with
``available = False`` so the UI ``_CLIENT_TYPES`` array does not list
it, and the indexer modal's ``_IMPLEMENTATIONS`` array stays at
``['newznab','torznab']`` until the wizard lands. The CHECK widening
arrives first because every downstream piece (stub class import,
test fixture, future wiring) needs the column shape to allow the
new literal at insert time.

See ``docs/grabarr-direct-protocol.md`` (v0.2) for the full picture.

Revision ID: 0022_grabarr_direct_foundation
Revises: 0021_download_client_timeout
Create Date: 2026-05-12
"""

from __future__ import annotations

from alembic import op


revision = "0022_grabarr_direct_foundation"
down_revision = "0021_download_client_timeout"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("download_client") as batch_op:
        batch_op.drop_constraint("ck_download_client_type", type_="check")
        batch_op.create_check_constraint(
            "ck_download_client_type",
            "type IN ('qbittorrent','sabnzbd','transmission','deluge',"
            "'nzbget','grabarr_direct')",
        )

    with op.batch_alter_table("indexer") as batch_op:
        batch_op.drop_constraint("ck_indexer_implementation", type_="check")
        batch_op.create_check_constraint(
            "ck_indexer_implementation",
            "implementation IN ('newznab','torznab','grabarr')",
        )


def downgrade() -> None:
    # Clamp any rows on the new literals before re-tightening, otherwise
    # the recreate fails on existing data. Deletes are the safe pick
    # since these rows can't function under the old constraint anyway.
    op.execute(
        "DELETE FROM indexer WHERE implementation = 'grabarr'"
    )
    op.execute(
        "DELETE FROM download_client WHERE type = 'grabarr_direct'"
    )

    with op.batch_alter_table("indexer") as batch_op:
        batch_op.drop_constraint("ck_indexer_implementation", type_="check")
        batch_op.create_check_constraint(
            "ck_indexer_implementation",
            "implementation IN ('newznab','torznab')",
        )

    with op.batch_alter_table("download_client") as batch_op:
        batch_op.drop_constraint("ck_download_client_type", type_="check")
        batch_op.create_check_constraint(
            "ck_download_client_type",
            "type IN ('qbittorrent','sabnzbd','transmission','deluge','nzbget')",
        )
