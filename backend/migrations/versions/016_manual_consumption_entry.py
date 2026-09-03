"""Add manual consumption metadata to bills.

Revision ID: 016
Revises: 015
Create Date: 2026-09-03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Batch mode is a no-op-style ALTER on MySQL and safely recreates the table
    # on SQLite, which keeps the migration testable against an isolated DB.
    with op.batch_alter_table("bills") as batch_op:
        batch_op.add_column(
            sa.Column("source", sa.String(20), nullable=False, server_default="rutai_sync"),
        )
        batch_op.add_column(sa.Column("attributed_distributor_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("attributed_person_name", sa.String(100), nullable=True))
        batch_op.add_column(sa.Column("attributed_org_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("attributed_org_name", sa.String(128), nullable=True))
        batch_op.add_column(sa.Column("entry_note", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("created_by_admin_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("idempotency_key", sa.String(128), nullable=True))
        batch_op.add_column(sa.Column("submission_fingerprint", sa.String(64), nullable=True))
        batch_op.create_foreign_key(
            "fk_bills_created_by_admin_id",
            "admin_accounts",
            ["created_by_admin_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_unique_constraint(
            "uq_bills_admin_idempotency",
            ["created_by_admin_id", "idempotency_key"],
        )
        batch_op.create_index(
            "ix_bills_source_created",
            ["source", "created_at", "id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("bills") as batch_op:
        batch_op.drop_index("ix_bills_source_created")
        batch_op.drop_constraint("uq_bills_admin_idempotency", type_="unique")
        batch_op.drop_constraint("fk_bills_created_by_admin_id", type_="foreignkey")
        batch_op.drop_column("submission_fingerprint")
        batch_op.drop_column("idempotency_key")
        batch_op.drop_column("created_by_admin_id")
        batch_op.drop_column("entry_note")
        batch_op.drop_column("attributed_org_name")
        batch_op.drop_column("attributed_org_id")
        batch_op.drop_column("attributed_person_name")
        batch_op.drop_column("attributed_distributor_id")
        batch_op.drop_column("source")
