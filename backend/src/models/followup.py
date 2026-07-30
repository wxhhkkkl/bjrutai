import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base


class FollowupMethod(str, enum.Enum):
    PHONE = "phone"
    WECHAT = "wechat"
    VISIT = "visit"
    OTHER = "other"


class FollowupResult(str, enum.Enum):
    SUCCESSFUL = "successful"
    FAILED = "failed"
    PENDING = "pending"
    NO_ANSWER = "no_answer"


class ReminderStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    CANCELLED = "cancelled"


class FollowupRecord(Base):
    __tablename__ = "followup_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    doctor_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    method: Mapped[FollowupMethod] = mapped_column(
        SAEnum(FollowupMethod, name="followup_method_enum"), nullable=False
    )
    result: Mapped[FollowupResult] = mapped_column(
        SAEnum(FollowupResult, name="followup_result_enum"),
        default=FollowupResult.PENDING,
    )
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reminder_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    reminder_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reminder_status: Mapped[ReminderStatus] = mapped_column(
        SAEnum(ReminderStatus, name="reminder_status_enum"), default=ReminderStatus.PENDING
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    customer: Mapped["Customer"] = relationship("Customer", back_populates="followup_records")
