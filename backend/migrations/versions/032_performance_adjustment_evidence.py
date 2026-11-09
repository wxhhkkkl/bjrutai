"""Persist evidence files attached to manual performance adjustments.

Revision ID: 032
Revises: 031
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


_PURPOSES_WITHOUT_PERFORMANCE_EVIDENCE = (
    "purpose IN ('product_image','aftersale_proof','invoice_pdf',"
    "'reconciliation_evidence','finance_export','attribution_evidence')"
)
_PURPOSES_WITH_PERFORMANCE_EVIDENCE = (
    "purpose IN ('product_image','aftersale_proof','invoice_pdf',"
    "'reconciliation_evidence','finance_export','attribution_evidence',"
    "'performance_adjustment_evidence')"
)


def upgrade():
    op.drop_constraint("ck_mall_file_purpose", "mall_files", type_="check")
    op.create_check_constraint(
        "ck_mall_file_purpose", "mall_files", _PURPOSES_WITH_PERFORMANCE_EVIDENCE
    )
    op.add_column(
        "performance_adjustments",
        sa.Column("evidence_file_ids", mysql.JSON(), nullable=True),
    )
    op.execute(
        "UPDATE performance_adjustments "
        "SET evidence_file_ids = JSON_ARRAY() WHERE evidence_file_ids IS NULL"
    )
    op.alter_column(
        "performance_adjustments",
        "evidence_file_ids",
        existing_type=mysql.JSON(),
        nullable=False,
    )


def downgrade():
    file_count = op.get_bind().scalar(
        sa.text(
            "SELECT COUNT(*) FROM mall_files " "WHERE purpose = 'performance_adjustment_evidence'"
        )
    )
    if file_count:
        raise RuntimeError("Performance adjustment evidence exists; refusing a lossy downgrade")
    op.drop_column("performance_adjustments", "evidence_file_ids")
    op.drop_constraint("ck_mall_file_purpose", "mall_files", type_="check")
    op.create_check_constraint(
        "ck_mall_file_purpose", "mall_files", _PURPOSES_WITHOUT_PERFORMANCE_EVIDENCE
    )
