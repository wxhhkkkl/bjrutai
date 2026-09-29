"""record commission point redemptions

Revision ID: 022
Revises: 021
Create Date: 2026-09-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "commission_results",
        sa.Column("redeemed_points_x100", sa.Integer(), nullable=True),
    )
    op.add_column(
        "commission_results",
        sa.Column("points_redeemed_by", sa.Integer(), nullable=True),
    )
    op.add_column(
        "commission_results",
        sa.Column("points_redeemed_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("commission_results", "points_redeemed_at")
    op.drop_column("commission_results", "points_redeemed_by")
    op.drop_column("commission_results", "redeemed_points_x100")
