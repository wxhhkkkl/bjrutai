"""Persist order close intent independently of payment outcome.

Revision ID: 028
Revises: 027
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "mall_orders", sa.Column("close_requested_at", mysql.DATETIME(fsp=6), nullable=True)
    )
    op.add_column("mall_orders", sa.Column("close_request_reason", sa.String(500), nullable=True))


def downgrade():
    count = op.get_bind().scalar(
        sa.text(
            "SELECT COUNT(*) FROM mall_orders WHERE close_requested_at IS NOT NULL "
            "OR close_request_reason IS NOT NULL"
        )
    )
    if count:
        raise RuntimeError("Order close intent facts exist; refusing a lossy downgrade")
    op.drop_column("mall_orders", "close_request_reason")
    op.drop_column("mall_orders", "close_requested_at")
