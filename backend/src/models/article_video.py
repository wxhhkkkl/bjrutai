"""Application-authorized VOD media, including uploads awaiting an article."""

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class VideoStatus(str, enum.Enum):
    AUTHORIZED = "authorized"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    DELETING = "deleting"
    DELETED = "deleted"


class ArticleVideo(Base):
    __tablename__ = "article_videos"
    __table_args__ = (Index("ix_article_videos_cleanup", "status", "unbound_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    upload_session_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    uploaded_by_admin_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("admin_accounts.id"), nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)
    declared_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    actual_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    vod_sub_app_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    file_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    procedure_task_id: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[VideoStatus] = mapped_column(
        Enum(
            VideoStatus,
            values_callable=lambda values: [v.value for v in values],
            name="article_video_status",
        ),
        default=VideoStatus.AUTHORIZED,
        nullable=False,
    )
    ownership_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    upload_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime)
    processing_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime)
    playback_url: Mapped[str | None] = mapped_column(String(2048))
    poster_url: Mapped[str | None] = mapped_column(String(2048))
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    failure_message: Mapped[str | None] = mapped_column(String(255))
    unbound_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.utcnow)
    cloud_deleted_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
