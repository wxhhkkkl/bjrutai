"""Add homepage banner management table.

Revision ID: 017
Revises: 016
Create Date: 2026-09-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("banners"):
        op.create_table(
            "banners",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("title", sa.String(length=100), nullable=True),
            sa.Column("image_url", sa.String(length=2048), nullable=False),
            sa.Column(
                "action_type",
                sa.Enum("none", "article", name="banner_action_type_enum"),
                nullable=False,
                server_default="none",
            ),
            sa.Column("article_id", sa.Integer(), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column(
                "status",
                sa.Enum("enabled", "disabled", name="banner_status_enum"),
                nullable=False,
                server_default="disabled",
            ),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("banners")}
    if "ix_banners_public_order" not in indexes:
        op.create_index("ix_banners_public_order", "banners", ["status", "sort_order", "id"])


def downgrade() -> None:
    op.drop_index("ix_banners_public_order", table_name="banners")
    op.drop_table("banners")
