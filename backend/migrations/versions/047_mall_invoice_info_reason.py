"""Keep the buyer-facing note written when finance asks for more invoice information."""

import sqlalchemy as sa
from alembic import op

revision = "047"
down_revision = "046"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("mall_invoice_requests") as batch_op:
        batch_op.add_column(
            sa.Column("info_request_reason", sa.String(500), nullable=True)
        )


def downgrade():
    with op.batch_alter_table("mall_invoice_requests") as batch_op:
        batch_op.drop_column("info_request_reason")
