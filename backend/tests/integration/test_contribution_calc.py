"""Integration tests for 消费金额（业绩贡献=消费金额，账单口径）.

消费金额由 PAID 账单直接汇总：PAID 计入、REFUNDED/CANCELLED 排除、按周期过滤。
"""

from datetime import datetime, timezone

import pytest

from src.models.bill import Bill, TransactionStatus
from src.models.binding import BindingStatus, Customer
from src.schemas.organization import OrgCreate
from src.services import organization_service
from src.services.consumption_service import consumption_by_distributor
from tests.conftest import seed_user


async def _seed_distributor(db, org_id):
    user_id = await seed_user(db, openid="openid_calc", user_type="distributor", name="推广员A")
    from src.models.distributor import Distributor, OrgRole

    d = Distributor(user_id=user_id, org_id=org_id, org_role=OrgRole.MEMBER)
    db.add(d)
    await db.flush()
    await db.refresh(d)
    return d.id


async def _seed_customer(db, distributor_id):
    c = Customer(
        distributor_id=distributor_id, name="患者", phone="13800138000", phone_masked="138****8000",
        id_card_encrypted="x", id_card_masked="y", binding_status=BindingStatus.BOUND, version=1,
    )
    db.add(c)
    await db.flush()
    await db.refresh(c)
    return c.id


async def _seed_bill(db, customer_id, paid_cent, txn_id, when, status=TransactionStatus.PAID):
    db.add(Bill(
        customer_id=customer_id, transaction_id=txn_id, transaction_time=when,
        paid_amount_cent=paid_cent, total_amount_cent=paid_cent, transaction_status=status,
    ))
    await db.flush()


@pytest.mark.asyncio
async def test_paid_bill_counts_toward_consumption(db_session):
    org_id = (await organization_service.create_org(db_session, OrgCreate(name="总部", orgType="headquarters"))).id
    dist = await _seed_distributor(db_session, org_id)
    cid = await _seed_customer(db_session, dist)
    await _seed_bill(db_session, cid, 50000, "txn_calc_1", datetime(2026, 7, 15, tzinfo=timezone.utc))

    assert await consumption_by_distributor(db_session, [dist], "2026-07") == {dist: 50000}


@pytest.mark.asyncio
async def test_refunded_and_cancelled_excluded(db_session):
    org_id = (await organization_service.create_org(db_session, OrgCreate(name="总部", orgType="headquarters"))).id
    dist = await _seed_distributor(db_session, org_id)
    cid = await _seed_customer(db_session, dist)
    await _seed_bill(db_session, cid, 100000, "txn_ok", datetime(2026, 7, 1, tzinfo=timezone.utc))
    await _seed_bill(db_session, cid, 80000, "txn_refund", datetime(2026, 7, 2, tzinfo=timezone.utc), TransactionStatus.REFUNDED)
    await _seed_bill(db_session, cid, 30000, "txn_cancel", datetime(2026, 7, 3, tzinfo=timezone.utc), TransactionStatus.CANCELLED)

    assert await consumption_by_distributor(db_session, [dist], "2026-07") == {dist: 100000}


@pytest.mark.asyncio
async def test_period_filtering(db_session):
    org_id = (await organization_service.create_org(db_session, OrgCreate(name="总部", orgType="headquarters"))).id
    dist = await _seed_distributor(db_session, org_id)
    cid = await _seed_customer(db_session, dist)
    await _seed_bill(db_session, cid, 100000, "txn_july", datetime(2026, 7, 10, tzinfo=timezone.utc))
    await _seed_bill(db_session, cid, 50000, "txn_june", datetime(2026, 6, 10, tzinfo=timezone.utc))

    assert await consumption_by_distributor(db_session, [dist], "2026-07") == {dist: 100000}
    assert await consumption_by_distributor(db_session, [dist], None) == {dist: 150000}
