"""Add ``quality_profile.auto_grab_min_score``.

Operator-tunable floor for RSS / on-add auto-grabs. The grab
decision still requires ``rejection is None``; this gate adds a
score threshold on top so weak hits the manual modal would still
show stay out of the auto-dispatch path.

Default 0 preserves the legacy ``> 0`` behaviour for existing
rows (operator opts in to a stricter floor by editing the
profile).

Revision ID: 0035_quality_profile_auto_grab_min_score
Revises: 0034_queue_entry_state_extracting_importing
Create Date: 2026-05-19
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0035_quality_profile_auto_grab_min_score"
down_revision: Union[str, Sequence[str], None] = (
    "0034_queue_entry_state_extracting_importing"
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("quality_profile") as batch:
        batch.add_column(
            sa.Column(
                "auto_grab_min_score",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("quality_profile") as batch:
        batch.drop_column("auto_grab_min_score")
