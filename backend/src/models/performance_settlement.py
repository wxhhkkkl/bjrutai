"""Monthly performance settlement batch — audit/freeze state machine (008).

One row per period (``YYYY-MM``). ``reviewed`` freezes the period: the
commission engine must skip recomputing it. ``rejected`` records the reject
reason and returns to ``pending`` after a manual recompute.
"""

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum as SAEnum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class SettlementStatus(str, enum.Enum):
    PENDING = "pending"
    REVIEWED = "reviewed"
    REJECTED = "rejected"


class PerformanceSettlement(Base):
    __tablename__ = "performance_settlements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    period: Mapped[str] = mapped_column(String(7), nullable=False, unique=True, index=True)  # 'YYYY-MM'
    status: Mapped[SettlementStatus] = mapped_column(
        SAEnum(
            SettlementStatus,
            name="settlement_status_enum",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=SettlementStatus.PENDING,
    )
    reviewed_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # AdminAccount.id
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reject_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
