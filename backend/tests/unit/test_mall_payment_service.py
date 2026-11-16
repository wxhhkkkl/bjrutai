from dataclasses import replace
from datetime import datetime

import pytest
from sqlalchemy import func, select

from src.core.config import get_settings
from src.core.exceptions import ConflictException
from src.models.mall_catalog import MallStockMovement
from src.models.mall_consumption import MallConsumption
from src.models.mall_finance import MallPayment
from src.models.mall_operations import MallJob
from src.models.performance_evidence import PerformancePeriodVersion
from src.schemas.mall_catalog import VersionAction
from src.services.mall_order_service import create_order
from tests.unit.test_mall_order_service import intent


async def payable(db, monkeypatch, *, openid="payment-test-openid"):
    from src.services.mall_payment_service import prepare_payment

    actor, _, _, skus, _, body = await intent(db, monkeypatch)
    order = await create_order(db, actor, body, key="payable-order-intent-001")
    from src.models.user import User

    (await db.get(User, actor.actor_id)).openid = openid
    order.created_at = datetime(2026, 10, 1)
    monkeypatch.setattr(get_settings(), "wechat_app_id", "wx-test")
    monkeypatch.setattr(get_settings(), "mall_wechat_mchid", "test-merchant", raising=False)
    payment = await prepare_payment(
        db,
        actor,
        order.id,
        VersionAction(expectedVersion=order.version),
        key="payment-prepare-intent-001",
    )
    await db.commit()
    return actor, order, skus, payment


def success(payment, order, *, paid_at=None):
    from src.integrations.wechat_pay_types import PaymentFact

    return PaymentFact(
        "wx-test",
        "test-merchant",
        payment.out_trade_no,
        "SUCCESS",
        order.payable_amount_cent,
        "CNY",
        "synthetic-channel-id",
        paid_at or datetime(2026, 11, 4, 16, 30),
        order.payable_amount_cent,
        openid="payment-test-openid",
    )


@pytest.mark.asyncio
async def test_unique_payment_replay_and_new_key_reuse_existing_identity(db_session, monkeypatch):
    from src.services.mall_payment_service import prepare_payment

    actor, order, skus, payment = await payable(db_session, monkeypatch)
    repeat = await prepare_payment(
        db_session,
        actor,
        order.id,
        VersionAction(expectedVersion=1),
        key="payment-prepare-intent-001",
    )
    other_key = await prepare_payment(
        db_session,
        actor,
        order.id,
        VersionAction(expectedVersion=order.version),
        key="payment-prepare-intent-002",
    )
    assert payment.id == repeat.id == other_key.id and payment.status == "creating"
    assert (
        payment.out_trade_no and payment.active_slot == 1 and order.active_payment_id == payment.id
    )
    assert await db_session.scalar(select(func.count()).select_from(MallPayment)) == 1
    assert skus[0].available_qty == 9 and skus[0].reserved_qty == 1
    assert (
        await db_session.scalar(
            select(func.count()).select_from(MallJob).where(MallJob.kind == "mall_payment_create")
        )
        == 1
    )


@pytest.mark.asyncio
async def test_verified_success_converts_reserved_stock_and_creates_one_source(
    db_session, monkeypatch
):
    from src.services.mall_payment_service import apply_verified_payment

    actor, order, skus, payment = await payable(db_session, monkeypatch)
    fact = success(payment, order)
    for _ in range(20):
        await apply_verified_payment(db_session, payment.id, fact)
    await db_session.commit()
    assert payment.status == "succeeded" and order.status == "pending_shipment"
    assert order.paid_amount_cent == 21000 and order.business_period == "2026-11"
    assert [(sku.available_qty, sku.reserved_qty) for sku in skus] == [(9, 0), (8, 0)]
    sources = (await db_session.scalars(select(MallConsumption))).all()
    assert (
        len(sources) == 1
        and sources[0].original_goods_cent == sources[0].performance_base_cent == 20000
    )
    assert sources[0].status == "unassigned" and sources[0].customer_id is None
    period = await db_session.get(PerformancePeriodVersion, "2026-11")
    assert period.revision == 1
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(MallStockMovement)
            .where(MallStockMovement.kind == "sale")
        )
        == 2
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"appid": "alien"},
        {"mchid": "alien"},
        {"total_cent": 1},
        {"currency": "USD"},
        {"out_trade_no": "other"},
        {"payer_total_cent": 1},
        {"transaction_id": None},
        {"paid_at": None},
        {"openid": "alien-openid"},
        {"openid": None},
    ],
)
async def test_wrong_verified_facts_do_not_change_order_or_release_stock(
    db_session, monkeypatch, changes
):
    from src.services.mall_payment_service import apply_verified_payment

    _, order, skus, payment = await payable(db_session, monkeypatch)
    with pytest.raises(ConflictException):
        await apply_verified_payment(
            db_session, payment.id, replace(success(payment, order), **changes)
        )
    assert order.paid_amount_cent == 0 and skus[0].reserved_qty == 1
    assert await db_session.scalar(select(func.count()).select_from(MallConsumption)) == 0


