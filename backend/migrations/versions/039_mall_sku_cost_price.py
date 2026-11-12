"""Store optional cost prices on mall SKUs.

Revision ID: 039
Revises: 038
"""

import sqlalchemy as sa
from alembic import op

revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {item["name"] for item in inspector.get_columns("mall_skus")}
    if "cost_price_cent" not in columns:
        op.add_column(
            "mall_skus",
            sa.Column("cost_price_cent", sa.BigInteger(), nullable=True),
        )
    constraints = {item["name"] for item in inspector.get_check_constraints("mall_skus")}
    if "ck_mall_sku_cost_price" not in constraints:
        op.create_check_constraint(
            "ck_mall_sku_cost_price",
            "mall_skus",
            "cost_price_cent IS NULL OR cost_price_cent >= 0",
        )


def downgrade():
    bind = op.get_bind()
    columns = {item["name"] for item in sa.inspect(bind).get_columns("mall_skus")}
    if "cost_price_cent" not in columns:
        return
    if bind.scalar(sa.text("SELECT COUNT(*) FROM mall_skus WHERE cost_price_cent IS NOT NULL")):
        raise RuntimeError("Mall SKU cost prices exist; refusing a lossy downgrade")
    constraints = {item["name"] for item in sa.inspect(bind).get_check_constraints("mall_skus")}
    if "ck_mall_sku_cost_price" in constraints:
        op.drop_constraint("ck_mall_sku_cost_price", "mall_skus", type_="check")
    op.drop_column("mall_skus", "cost_price_cent")
