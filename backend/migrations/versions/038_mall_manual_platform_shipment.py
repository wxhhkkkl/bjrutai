"""Track manual WeChat backend shipping reports separately from local dispatch.

Revision ID: 038
Revises: 037
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "038"
down_revision = "037"
branch_labels = None
depends_on = None


def _time_type(bind):
    if bind.dialect.name in {"mysql", "mariadb"}:
        return mysql.DATETIME(fsp=6)
    return sa.DateTime()


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {item["name"] for item in inspector.get_columns("mall_shipments")}
    if "platform_report_status" not in columns:
        op.add_column(
            "mall_shipments",
            sa.Column(
                "platform_report_status",
                sa.String(24),
                nullable=False,
                server_default="unknown",
            ),
        )
    if "platform_reported_at" not in columns:
        op.add_column(
            "mall_shipments",
            sa.Column("platform_reported_at", _time_type(bind), nullable=True),
        )
    constraints = {item["name"] for item in inspector.get_check_constraints("mall_shipments")}
    if "ck_mall_shipment_platform_report_status" not in constraints:
        op.create_check_constraint(
            "ck_mall_shipment_platform_report_status",
            "mall_shipments",
            "platform_report_status IN ('pending','manual_reported','unknown')",
        )
    indexes = {item["name"] for item in inspector.get_indexes("mall_shipments")}
    if "ix_mall_shipments_platform_report_status" not in indexes:
        op.create_index(
            "ix_mall_shipments_platform_report_status",
            "mall_shipments",
            ["platform_report_status"],
        )


def downgrade():
    bind = op.get_bind()
    if bind.scalar(
        sa.text(
            "SELECT COUNT(*) FROM mall_shipments "
            "WHERE platform_report_status = 'manual_reported' "
            "OR platform_reported_at IS NOT NULL"
        )
    ):
        raise RuntimeError("Manual WeChat shipping reports exist; refusing to discard them")
    op.drop_constraint(
        "ck_mall_shipment_platform_report_status", "mall_shipments", type_="check"
    )
    op.drop_index("ix_mall_shipments_platform_report_status", table_name="mall_shipments")
    op.drop_column("mall_shipments", "platform_reported_at")
    op.drop_column("mall_shipments", "platform_report_status")
