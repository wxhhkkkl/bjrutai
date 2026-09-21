"""Article comment persistence models."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class ArticleComment(Base):
    __tablename__ = "article_comments"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_article_comments_user_idempotency",
        ),
        Index(
            "ix_article_comments_public_order",
            "article_id",
            "status",
            "is_pinned",
            "created_at",
            "id",
        ),
        Index(
            "ix_article_comments_status_created",
            "status",
            "created_at",
            "id",
        ),
        Index(
            "ix_article_comments_deleted_at",
            "status",
            "deleted_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    article_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("articles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    display_name_snapshot: Mapped[str] = mapped_column(
        String(100), nullable=False, default="儒泰用户"
    )
    avatar_url_snapshot: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    moderation_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    moderation_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    moderation_rule_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    moderation_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    moderation_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_pinned: Mapped[bool] = mapped_column(nullable=False, default=False)
    like_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    submission_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
