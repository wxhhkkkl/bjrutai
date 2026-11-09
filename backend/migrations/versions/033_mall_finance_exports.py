"""Persist bounded finance export requests and their private file reference.

Revision ID: 033
Revises: 032
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mall_finance_export_requests",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("from_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("to_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("status_filter", sa.String(24), nullable=True),
        sa.Column("format", sa.String(8), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("requested_by", sa.Integer(), nullable=False),
        sa.Column("command_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("file_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("completed_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.ForeignKeyConstraint(
            ["requested_by"], ["admin_accounts.id"],
            name="fk_mall_finance_export_admin", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["command_id"], ["mall_commands.id"],
            name="fk_mall_finance_export_command", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["file_id"], ["mall_files.id"],
            name="fk_mall_finance_export_file", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("command_id", name="uq_mall_finance_export_command"),
        sa.UniqueConstraint("file_id", name="uq_mall_finance_export_file"),
        sa.CheckConstraint("kind IN ('payments','refunds')", name="ck_mall_finance_export_kind"),
        sa.CheckConstraint("format IN ('csv','xlsx')", name="ck_mall_finance_export_format"),
        sa.CheckConstraint(
            "status IN ('queued','processing','ready','failed')",
            name="ck_mall_finance_export_status",
        ),
        sa.CheckConstraint("from_at < to_at", name="ck_mall_finance_export_range"),
        sa.CheckConstraint(
            "row_count IS NULL OR row_count >= 0", name="ck_mall_finance_export_rows"
        ),
    )
    op.create_index(
        "ix_mall_finance_export_status",
        "mall_finance_export_requests",
        ["status", "created_at", "id"],
    )


def downgrade():
    count = op.get_bind().scalar(sa.text("SELECT COUNT(*) FROM mall_finance_export_requests"))
    if count:
        raise RuntimeError("Mall finance export requests exist; refusing a lossy downgrade")
    op.drop_index("ix_mall_finance_export_status", table_name="mall_finance_export_requests")
    op.drop_table("mall_finance_export_requests")
