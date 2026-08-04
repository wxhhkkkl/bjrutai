"""Commission result — monthly commission computed from performance rules (FR-011/FR-013)."""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base
from .performance_rule import RuleType


class CommissionResult(Base):
    __tablename__ = "commission_results"
    __table_args__ = (
        UniqueConstraint("period", "distributor_id", "rule_type", name="uk_comm_period_dist_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    period: Mapped[str] = mapped_column(String(7), nullable=False, index=True)  # 'YYYY-MM'
    distributor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("distributors.id", ondelete="CASCADE"), nullable=False
    )
    org_id: Mapped[int] = mapped_column(Integer, nullable=False)
    rule_type: Mapped[RuleType] = mapped_column(
        SAEnum(RuleType, name="rule_type_enum_pr", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    base_cent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ratio: Mapped[str] = mapped_column(String(20), nullable=False)  # decimal as string (precision)
    commission_cent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
