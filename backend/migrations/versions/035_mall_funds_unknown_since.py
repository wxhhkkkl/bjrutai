"""Persist the first timestamp for a payment/refund unknown interval.

Revision ID: 035
Revises: 034
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade():
    unknown_since = sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")
    op.add_column("mall_payments", sa.Column("unknown_since", unknown_since, nullable=True))
    op.add_column("mall_refunds", sa.Column("unknown_since", unknown_since, nullable=True))
    op.create_index(
        "ix_mall_payment_unknown", "mall_payments", ["status", "unknown_since"]
    )
    op.create_index("ix_mall_refund_unknown", "mall_refunds", ["status", "unknown_since"])
    op.execute(
        "UPDATE mall_payments SET unknown_since = COALESCE(last_query_at, updated_at, created_at) "
        "WHERE status = 'unknown'"
    )
    op.execute(
        "UPDATE mall_refunds SET unknown_since = COALESCE(last_query_at, updated_at, created_at) "
        "WHERE status = 'unknown'"
    )


def downgrade():
    bind = op.get_bind()
    payment_evidence = bind.scalar(
        sa.text("SELECT COUNT(*) FROM mall_payments WHERE unknown_since IS NOT NULL")
    )
    refund_evidence = bind.scalar(
        sa.text("SELECT COUNT(*) FROM mall_refunds WHERE unknown_since IS NOT NULL")
    )
    if payment_evidence or refund_evidence:
        raise RuntimeError("Unknown funds timing evidence exists; refusing a lossy downgrade")
    op.drop_index("ix_mall_refund_unknown", table_name="mall_refunds")
    op.drop_index("ix_mall_payment_unknown", table_name="mall_payments")
    op.drop_column("mall_refunds", "unknown_since")
    op.drop_column("mall_payments", "unknown_since")
