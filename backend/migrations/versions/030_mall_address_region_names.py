"""Store non-sensitive administrative labels for buyer address selection.

Revision ID: 030
Revises: 029
"""

import sqlalchemy as sa
from alembic import op

revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("mall_addresses", sa.Column("region_names", sa.JSON(), nullable=True))


def downgrade():
    count = op.get_bind().scalar(
        sa.text("SELECT COUNT(*) FROM mall_addresses WHERE region_names IS NOT NULL")
    )
    if count:
        raise RuntimeError("Buyer region labels exist; refusing a lossy downgrade")
    op.drop_column("mall_addresses", "region_names")