@pytest.mark.asyncio
async def test_close_success_and_late_success_have_no_double_stock_side_effect(
    db_session, monkeypatch
):
    from src.integrations.wechat_pay_types import VerifiedClose
    from src.services.mall_payment_service import apply_verified_close, apply_verified_payment

    _, order, skus, payment = await payable(db_session, monkeypatch)
    closed = VerifiedClose(payment.out_trade_no, payment.mchid_snapshot)
    await apply_verified_close(db_session, payment.id, closed)
    await apply_verified_close(db_session, payment.id, closed)
    assert order.status == "closed" and [(s.available_qty, s.reserved_qty) for s in skus] == [
        (10, 0),
        (10, 0),
    ]
    await apply_verified_payment(db_session, payment.id, success(payment, order))
    assert order.paid_amount_cent == 21000 and order.status == "closed"
    assert (
        payment.status == "succeeded"
        and payment.last_error_code == "paid_order_requires_manual_refund"
    )
    assert [(s.available_qty, s.reserved_qty) for s in skus] == [(10, 0), (10, 0)]
    await apply_verified_close(db_session, payment.id, closed)
    assert payment.status == "succeeded"
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(MallJob)
            .where(MallJob.kind == "mall_paid_order_exception")
        )
        == 1
    )


@pytest.mark.asyncio
async def test_old_pending_cannot_overwrite_success(db_session, monkeypatch):
    from src.services.mall_payment_service import apply_verified_payment

    _, order, skus, payment = await payable(db_session, monkeypatch)
    fact = success(payment, order)
    await apply_verified_payment(db_session, payment.id, fact)
    await apply_verified_payment(
        db_session, payment.id, replace(fact, state="NOTPAY", transaction_id=None, paid_at=None)
    )
    assert payment.status == "succeeded" and skus[0].reserved_qty == 0


@pytest.mark.asyncio
async def test_unexpected_second_success_is_recorded_for_refund_without_double_source(
    db_session, monkeypatch
):
    from src.services.mall_payment_service import apply_verified_payment

    _, order, skus, payment = await payable(db_session, monkeypatch)
    await apply_verified_payment(db_session, payment.id, success(payment, order))
    other = MallPayment(
        order_id=order.id,
        out_trade_no="unexpected-second-request",
        amount_cent=order.payable_amount_cent,
        appid_snapshot="wx-test",
        mchid_snapshot="test-merchant",
        expires_at=order.expires_at,
        status="unknown",
    )
    db_session.add(other)
    await db_session.flush()
    fact = replace(success(other, order), transaction_id="unexpected-second-transaction")
    await apply_verified_payment(db_session, other.id, fact)
    assert (
        other.status == "succeeded"
        and other.last_error_code == "duplicate_payment_requires_manual_refund"
    )
    assert order.paid_amount_cent == 21000 and order.active_payment_id == payment.id
    assert [(s.available_qty, s.reserved_qty) for s in skus] == [(9, 0), (8, 0)]
    assert await db_session.scalar(select(func.count()).select_from(MallConsumption)) == 1
    assert (await db_session.get(PerformancePeriodVersion, "2026-11")).revision == 1
    job = (
        await db_session.scalars(select(MallJob).where(MallJob.kind == "mall_paid_order_exception"))
    ).one()
    assert job.status == "manual"
