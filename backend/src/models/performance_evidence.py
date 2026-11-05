"""Period coordination and immutable original calculation evidence."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base
from .mall_base import MALL_ID, UTC_TIME, MallRecord, utc_now


class PerformancePeriodVersion(Base):
    __tablename__ = "performance_period_versions"
    __table_args__ = (CheckConstraint("revision >= 0", name="ck_performance_period_revision"),)
    period: Mapped[str] = mapped_column(String(7), primary_key=True)
    revision: Mapped[int] = mapped_column(BigInteger, default=0)
    recomputed_revision: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16), default="open")
    freeze_fingerprint: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTC_TIME, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTC_TIME, default=utc_now, onupdate=utc_now)


class PerformanceEvidence(MallRecord, Base):
    __tablename__ = "performance_evidence"
    __table_args__ = (
        UniqueConstraint("evidence_key", name="uq_performance_evidence_key"),
        UniqueConstraint(
            "settlement_id",
            "distributor_id",
            "rule_type",
            name="uq_performance_evidence_calculation",
        ),
        CheckConstraint(
            "original_commission_cent >= 0 AND original_base_cent >= 0 "
            "AND legacy_base_cent >= 0 AND mall_base_cent >= 0",
            name="ck_performance_evidence_amount",
        ),
        CheckConstraint(
            "result_presence IN ('present','not_generated')",
            name="ck_performance_evidence_presence",
        ),
    )
    settlement_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("performance_settlements.id", ondelete="RESTRICT")
    )
    evidence_key: Mapped[str] = mapped_column(String(64))
    result_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("commission_results.id", ondelete="RESTRICT"), unique=True
    )
    period: Mapped[str] = mapped_column(String(7), index=True)
    distributor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("distributors.id", ondelete="RESTRICT")
    )
    rule_type: Mapped[str] = mapped_column(String(32))
    org_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    frozen_members: Mapped[list] = mapped_column(JSON, default=list)
    organization_path_snapshot: Mapped[list] = mapped_column(JSON, default=list)
    rule_source: Mapped[str] = mapped_column(String(32))
    rule_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    algorithm_version: Mapped[str] = mapped_column(String(32))
    legacy_base_cent: Mapped[int] = mapped_column(BigInteger, default=0)
    mall_base_cent: Mapped[int] = mapped_column(BigInteger, default=0)
    original_base_cent: Mapped[int] = mapped_column(BigInteger, default=0)
    original_commission_cent: Mapped[int] = mapped_column(BigInteger, default=0)
    result_presence: Mapped[str] = mapped_column(String(16))
    result_absence_reason: Mapped[str | None] = mapped_column(String(64))
    input_digest: Mapped[str] = mapped_column(String(64))
    frozen_at: Mapped[datetime | None] = mapped_column(UTC_TIME)
    evidence_status: Mapped[str] = mapped_column(String(24), default="manual_required")


class PerformanceEvidenceSource(MallRecord, Base):
    __tablename__ = "performance_evidence_sources"
    __table_args__ = (
        UniqueConstraint(
            "evidence_id", "source_type", "source_id", name="uq_performance_evidence_source"
        ),
        Index("ix_performance_evidence_source_lookup", "source_type", "source_id", "evidence_id"),
        CheckConstraint(
            "source_type IN ('bill','mall') AND base_cent >= 0",
            name="ck_performance_evidence_source",
        ),
    )
    evidence_id: Mapped[int] = mapped_column(
        MALL_ID, ForeignKey("performance_evidence.id", ondelete="RESTRICT")
    )
    source_type: Mapped[str] = mapped_column(String(8))
    source_id: Mapped[int] = mapped_column(BigInteger)
    source_version: Mapped[int] = mapped_column(BigInteger)
    attributed_distributor_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("distributors.id", ondelete="RESTRICT")
    )
    calculation_org_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    occurred_at: Mapped[datetime] = mapped_column(UTC_TIME)
    business_period: Mapped[str] = mapped_column(String(7))
    base_cent: Mapped[int] = mapped_column(BigInteger)
    source_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
