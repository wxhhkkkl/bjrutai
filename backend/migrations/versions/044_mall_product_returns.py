"""Add product-level return settings."""

import sqlalchemy as sa
from alembic import op

revision = "044"
down_revision = "043"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "mall_products",
        sa.Column("supports_return", sa.Boolean(), nullable=False, server_default="1"),
    )
    op.add_column(
        "mall_products",
        sa.Column("return_instructions", sa.String(2000), nullable=False, server_default=""),
    )


def downgrade():
    if op.get_bind().scalar(
        sa.text("SELECT COUNT(*) FROM mall_products WHERE supports_return = 0 OR return_instructions <> ''")
    ):
        raise RuntimeError("Product return settings exist; refusing a lossy downgrade")
    op.drop_column("mall_products", "return_instructions")
    op.drop_column("mall_products", "supports_return")
