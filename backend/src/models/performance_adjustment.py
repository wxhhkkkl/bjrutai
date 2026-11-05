"""Reviewed original-period differences and their later-period allocation."""

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base
from .mall_base import MALL_ID, UTC_TIME, MallRecord


class PerformanceAdjustment(MallRecord, Base):
    __tablename__ = "performance_adjustments"
    __table_args__ = (
        UniqueConstraint(
            "evidence_id",
            "trigger_source_type",
            "trigger_source_id",
            "trigger_version",
            name="uq_performance_adjustment_event",
        ),
        CheckConstraint(
            "status IN ('proposed','manual_required','reviewed','rejected')",
            name="ck_performance_adjustment_status",
        ),
        CheckConstraint(
            "original_commission_cent >= 0 AND replayed_commission_cent >= 0",
            name="ck_performance_adjustment_original",
        ),
    )
    adjustment_no: Mapped[str] = mapped_column(String(32), unique=True)
    origin_period: Mapped[str] = mapped_column(String(7), index=True)
    origin_result_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("commission_results.id", ondelete="RESTRICT")
    )
    evidence_id: Mapped[int] = mapped_column(
        MALL_ID, ForeignKey("performance_evidence.id", ondelete="RESTRICT")
    )
    trigger_source_type: Mapped[str] = mapped_column(String(16))
    trigger_source_id: Mapped[int] = mapped_column(BigInteger)
    trigger_version: Mapped[int] = mapped_column(BigInteger)
    beneficiary_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("distributors.id", ondelete="RESTRICT")
    )
    rule_type: Mapped[str] = mapped_column(String(32))
    original_commission_cent: Mapped[int] = mapped_column(BigInteger, default=0)
    replayed_commission_cent: Mapped[int] = mapped_column(BigInteger, default=0)
    prior_confirmed_adjustment_cent: Mapped[int] = mapped_column(BigInteger, default=0)
    delta_cent: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(24), default="proposed")
    reviewed_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("admin_accounts.id", ondelete="RESTRICT")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(UTC_TIME)
    reason: Mapped[str] = mapped_column(String(1000), default="")
    remaining_cent: Mapped[int] = mapped_column(BigInteger)


class PerformanceAdjustmentApplication(MallRecord, Base):
    __tablename__ = "performance_adjustment_applications"
    __table_args__ = (
        CheckConstraint(
            "status IN ('allocated','consumed','cancelled')",
            name="ck_performance_application_status",
        ),
        CheckConstraint(
            "abs(settled_cent) <= abs(allocated_cent) "
            "AND (settled_cent = 0 OR settled_cent * allocated_cent > 0)",
            name="ck_performance_application_amount",
        ),
    )
    adjustment_id: Mapped[int] = mapped_column(
        MALL_ID, ForeignKey("performance_adjustments.id", ondelete="RESTRICT")
    )
    target_period: Mapped[str] = mapped_column(String(7), index=True)
    target_result_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("commission_results.id", ondelete="RESTRICT")
    )
    allocated_cent: Mapped[int] = mapped_column(BigInteger)
    settled_cent: Mapped[int] = mapped_column(BigInteger, default=0)
    status: Mapped[str] = mapped_column(String(16), default="allocated")
    allocation_key: Mapped[str] = mapped_column(String(128), unique=True)
    consumed_at: Mapped[datetime | None] = mapped_column(UTC_TIME)
