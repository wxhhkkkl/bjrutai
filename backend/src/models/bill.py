import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base


class TransactionStatus(str, enum.Enum):
    PAID = "paid"
    PARTIALLY_REFUNDED = "partially_refunded"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class Bill(Base):
    __tablename__ = "bills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    rutai_user_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    transaction_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    transaction_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    consultation_fee_cent: Mapped[int] = mapped_column(Integer, default=0)
    medicine_fee_cent: Mapped[int] = mapped_column(Integer, default=0)
    total_amount_cent: Mapped[int] = mapped_column(Integer, default=0)
    discount_amount_cent: Mapped[int] = mapped_column(Integer, default=0)
    paid_amount_cent: Mapped[int] = mapped_column(Integer, default=0)
    refund_amount_cent: Mapped[int] = mapped_column(Integer, default=0)
    transaction_status: Mapped[TransactionStatus] = mapped_column(
        SAEnum(TransactionStatus, name="transaction_status_enum"),
        default=TransactionStatus.PAID,
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    customer: Mapped["Customer"] = relationship("Customer", back_populates="bills")
