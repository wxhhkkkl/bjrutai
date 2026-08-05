"""Unit tests for settlement state machine (008, FR-003/FR-012/FR-013)."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import BadRequestException, NotFoundException
from src.models.performance_settlement import PerformanceSettlement, SettlementStatus
from src.services import settlement_service


async def _seed(db: AsyncSession, period: str, status: SettlementStatus = SettlementStatus.PENDING) -> int:
    s = PerformanceSettlement(period=period, status=status)
    db.add(s)
    await db.flush()
    await db.refresh(s)
    return s.id


@pytest.mark.asyncio
async def test_review_pending_marks_reviewed(db_session: AsyncSession):
    await _seed(db_session, "2026-07")
    data = await settlement_service.review_settlement(db_session, "2026-07", operator_id=1)
    assert data["status"] == "reviewed"
    assert data["reviewedBy"] == 1
    assert data["reviewedAt"] is not None

    s = (await db_session.execute(select(PerformanceSettlement))).scalars().first()
    assert s.status == SettlementStatus.REVIEWED
    assert s.reviewed_by == 1


@pytest.mark.asyncio
async def test_review_reviewed_raises(db_session: AsyncSession):
    await _seed(db_session, "2026-07", SettlementStatus.REVIEWED)
    with pytest.raises(BadRequestException):
        await settlement_service.review_settlement(db_session, "2026-07", operator_id=1)


@pytest.mark.asyncio
async def test_review_missing_settlement_raises(db_session: AsyncSession):
    with pytest.raises(NotFoundException):
        await settlement_service.review_settlement(db_session, "2026-07", operator_id=1)


@pytest.mark.asyncio
async def test_reject_pending_records_reason(db_session: AsyncSession):
    await _seed(db_session, "2026-07")
    data = await settlement_service.reject_settlement(db_session, "2026-07", operator_id=1, reason="核对有误")
    assert data["status"] == "rejected"
    assert data["rejectReason"] == "核对有误"

    s = (await db_session.execute(select(PerformanceSettlement))).scalars().first()
    assert s.status == SettlementStatus.REJECTED
    assert s.reject_reason == "核对有误"


@pytest.mark.asyncio
async def test_reject_requires_reason(db_session: AsyncSession):
    await _seed(db_session, "2026-07")
    with pytest.raises(BadRequestException):
        await settlement_service.reject_settlement(db_session, "2026-07", operator_id=1, reason="  ")


@pytest.mark.asyncio
async def test_reject_reviewed_raises(db_session: AsyncSession):
    await _seed(db_session, "2026-07", SettlementStatus.REVIEWED)
    with pytest.raises(BadRequestException):
        await settlement_service.reject_settlement(db_session, "2026-07", operator_id=1, reason="x")


@pytest.mark.asyncio
async def test_recompute_rejected_returns_pending(db_session: AsyncSession):
    """recompute delegates to commission engine; rejected period goes back to pending."""
    await _seed(db_session, "2026-07", SettlementStatus.REJECTED)
    data = await settlement_service.recompute_settlement(db_session, "2026-07")
    assert data["status"] == "pending"

    s = (await db_session.execute(select(PerformanceSettlement))).scalars().first()
    assert s.status == SettlementStatus.PENDING
    assert s.reject_reason is None


@pytest.mark.asyncio
async def test_recompute_reviewed_raises(db_session: AsyncSession):
    await _seed(db_session, "2026-07", SettlementStatus.REVIEWED)
    with pytest.raises(BadRequestException):
        await settlement_service.recompute_settlement(db_session, "2026-07")
