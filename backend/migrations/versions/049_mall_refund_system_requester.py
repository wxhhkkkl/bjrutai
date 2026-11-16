"""Allow policy-queued refunds that have no admin requester."""

import sqlalchemy as sa
from alembic import op

revision = "049"
down_revision = "048"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "mall_refunds",
        "requested_by",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade():
    if op.get_bind().scalar(
        sa.text("SELECT COUNT(*) FROM mall_refunds WHERE requested_by IS NULL")
    ):
        raise RuntimeError("System-requested refunds exist; refusing a lossy downgrade")
    op.alter_column(
        "mall_refunds",
        "requested_by",
        existing_type=sa.Integer(),
        nullable=False,
    )
