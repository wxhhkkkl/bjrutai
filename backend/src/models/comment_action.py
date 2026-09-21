"""Business timeline for automatic and administrator comment actions."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class CommentAction(Base):
    __tablename__ = "comment_actions"
    __table_args__ = (
        Index("ix_comment_actions_comment_created", "comment_id", "created_at", "id"),
        Index("ix_comment_actions_type_created", "action_type", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    comment_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("article_comments.id", ondelete="CASCADE"),
        nullable=False,
    )
    operator_admin_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("admin_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    operator_name_snapshot: Mapped[str] = mapped_column(
        String(100), nullable=False, default="系统"
    )
    action_type: Mapped[str] = mapped_column(String(24), nullable=False)
    from_status: Mapped[str] = mapped_column(String(20), nullable=False)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    moderation_rule_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    version_before: Mapped[int] = mapped_column(Integer, nullable=False)
    version_after: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
