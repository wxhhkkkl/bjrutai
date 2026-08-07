"""Unit tests for ReportService settlement-report support (010, FR-005/FR-006).

Covers ensure_settlement_report idempotent upsert (source='performance_settlement'
+ period), sections built from commission_results, and status sync.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.commission_result import CommissionResult
from src.models.performance_rule import RuleType
from src.models.report import Report
from src.services.report_service import ReportService


async def _seed_commission_result(
    db: AsyncSession,
    period: str,
    distributor_id: int = 101,
    org_id: int = 1,
    name: str = "张三",
    base_cent: int = 800000,
    ratio: float = 0.05,
    commission_cent: int = 40000,
) -> int:
    """Insert a commission result row (with minimal supporting distributor/org)."""
    from src.models.distributor import Distributor, OrgRole
    from src.models.organization import Organization

    org = Organization(name=f"组织{org_id}", org_type="branch", level=1, sort_order=0)
    db.add(org)
    await db.flush()
    await db.refresh(org)

    dist = Distributor(user_id=distributor_id, org_id=org.id, org_role=OrgRole.MEMBER)
    db.add(dist)
    await db.flush()
    await db.refresh(dist)

    result = CommissionResult(
        period=period,
        distributor_id=dist.id,
        org_id=org.id,
        rule_type=RuleType.INTRA_ORG,
        base_cent=base_cent,
        ratio=f"{ratio:.6f}",
        commission_cent=commission_cent,
        rule_snapshot={"ruleType": "intra_org", "tiers": [], "version": 1},
        computed_at=datetime.now(timezone.utc),
    )
    db.add(result)
    await db.flush()
    await db.refresh(result)
    return result.id


@pytest.mark.asyncio
async def test_ensure_settlement_report_creates_record(db_session: AsyncSession):
    """ensure_settlement_report creates a performance_settlement report row."""
    await _seed_commission_result(db_session, "2026-07")

    await ReportService.ensure_settlement_report(db_session, "2026-07", "pending")

    rows = (await db_session.execute(select(Report))).scalars().all()
    assert len(rows) == 1
    report = rows[0]
    assert report.source == "performance_settlement"
    assert report.period == "2026-07"
    assert report.status == "pending"
    assert report.dimensions == ["performance"]
    assert report.start_date == "2026-07-01"
    assert report.end_date == "2026-07-31"
    # Sections carry summary + details (FR-006)
    perf = report.sections.get("performance", {})
    assert perf["title"] == "绩效核算"
    assert "核算人数" in perf["summary"]
    assert perf["summary"]["核算人数"] == 1
    assert len(perf["details"]) == 1


@pytest.mark.asyncio
async def test_ensure_settlement_report_idempotent(db_session: AsyncSession):
    """ensure_settlement_report upserts: same period does not duplicate rows."""
    await _seed_commission_result(db_session, "2026-07")

    await ReportService.ensure_settlement_report(db_session, "2026-07", "pending")
    await ReportService.ensure_settlement_report(db_session, "2026-07", "reviewed")

    rows = (await db_session.execute(select(Report))).scalars().all()
    assert len(rows) == 1
    assert rows[0].status == "reviewed"


@pytest.mark.asyncio
async def test_ensure_settlement_report_updates_status_on_review(db_session: AsyncSession):
    """ensure_settlement_report reflects settlement status changes (FR-005)."""
    await _seed_commission_result(db_session, "2026-06")

    await ReportService.ensure_settlement_report(db_session, "2026-06", "pending")
    await ReportService.ensure_settlement_report(db_session, "2026-06", "reviewed")

    row = (await db_session.execute(select(Report))).scalars().first()
    assert row.status == "reviewed"


@pytest.mark.asyncio
async def test_ensure_settlement_report_generated_by(db_session: AsyncSession):
    """ensure_settlement_report records the operator as generated_by (FR-010)."""
    await _seed_commission_result(db_session, "2026-05")

    await ReportService.ensure_settlement_report(db_session, "2026-05", "pending", generated_by="User 7")

    row = (await db_session.execute(select(Report))).scalars().first()
    assert row.generated_by == "User 7"
