import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
)
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class RuleType(str, enum.Enum):
    FIXED_RATIO = "fixed_ratio"
    FIXED_AMOUNT = "fixed_amount"
    TIERED = "tiered"


class RuleBase(str, enum.Enum):
    PAID_AMOUNT = "paid_amount"
    TOTAL_AMOUNT = "total_amount"


class RuleStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    EXPIRED = "expired"


# ---------------------------------------------------------------------------
# Change log for sharing rule modifications
# ---------------------------------------------------------------------------
sharing_rule_change_logs = Table(
    "sharing_rule_change_logs",
    Base.metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("rule_id", Integer, ForeignKey("sharing_rules.id"), nullable=False),
    Column("changed_by", Integer, ForeignKey("users.id"), nullable=False),
    Column("old_value", JSON, default=dict),
    Column("new_value", JSON, default=dict),
    Column("created_at", DateTime, default=datetime.utcnow),
)


class SharingRule(Base):
    __tablename__ = "sharing_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    rule_type: Mapped[RuleType] = mapped_column(
        SAEnum(RuleType, name="rule_type_enum"), nullable=False
    )
    base: Mapped[RuleBase] = mapped_column(
        SAEnum(RuleBase, name="rule_base_enum"), nullable=False
    )
    value: Mapped[str] = mapped_column(Text, nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[RuleStatus] = mapped_column(
        SAEnum(RuleStatus, name="rule_status_enum"), default=RuleStatus.ACTIVE
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------------------------------------------------------------------------
# Contribution coefficient – global setting for contribution calculation
# ---------------------------------------------------------------------------
class ContributionCoefficient(Base):
    __tablename__ = "contribution_coefficient"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    coefficient: Mapped[str] = mapped_column(String(20), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    previous_coefficient: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
