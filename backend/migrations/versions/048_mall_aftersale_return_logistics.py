"""Cache return-shipment maps and tracks per aftersale without new tables."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "048"
down_revision = "047"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "mall_aftersales",
        sa.Column(
            "return_logistics_provider",
            sa.String(32),
            nullable=False,
            server_default="kuaidi100",
        ),
    )
    op.add_column(
        "mall_aftersales",
        sa.Column(
            "return_logistics_status",
            sa.String(24),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "mall_aftersales",
        sa.Column(
            "return_logistics_snapshot",
            mysql.JSON(),
            nullable=False,
            server_default=sa.text("(JSON_OBJECT())"),
        ),
    )
    op.add_column(
        "mall_aftersales",
        sa.Column("return_logistics_fetched_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "mall_aftersales",
        sa.Column("return_logistics_next_query_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "mall_aftersales",
        sa.Column("return_logistics_last_error_code", sa.String(64), nullable=True),
    )


def downgrade():
    if op.get_bind().scalar(
        sa.text(
            "SELECT COUNT(*) FROM mall_aftersales WHERE return_logistics_fetched_at IS NOT NULL"
        )
    ):
        raise RuntimeError("Return logistics snapshots exist; refusing a lossy downgrade")
    op.drop_column("mall_aftersales", "return_logistics_last_error_code")
    op.drop_column("mall_aftersales", "return_logistics_next_query_at")
    op.drop_column("mall_aftersales", "return_logistics_fetched_at")
    op.drop_column("mall_aftersales", "return_logistics_snapshot")
    op.drop_column("mall_aftersales", "return_logistics_status")
    op.drop_column("mall_aftersales", "return_logistics_provider")
