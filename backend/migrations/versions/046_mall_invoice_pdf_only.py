"""Allow registering an invoice PDF without re-entering its printed fields."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "046"
down_revision = "045"
branch_labels = None
depends_on = None


def upgrade():
    timestamp = sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")
    with op.batch_alter_table("mall_invoices") as batch_op:
        batch_op.alter_column(
            "seller_identity", existing_type=sa.String(64), nullable=True
        )
        batch_op.alter_column("invoice_no", existing_type=sa.String(64), nullable=True)
        batch_op.alter_column("issued_at", existing_type=timestamp, nullable=True)


def downgrade():
    bind = op.get_bind()
    missing_metadata = bind.scalar(
        sa.text(
            "SELECT COUNT(*) FROM mall_invoices "
            "WHERE seller_identity IS NULL OR invoice_no IS NULL OR issued_at IS NULL"
        )
    )
    if missing_metadata:
        raise RuntimeError("PDF-only invoice records exist; refusing a lossy downgrade")

    timestamp = sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")
    with op.batch_alter_table("mall_invoices") as batch_op:
        batch_op.alter_column(
            "seller_identity", existing_type=sa.String(64), nullable=False
        )
        batch_op.alter_column("invoice_no", existing_type=sa.String(64), nullable=False)
        batch_op.alter_column("issued_at", existing_type=timestamp, nullable=False)
