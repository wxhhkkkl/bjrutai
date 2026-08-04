"""Performance rule models — org-level commission configuration (FR-003~FR-007).

Each org configures two commission types (intra_org / org_management) as a
tiered percentage ladder over consumption amounts (cents). Change history is
kept in performance_rule_change_logs.
"""

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class RuleType(str, enum.Enum):
    INTRA_ORG = "intra_org"
    ORG_MANAGEMENT = "org_management"


class RuleStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class ChangeOperation(str, enum.Enum):
    CREATE = "create"
    UPDATE = "update"
    APPLY = "apply"


class PerformanceRule(Base):
    __tablename__ = "performance_rules"
    __table_args__ = (
        UniqueConstraint("org_id", "rule_type", name="uk_rule_org_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    rule_type: Mapped[RuleType] = mapped_column(
        SAEnum(RuleType, name="rule_type_enum_pr", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    tiers: Mapped[list] = mapped_column(JSON, nullable=False)  # [{minCent, maxCent, ratio}]
    status: Mapped[RuleStatus] = mapped_column(
        SAEnum(RuleStatus, name="rule_status_enum_pr", values_callable=lambda x: [e.value for e in x]),
        default=RuleStatus.ACTIVE,
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PerformanceRuleChangeLog(Base):
    __tablename__ = "performance_rule_change_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("performance_rules.id", ondelete="CASCADE"), nullable=False, index=True
    )
    operation_type: Mapped[ChangeOperation] = mapped_column(
        SAEnum(ChangeOperation, name="change_op_enum_pr", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ChangeOperation.CREATE,
    )
    changed_by: Mapped[int] = mapped_column(Integer, nullable=False)  # 后台管理员 AdminAccount.id
    old_value: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    new_value: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
