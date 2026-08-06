"""Unit tests for commission_service (FR-011/FR-013)."""

from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.bill import Bill, TransactionStatus
from src.models.binding import BindingStatus, Customer
from src.models.commission_result import CommissionResult
from src.schemas.organization import OrgCreate
from src.schemas.performance_rule import PerformanceRuleUpdateRequest, Tier
from src.services import organization_service
from src.services.commission_service import compute_commission, preview_org_commission
from src.services.performance_service import save_rule
from tests.conftest import seed_user


async def _seed_org_tree(db: AsyncSession) -> tuple[int, int]:
    root = await organization_service.create_org(db, OrgCreate(name="总部", orgType="headquarters"))
    child = await organization_service.create_org(db, OrgCreate(name="华北区", orgType="region", parentId=root.id))
    return root.id, child.id


async def _seed_distributor(db: AsyncSession, org_id: int, phone: str, role: str = "member") -> int:
    user_id = await seed_user(db, openid=f"openid_{phone}", user_type="distributor", name="推广员A", phone=phone)
    from src.models.distributor import Distributor, OrgRole

    d = Distributor(user_id=user_id, org_id=org_id, org_role=OrgRole(role))
    db.add(d)
    await db.flush()
    await db.refresh(d)
    return d.id


async def _seed_customer(db: AsyncSession, distributor_id: int, id_card: str) -> int:
    c = Customer(
        distributor_id=distributor_id, name="患者", phone="13800138000",
        phone_masked="138****8000", id_card_encrypted=id_card,
        id_card_masked="110***********1234", binding_status=BindingStatus.BOUND, version=1,
    )
    db.add(c)
    await db.flush()
    await db.refresh(c)
    return c.id


async def _seed_bill(db: AsyncSession, customer_id: int, paid_cent: int, txn_id: str, status=TransactionStatus.PAID) -> None:
    db.add(Bill(
        customer_id=customer_id, transaction_id=txn_id, transaction_time=datetime(2026, 7, 15),
        paid_amount_cent=paid_cent, total_amount_cent=paid_cent, transaction_status=status,
    ))
    await db.flush()


async def _save_rule(db: AsyncSession, org_id: int, rule_type: str, ratio: float) -> None:
    await save_rule(
        db, org_id, rule_type,
        PerformanceRuleUpdateRequest(tiers=[Tier(minCent=0, maxCent=None, ratio=ratio)]),
        operator_id=1,
    )


@pytest.mark.asyncio
async def test_compute_member_and_admin(db_session: AsyncSession):
    _, child_id = await _seed_org_tree(db_session)
    member = await _seed_distributor(db_session, child_id, "13900000001")
    admin = await _seed_distributor(db_session, child_id, "13900000002", role="admin")

    cid_m = await _seed_customer(db_session, member, "110101199001011234")
    cid_a = await _seed_customer(db_session, admin, "110101199001011235")
    await _seed_bill(db_session, cid_m, 800000, "txn_m")
    await _seed_bill(db_session, cid_a, 200000, "txn_a")

    await _save_rule(db_session, child_id, "intra_org", 0.05)
    await _save_rule(db_session, child_id, "org_management", 0.08)

    await compute_commission(db_session, "2026-07")

    results = (await db_session.execute(select(CommissionResult))).scalars().all()
    # 管理员同时计组织内（自身消费）与组织管理（子树总额）两种提成
    assert len(results) == 3
    by_dist_type = {(r.distributor_id, r.rule_type.value): r for r in results}

    intra_member = by_dist_type[(member, "intra_org")]
    assert intra_member.base_cent == 800000
    assert intra_member.commission_cent == 40000  # 800000 * 0.05

    intra_admin = by_dist_type[(admin, "intra_org")]
    assert intra_admin.base_cent == 200000  # 管理员自身消费
    assert intra_admin.commission_cent == 10000  # 200000 * 0.05

    mgmt = by_dist_type[(admin, "org_management")]
    assert mgmt.base_cent == 1000000  # member(800000) + admin(200000) = subtree total
    assert mgmt.commission_cent == 80000  # 1000000 * 0.08


@pytest.mark.asyncio
async def test_compute_excludes_refunded_and_is_idempotent(db_session: AsyncSession):
    _, org_id = await _seed_org_tree(db_session)
    member = await _seed_distributor(db_session, org_id, "13900000001")
    cid = await _seed_customer(db_session, member, "110101199001011234")
    await _seed_bill(db_session, cid, 1000000, "txn_ok")
    await _seed_bill(db_session, cid, 500000, "txn_refund", status=TransactionStatus.REFUNDED)
    await _seed_bill(db_session, cid, 300000, "txn_cancel", status=TransactionStatus.CANCELLED)

    await _save_rule(db_session, org_id, "intra_org", 0.05)

    await compute_commission(db_session, "2026-07")
    await compute_commission(db_session, "2026-07")  # second run overwrites, no duplicates

    results = (await db_session.execute(select(CommissionResult))).scalars().all()
    assert len(results) == 1  # idempotent
    assert results[0].base_cent == 1000000  # refunded/cancelled excluded
    assert results[0].commission_cent == 50000


@pytest.mark.asyncio
async def test_preview_matches_compute(db_session: AsyncSession):
    _, org_id = await _seed_org_tree(db_session)
    member = await _seed_distributor(db_session, org_id, "13900000001")
    cid = await _seed_customer(db_session, member, "110101199001011234")
    await _seed_bill(db_session, cid, 400000, "txn_p")

    await _save_rule(db_session, org_id, "intra_org", 0.05)
    await _save_rule(db_session, org_id, "org_management", 0.08)

    preview = await preview_org_commission(db_session, org_id, "2026-07")
    assert preview["intraOrg"][0]["commissionCent"] == 20000  # 400000 * 0.05

    # No admin -> no orgManagement row (no persistence either)
    assert preview["orgManagement"] == []


@pytest.mark.asyncio
async def test_monthly_settlement_hook_calls_compute(db_session: AsyncSession):
    """monthly_settlement_job runs compute_commission for the previous month."""
    from unittest.mock import AsyncMock, patch

    from src.tasks import settlement_task

    with patch("src.services.commission_service.compute_commission", new=AsyncMock(return_value={"period": "2026-07", "computed": 0, "frozen": False})) as mock_compute:
        await settlement_task.monthly_settlement_job()
        mock_compute.assert_awaited_once()
