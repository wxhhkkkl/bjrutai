"""Persist manual fulfillment content for virtual mall orders."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "045"
down_revision = "044"
branch_labels = None
depends_on = None


def upgrade():
    mall_id = (
        sa.BigInteger()
        .with_variant(mysql.BIGINT(unsigned=True), "mysql")
        .with_variant(sa.Integer(), "sqlite")
    )
    timestamp = sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")
    op.create_table(
        "mall_virtual_deliveries",
        sa.Column("id", mall_id, primary_key=True, autoincrement=True),
        sa.Column("created_at", timestamp, nullable=False),
        sa.Column("updated_at", timestamp, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("order_id", mall_id, nullable=False),
        sa.Column("delivery_content", sa.Text(), nullable=False),
        sa.Column("delivered_by", sa.Integer(), nullable=False),
        sa.Column("delivered_at", timestamp, nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["mall_orders.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["delivered_by"], ["admin_accounts.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("order_id", name="uq_mall_virtual_delivery_order"),
    )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "mall_virtual_deliveries" not in inspector.get_table_names():
        return
    if bind.scalar(sa.text("SELECT COUNT(*) FROM mall_virtual_deliveries")):
        raise RuntimeError("Virtual delivery records exist; refusing a lossy downgrade")
    op.drop_table("mall_virtual_deliveries")
