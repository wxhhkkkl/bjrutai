"""Article VOD upload sessions and a nullable single-video article relation.

Revision ID: 023
Revises: 022
"""

import sqlalchemy as sa
from alembic import op

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "article_videos" not in existing_tables:
        op.create_table(
            "article_videos",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("upload_session_id", sa.String(36), nullable=False),
            sa.Column(
                "uploaded_by_admin_id",
                sa.Integer(),
                sa.ForeignKey("admin_accounts.id"),
                nullable=False,
            ),
            sa.Column("file_name", sa.String(255), nullable=False),
            sa.Column("content_type", sa.String(50), nullable=False),
            sa.Column("declared_size_bytes", sa.BigInteger(), nullable=False),
            sa.Column("actual_size_bytes", sa.BigInteger()),
            sa.Column("vod_sub_app_id", sa.BigInteger(), nullable=False),
            sa.Column("file_id", sa.String(100)),
            sa.Column("procedure_task_id", sa.String(255)),
            sa.Column(
                "status",
                sa.Enum(
                    "authorized",
                    "processing",
                    "ready",
                    "failed",
                    "deleting",
                    "deleted",
                    name="article_video_status",
                ),
                nullable=False,
            ),
            sa.Column("ownership_verified", sa.Boolean(), nullable=False),
            sa.Column("upload_confirmed_at", sa.DateTime()),
            sa.Column("processing_confirmed_at", sa.DateTime()),
            sa.Column("playback_url", sa.String(2048)),
            sa.Column("poster_url", sa.String(2048)),
            sa.Column("duration_seconds", sa.Float()),
            sa.Column("failure_message", sa.String(255)),
            sa.Column("unbound_at", sa.DateTime()),
            sa.Column("cloud_deleted_at", sa.DateTime()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("upload_session_id", name="uq_article_videos_session"),
            sa.UniqueConstraint("file_id", name="uq_article_videos_file"),
        )
        inspector = sa.inspect(bind)

    actual_columns = {column["name"] for column in inspector.get_columns("article_videos")}
    required_columns = {
        "id",
        "upload_session_id",
        "uploaded_by_admin_id",
        "file_name",
        "content_type",
        "declared_size_bytes",
        "actual_size_bytes",
        "vod_sub_app_id",
        "file_id",
        "procedure_task_id",
        "status",
        "ownership_verified",
        "upload_confirmed_at",
        "processing_confirmed_at",
        "playback_url",
        "poster_url",
        "duration_seconds",
        "failure_message",
        "unbound_at",
        "cloud_deleted_at",
        "created_at",
        "updated_at",
    }
    if not required_columns.issubset(actual_columns):
        raise RuntimeError("Existing article_videos table does not match migration 023")

    existing_indexes = {index["name"] for index in inspector.get_indexes("article_videos")}
    if "ix_article_videos_cleanup" not in existing_indexes:
        op.create_index("ix_article_videos_cleanup", "article_videos", ["status", "unbound_at"])

    article_columns = {column["name"] for column in inspector.get_columns("articles")}
    article_uniques = {
        constraint["name"] for constraint in inspector.get_unique_constraints("articles")
    }
    article_foreign_keys = {
        constraint["name"] for constraint in inspector.get_foreign_keys("articles")
    }
    with op.batch_alter_table("articles") as batch:
        if "video_id" not in article_columns:
            batch.add_column(sa.Column("video_id", sa.Integer(), nullable=True))
        if "uq_articles_video_id" not in article_uniques:
            batch.create_unique_constraint("uq_articles_video_id", ["video_id"])
        if "fk_articles_video_id" not in article_foreign_keys:
            batch.create_foreign_key(
                "fk_articles_video_id",
                "article_videos",
                ["video_id"],
                ["id"],
                ondelete="RESTRICT",
            )


def downgrade():
    with op.batch_alter_table("articles") as batch:
        batch.drop_constraint("fk_articles_video_id", type_="foreignkey")
        batch.drop_constraint("uq_articles_video_id", type_="unique")
        batch.drop_column("video_id")
    op.drop_index("ix_article_videos_cleanup", table_name="article_videos")
    op.drop_table("article_videos")
