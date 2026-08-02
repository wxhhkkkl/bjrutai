import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base


class ContributionStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SETTLED = "settled"
    REVERSED = "reversed"
    CANCELLED = "cancelled"


class ContributionCategory(str, enum.Enum):
    BINDING = "binding"
    SERVICE = "service"
    FOLLOWUP = "followup"
    BILL = "bill"
    ADJUSTMENT = "adjustment"


class SettlementStatus(str, enum.Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ContributionRecord(Base):
    __tablename__ = "contribution_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    distributor_id: Mapped[int] = mapped_column(Integer, ForeignKey("distributors.id"), nullable=False, index=True)
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id"), nullable=False)
    bill_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("bills.id"), nullable=True)
    points: Mapped[str] = mapped_column(String(20), default="0.00")
    status: Mapped[ContributionStatus] = mapped_column(
        SAEnum(ContributionStatus, name="contribution_status_enum"),
        default=ContributionStatus.PENDING,
    )
    category: Mapped[ContributionCategory] = mapped_column(
        SAEnum(ContributionCategory, name="contribution_category_enum"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    source_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    source_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    rule_version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    settled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reversed_record_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("contribution_records.id"), nullable=True
    )
    adjustment_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    distributor: Mapped["Distributor"] = relationship("Distributor", back_populates="contribution_records")


class SettlementLog(Base):
    __tablename__ = "settlement_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    period: Mapped[str] = mapped_column(String(7), nullable=False, index=True)
    status: Mapped[SettlementStatus] = mapped_column(
        SAEnum(SettlementStatus, name="settlement_status_enum"),
        default=SettlementStatus.RUNNING,
    )
    total_records: Mapped[int] = mapped_column(Integer, default=0)
    settled_records: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
