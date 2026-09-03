"""Unit tests for consumption_service (业绩贡献 = 消费金额，账单口径)."""

from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.bill import Bill, TransactionStatus
from src.models.binding import BindingStatus, Customer
from src.models.distributor import Distributor, OrgRole
from src.schemas.organization import OrgCreate
from src.services import organization_service
from src.services.consumption_service import (
    consumption_by_customer,
    consumption_by_distributor,
)
from tests.conftest import seed_user


async def _seed_org(db: AsyncSession) -> int:
    return (await organization_service.create_org(db, OrgCreate(name="总部", orgType="headquarters"))).id


async def _seed_distributor(db: AsyncSession, org_id: int) -> int:
    user_id = await seed_user(db, openid="openid_c", user_type="distributor", name="推广员A")
    d = Distributor(user_id=user_id, org_id=org_id, org_role=OrgRole.MEMBER)
    db.add(d)
    await db.flush()
    await db.refresh(d)
    return d.id


async def _seed_customer(db: AsyncSession, distributor_id: int) -> int:
    c = Customer(
        distributor_id=distributor_id, name="患者", phone="13800138000", phone_masked="138****8000",
        id_card_encrypted="x", id_card_masked="y", binding_status=BindingStatus.BOUND, version=1,
    )
    db.add(c)
    await db.flush()
    await db.refresh(c)
    return c.id


async def _seed_bill(db: AsyncSession, customer_id: int, paid_cent: int, txn_id: str,
                    when: datetime | None = None, status: TransactionStatus = TransactionStatus.PAID) -> None:
    b = Bill(
        customer_id=customer_id, transaction_id=txn_id,
        transaction_time=when or datetime(2026, 7, 15),
        paid_amount_cent=paid_cent, total_amount_cent=paid_cent,
        transaction_status=status,
    )
    db.add(b)
    await db.flush()


@pytest.mark.asyncio
async def test_consumption_sums_cents(db_session: AsyncSession):
    org_id = await _seed_org(db_session)
    dist = await _seed_distributor(db_session, org_id)
    cid = await _seed_customer(db_session, dist)
    await _seed_bill(db_session, cid, 800000, "txn_1")
    await _seed_bill(db_session, cid, 200000, "txn_2")

    assert await consumption_by_distributor(db_session, [dist], "2026-07") == {dist: 1000000}
    assert await consumption_by_distributor(db_session, [dist], None) == {dist: 1000000}


@pytest.mark.asyncio
async def test_consumption_excludes_refunded_cancelled(db_session: AsyncSession):
    org_id = await _seed_org(db_session)
    dist = await _seed_distributor(db_session, org_id)
    cid = await _seed_customer(db_session, dist)
    await _seed_bill(db_session, cid, 1000000, "txn_ok")
    await _seed_bill(db_session, cid, 500000, "txn_refund", status=TransactionStatus.REFUNDED)
    await _seed_bill(db_session, cid, 300000, "txn_cancel", status=TransactionStatus.CANCELLED)

    assert await consumption_by_distributor(db_session, [dist], "2026-07") == {dist: 1000000}


@pytest.mark.asyncio
async def test_consumption_honors_period(db_session: AsyncSession):
    org_id = await _seed_org(db_session)
    dist = await _seed_distributor(db_session, org_id)
    cid = await _seed_customer(db_session, dist)
    await _seed_bill(db_session, cid, 1000000, "txn_july", when=datetime(2026, 7, 10))
    await _seed_bill(db_session, cid, 500000, "txn_june", when=datetime(2026, 6, 10))

    assert await consumption_by_distributor(db_session, [dist], "2026-07") == {dist: 1000000}


@pytest.mark.asyncio
async def test_consumption_empty_input(db_session: AsyncSession):
    assert await consumption_by_distributor(db_session, [], "2026-07") == {}


@pytest.mark.asyncio
async def test_consumption_by_customer_groups(db_session: AsyncSession):
    org_id = await _seed_org(db_session)
    dist = await _seed_distributor(db_session, org_id)
    c1 = await _seed_customer(db_session, dist)
    c2 = await _seed_customer(db_session, dist)
    await _seed_bill(db_session, c1, 300000, "txn_c1")
    await _seed_bill(db_session, c2, 700000, "txn_c2")

    result = await consumption_by_customer(db_session, [c1, c2])
    assert result == {c1: 300000, c2: 700000}


@pytest.mark.asyncio
async def test_manual_bill_keeps_snapshot_while_synced_bill_uses_current_owner(db_session: AsyncSession):
    org_id = await _seed_org(db_session)
    original_dist = await _seed_distributor(db_session, org_id)
    current_user_id = await seed_user(
        db_session,
        openid="openid_current_owner",
        user_type="distributor",
        name="推广员B",
    )
    current_dist = Distributor(user_id=current_user_id, org_id=org_id, org_role=OrgRole.MEMBER)
    db_session.add(current_dist)
    await db_session.flush()

    customer_id = await _seed_customer(db_session, original_dist)
    db_session.add(Bill(
        customer_id=customer_id,
        transaction_id="manual_snapshot",
        transaction_time=datetime(2026, 7, 10),
        paid_amount_cent=50000,
        total_amount_cent=50000,
        transaction_status=TransactionStatus.PAID,
        source="manual",
        attributed_distributor_id=original_dist,
        attributed_person_name="推广员A",
        attributed_org_id=org_id,
        attributed_org_name="总部",
    ))
    await _seed_bill(db_session, customer_id, 70000, "rutai_current_owner")

    customer = await db_session.get(Customer, customer_id)
    customer.distributor_id = current_dist.id
    await db_session.flush()

    result = await consumption_by_distributor(
        db_session, [original_dist, current_dist.id], "2026-07"
    )
    assert result == {original_dist: 50000, current_dist.id: 70000}
