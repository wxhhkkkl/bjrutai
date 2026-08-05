"""add performance_settlements + commission_results.rule_snapshot

Revision ID: 011
Revises: 010
Create Date: 2026-08-05

008 绩效计算模块：
- 新增 performance_settlements（月度核算批次，period 唯一，审核状态机）。
- commission_results 增加 rule_snapshot（核算时生效绩效规则快照 JSON）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '011'
down_revision: Union[str, None] = '010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "performance_settlements",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("period", sa.String(length=7), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "reviewed", "rejected", name="settlement_status_enum"),
            nullable=False,
        ),
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("reject_reason", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("period", name="uq_performance_settlements_period"),
    )
    op.add_column(
        "commission_results",
        sa.Column("rule_snapshot", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("commission_results", "rule_snapshot")
    op.drop_table("performance_settlements")
