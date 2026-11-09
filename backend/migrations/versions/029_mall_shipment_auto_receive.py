"""Snapshot the local automatic receipt deadline on each shipment.

Revision ID: 029
Revises: 028
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "mall_shipments",
        sa.Column("auto_receive_at", mysql.DATETIME(fsp=6), nullable=True),
    )


def downgrade():
    count = op.get_bind().scalar(
        sa.text("SELECT COUNT(*) FROM mall_shipments WHERE auto_receive_at IS NOT NULL")
    )
    if count:
        raise RuntimeError("Automatic receipt deadlines exist; refusing a lossy downgrade")
    op.drop_column("mall_shipments", "auto_receive_at")
