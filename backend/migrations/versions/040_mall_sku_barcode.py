"""Store optional product barcodes per specification."""

import sqlalchemy as sa
from alembic import op

revision = "040"
down_revision = "039"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("mall_skus", sa.Column("barcode", sa.String(64), nullable=True))


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT COUNT(*) FROM mall_skus WHERE barcode IS NOT NULL")):
        raise RuntimeError("Mall SKU barcodes exist; refusing a lossy downgrade")
    op.drop_column("mall_skus", "barcode")
