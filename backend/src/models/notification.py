import enum
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base

if TYPE_CHECKING:
    from .user import User


class NotificationCategory(str, enum.Enum):
    SYSTEM = "system"
    BINDING = "binding"
    PROMOTION = "promotion"
    BILL = "bill"
    FOLLOWUP = "followup"
    QUALIFICATION = "qualification"
    MALL = "mall"


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("uq_notifications_event_key", "event_key", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    category: Mapped[NotificationCategory] = mapped_column(
        SAEnum(NotificationCategory, name="notification_category_enum"),
        nullable=False,
    )
    event_key: Mapped[Optional[str]] = mapped_column(String(191), nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    target: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    feedback_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("feedbacks.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
        index=True,
    )
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="notifications")
