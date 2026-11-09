"""Allow purpose-scoped evidence files for consumption attribution.

Revision ID: 031
Revises: 030
"""

import sqlalchemy as sa
from alembic import op

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


_OLD_PURPOSES = (
    "purpose IN ('product_image','aftersale_proof','invoice_pdf',"
    "'reconciliation_evidence','finance_export')"
)
_NEW_PURPOSES = (
    "purpose IN ('product_image','aftersale_proof','invoice_pdf',"
    "'reconciliation_evidence','finance_export','attribution_evidence')"
)


def upgrade():
    op.drop_constraint("ck_mall_file_purpose", "mall_files", type_="check")
    op.create_check_constraint("ck_mall_file_purpose", "mall_files", _NEW_PURPOSES)


def downgrade():
    used = op.get_bind().scalar(
        sa.text("SELECT COUNT(*) FROM mall_files WHERE purpose = 'attribution_evidence'")
    )
    if used:
        raise RuntimeError("Attribution evidence files exist; refusing a lossy downgrade")
    op.drop_constraint("ck_mall_file_purpose", "mall_files", type_="check")
    op.create_check_constraint("ck_mall_file_purpose", "mall_files", _OLD_PURPOSES)

