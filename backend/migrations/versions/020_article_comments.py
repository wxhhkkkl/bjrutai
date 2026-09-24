"""add article comments, likes and comment action timeline

Revision ID: 020
Revises: 019
Create Date: 2026-09-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COMMENT_TABLES = {"article_comments", "comment_likes", "comment_actions"}
INDEX_NAMES = {
    "ix_article_comments_public_order",
    "ix_article_comments_status_created",
    "ix_article_comments_deleted_at",
    "ix_comment_likes_user_comment",
    "ix_comment_actions_comment_created",
    "ix_comment_actions_type_created",
}
CONSTRAINT_NAMES = {
    "uq_article_comments_user_idempotency",
    "uq_comment_likes_comment_user",
}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("article_comments"):
        op.create_table(
            "article_comments",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("article_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("display_name_snapshot", sa.String(length=100), nullable=False),
            sa.Column("avatar_url_snapshot", sa.String(length=500), nullable=True),
            sa.Column("content", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column(
                "moderation_status",
                sa.String(length=20),
                nullable=False,
                server_default="pending",
            ),
            sa.Column("moderation_category", sa.String(length=32), nullable=True),
            sa.Column("moderation_rule_version", sa.String(length=32), nullable=True),
            sa.Column("moderation_checked_at", sa.DateTime(), nullable=True),
            sa.Column("moderation_reason", sa.String(length=255), nullable=True),
            sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("like_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("hidden_at", sa.DateTime(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
            sa.Column("idempotency_key", sa.String(length=128), nullable=True),
            sa.Column("submission_fingerprint", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["article_id"], ["articles.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "user_id",
                "idempotency_key",
                name="uq_article_comments_user_idempotency",
            ),
        )

    existing_indexes = {item["name"] for item in sa.inspect(bind).get_indexes("article_comments")}
    if "ix_article_comments_public_order" not in existing_indexes:
        op.create_index(
            "ix_article_comments_public_order",
            "article_comments",
            ["article_id", "status", "is_pinned", "created_at", "id"],
        )
    if "ix_article_comments_status_created" not in existing_indexes:
        op.create_index(
            "ix_article_comments_status_created",
            "article_comments",
            ["status", "created_at", "id"],
        )
    if "ix_article_comments_deleted_at" not in existing_indexes:
        op.create_index(
            "ix_article_comments_deleted_at",
            "article_comments",
            ["status", "deleted_at"],
        )

    if not inspector.has_table("comment_likes"):
        op.create_table(
            "comment_likes",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("comment_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["comment_id"], ["article_comments.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "comment_id",
                "user_id",
                name="uq_comment_likes_comment_user",
            ),
        )
    existing_indexes = {item["name"] for item in sa.inspect(bind).get_indexes("comment_likes")}
    if "ix_comment_likes_user_comment" not in existing_indexes:
        op.create_index(
            "ix_comment_likes_user_comment",
            "comment_likes",
            ["user_id", "comment_id"],
        )

    if not inspector.has_table("comment_actions"):
        op.create_table(
            "comment_actions",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("comment_id", sa.Integer(), nullable=False),
            sa.Column("operator_admin_id", sa.Integer(), nullable=True),
            sa.Column("operator_name_snapshot", sa.String(length=100), nullable=False),
            sa.Column("action_type", sa.String(length=24), nullable=False),
            sa.Column("from_status", sa.String(length=20), nullable=False),
            sa.Column("to_status", sa.String(length=20), nullable=False),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("moderation_rule_version", sa.String(length=32), nullable=True),
            sa.Column("version_before", sa.Integer(), nullable=False),
            sa.Column("version_after", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["comment_id"], ["article_comments.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["operator_admin_id"],
                ["admin_accounts.id"],
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
    existing_indexes = {item["name"] for item in sa.inspect(bind).get_indexes("comment_actions")}
    if "ix_comment_actions_comment_created" not in existing_indexes:
        op.create_index(
            "ix_comment_actions_comment_created",
            "comment_actions",
            ["comment_id", "created_at", "id"],
        )
    if "ix_comment_actions_type_created" not in existing_indexes:
        op.create_index(
            "ix_comment_actions_type_created",
            "comment_actions",
            ["action_type", "created_at"],
        )


def downgrade() -> None:
    op.drop_index("ix_comment_actions_type_created", table_name="comment_actions")
    op.drop_index("ix_comment_actions_comment_created", table_name="comment_actions")
    op.drop_table("comment_actions")
    op.drop_index("ix_comment_likes_user_comment", table_name="comment_likes")
    op.drop_table("comment_likes")
    op.drop_index("ix_article_comments_deleted_at", table_name="article_comments")
    op.drop_index("ix_article_comments_status_created", table_name="article_comments")
    op.drop_index("ix_article_comments_public_order", table_name="article_comments")
    op.drop_table("article_comments")
