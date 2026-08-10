"""Feedback domain models.

Feedback is intentionally separate from AuditLog: AuditLog remains a security
record while these tables are the queryable business source of truth.
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class Feedback(Base):
    __tablename__ = "feedbacks"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_feedbacks_user_idempotency"),
        UniqueConstraint("source_audit_log_id", name="uq_feedbacks_source_audit_log"),
        Index("ix_feedbacks_status_created", "status", "created_at", "id"),
        Index("ix_feedbacks_type_created", "type", "created_at", "id"),
        Index("ix_feedbacks_user_created", "user_id", "created_at", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feedback_no: Mapped[str] = mapped_column(String(40), nullable=False, unique=True, index=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    submitter_name_snapshot: Mapped[str | None] = mapped_column(String(100), nullable=True)
    submitter_phone_masked_snapshot: Mapped[str | None] = mapped_column(String(20), nullable=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    image_files: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="submitted")
    first_handler_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("admin_accounts.id", ondelete="SET NULL"), nullable=True
    )
    first_handled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("admin_accounts.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    submission_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_audit_log_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("audit_logs.id", ondelete="SET NULL"), nullable=True
    )
    notification_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="not_required"
    )
    notification_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notification_next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notification_last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notification_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class FeedbackAction(Base):
    __tablename__ = "feedback_actions"
    __table_args__ = (
        Index("ix_feedback_actions_feedback_created", "feedback_id", "created_at", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feedback_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("feedbacks.id", ondelete="CASCADE"), nullable=False
    )
    operator_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("admin_accounts.id", ondelete="SET NULL"), nullable=True
    )
    operator_name_snapshot: Mapped[str] = mapped_column(String(100), nullable=False)
    action_type: Mapped[str] = mapped_column(String(20), nullable=False)
    from_status: Mapped[str] = mapped_column(String(20), nullable=False)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    internal_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    version_before: Mapped[int] = mapped_column(Integer, nullable=False)
    version_after: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
