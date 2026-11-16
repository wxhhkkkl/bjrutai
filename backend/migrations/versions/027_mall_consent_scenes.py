"""Add explicit mall purposes without reusing historic registration consent.

Revision ID: 027
Revises: 026
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None

LEGACY = ("REGISTRATION", "BINDING", "PROMOTION", "FOLLOWUP")
MALL = ("MALL_ADDRESS", "MALL_CHECKOUT")


def upgrade():
    op.alter_column(
        "consent_records",
        "scene",
        existing_type=mysql.ENUM(*LEGACY),
        type_=mysql.ENUM(*LEGACY, *MALL),
        existing_nullable=False,
    )


def downgrade():
    count = op.get_bind().scalar(
        sa.text(
            "SELECT COUNT(*) FROM consent_records WHERE scene IN ('MALL_ADDRESS','MALL_CHECKOUT')"
        )
    )
    if count:
        raise RuntimeError("Mall consent facts exist; refusing a lossy downgrade")
    op.alter_column(
        "consent_records",
        "scene",
        existing_type=mysql.ENUM(*LEGACY, *MALL),
        type_=mysql.ENUM(*LEGACY),
        existing_nullable=False,
    )
