"""add personal intra-org commission overrides

Revision ID: 021
Revises: 020
Create Date: 2026-09-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "personal_performance_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("distributor_id", sa.Integer(), nullable=False),
        sa.Column("tiers", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["distributor_id"], ["distributors.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "distributor_id", name="uq_personal_perf_distributor"
        ),
    )


def downgrade() -> None:
    op.drop_table("personal_performance_rules")
