"""Persist physical or virtual product type."""

import sqlalchemy as sa
from alembic import op

revision = "042"
down_revision = "041"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {item["name"] for item in inspector.get_columns("mall_products")}
    if "product_type" not in columns:
        op.add_column(
            "mall_products",
            sa.Column(
                "product_type",
                sa.String(16),
                nullable=False,
                server_default="physical",
            ),
        )
        op.execute(
            sa.text(
                "UPDATE mall_products "
                "SET product_type = CASE "
                "WHEN delivery_method = 'virtual' THEN 'virtual' "
                "ELSE 'physical' END"
            )
        )
    constraints = {item["name"] for item in inspector.get_check_constraints("mall_products")}
    if "ck_mall_product_type" not in constraints:
        op.create_check_constraint(
            "ck_mall_product_type",
            "mall_products",
            "product_type IN ('physical','virtual')",
        )


def downgrade():
    raise RuntimeError("Downgrade would discard product types")
