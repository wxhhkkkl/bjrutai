"""Link explicit invoice-purpose acknowledgement to each application.

Revision ID: 034
Revises: 033
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None

LEGACY = ("REGISTRATION", "BINDING", "PROMOTION", "FOLLOWUP")
MALL = ("MALL_ADDRESS", "MALL_CHECKOUT")
INVOICE = ("MALL_INVOICE",)


def upgrade():
    op.alter_column(
        "consent_records",
        "scene",
        existing_type=mysql.ENUM(*LEGACY, *MALL),
        type_=mysql.ENUM(*LEGACY, *MALL, *INVOICE),
        existing_nullable=False,
    )
    op.add_column(
        "mall_invoice_requests",
        sa.Column("consent_record_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_mall_invoice_consent",
        "mall_invoice_requests",
        "consent_records",
        ["consent_record_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade():
    bind = op.get_bind()
    invoice_consents = bind.scalar(
        sa.text("SELECT COUNT(*) FROM consent_records WHERE scene = 'MALL_INVOICE'")
    )
    linked_requests = bind.scalar(
        sa.text("SELECT COUNT(*) FROM mall_invoice_requests WHERE consent_record_id IS NOT NULL")
    )
    if invoice_consents or linked_requests:
        raise RuntimeError("Mall invoice consent evidence exists; refusing a lossy downgrade")
    op.drop_constraint("fk_mall_invoice_consent", "mall_invoice_requests", type_="foreignkey")
    op.drop_column("mall_invoice_requests", "consent_record_id")
    op.alter_column(
        "consent_records",
        "scene",
        existing_type=mysql.ENUM(*LEGACY, *MALL, *INVOICE),
        type_=mysql.ENUM(*LEGACY, *MALL),
        existing_nullable=False,
    )
