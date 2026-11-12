"""Add product delivery and freight templates."""

import sqlalchemy as sa
from alembic import op

revision = "041"
down_revision = "040"
branch_labels = None
depends_on = None


def upgrade():
    for table, column, kind in (
        ("mall_settings", "freight_templates", sa.JSON()),
        ("mall_products", "delivery_method", sa.String(16)),
        ("mall_products", "freight_template_id", sa.String(32)),
    ):
        if column not in {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table)}:
            op.add_column(table, sa.Column(column, kind, nullable=True))


def downgrade():
    raise RuntimeError("Downgrade would discard product delivery and freight templates")
