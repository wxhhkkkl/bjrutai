"""Independent InnoDB sessions exercise local payment facts, not real channels."""

import asyncio
from datetime import datetime
from uuid import uuid4

from sqlalchemy import func, select

from src.core.config import get_settings
from src.integrations.wechat_pay_types import PaymentFact
from src.models.mall_consumption import MallConsumption
from src.models.mall_finance import MallPayment
from src.models.performance_evidence import PerformancePeriodVersion
from src.schemas.mall_catalog import VersionAction
from src.schemas.mall_checkout import AddressWrite, OrderCreate, QuoteRequest
from src.services.mall_address_service import save_address
from src.services.mall_checkout_service import quote_order
from src.services.mall_order_service import create_order
from src.services.mall_payment_service import apply_verified_payment, prepare_payment
from tests.mall_checkout_fixtures import ADDRESS, checkout_seed


async def local_order(sessions):
    async with sessions() as db:
        actor, _, _, skus = await checkout_seed(db)
        address = await save_address(db, actor, AddressWrite(**ADDRESS))
        quote = await quote_order(
            db,
            actor,
            QuoteRequest(
                addressId=str(address.id),
                items=[
                    {"skuId": str(skus[0].id), "quantity": 1},
                ],
            ),
        )
        await db.commit()
        order = await create_order(
            db,
            actor,
            OrderCreate(
                quoteToken=quote["quoteToken"],
                consentVersion="mall-test-v1",
                consentConfirmed=True,
            ),
            key="mysql-payment-order-" + uuid4().hex,
        )
        order.created_at = datetime(2026, 10, 1)
        await db.commit()
        return actor, order.id, order.version


def enable(monkeypatch):
    for field in ("mall_enabled", "mall_purchase_enabled"):
        monkeypatch.setattr(get_settings(), field, True)
    monkeypatch.setattr(get_settings(), "wechat_app_id", "wx-test")
    monkeypatch.setattr(get_settings(), "mall_wechat_mchid", "test-merchant")


async def test_distinct_orders_prepare_without_empty_payment_gap_deadlock(
    mall_mysql_sessions, monkeypatch
):
    enable(monkeypatch)
    orders = [await local_order(mall_mysql_sessions) for _ in range(12)]

    async def prepare(context):
        actor, identity, version = context
        async with mall_mysql_sessions() as db:
            payment = await prepare_payment(
                db,
                actor,
                identity,
                VersionAction(expectedVersion=version),
                key="mysql-distinct-payment-" + uuid4().hex,
            )
            await db.commit()
            return payment.id

    identities = await asyncio.wait_for(
        asyncio.gather(*[prepare(context) for context in orders]), timeout=30
    )
    assert len(set(identities)) == 12


async def test_first_period_concurrent_sources_are_unique_and_revision_is_not_lost(
    mall_mysql_sessions, monkeypatch
):
    from src.models.mall_trade import MallOrder
    from src.models.user import User

    enable(monkeypatch)
    contexts = [await local_order(mall_mysql_sessions) for _ in range(4)]
    payments = []
    async with mall_mysql_sessions() as db:
        assert await db.get(PerformancePeriodVersion, "2026-09") is None
    for actor, identity, version in contexts:
        async with mall_mysql_sessions() as db:
            (await db.get(MallOrder, identity)).created_at = datetime(2026, 9, 1)
            payment = await prepare_payment(
                db,
                actor,
                identity,
                VersionAction(expectedVersion=version),
                key="mysql-period-payment-" + uuid4().hex,
            )
            openid = (await db.get(User, actor.actor_id)).openid
            fact = PaymentFact(
                "wx-test",
                "test-merchant",
                payment.out_trade_no,
                "SUCCESS",
                payment.amount_cent,
                "CNY",
                "txn-" + uuid4().hex,
                datetime(2026, 9, 15),
                payment.amount_cent,
                openid,
            )
            payments.append((payment.id, fact))
            await db.commit()

    async def settle(context):
        async with mall_mysql_sessions() as db:
            await apply_verified_payment(db, *context)
            await db.commit()

    await asyncio.wait_for(asyncio.gather(*[settle(context) for context in payments]), timeout=30)
    await asyncio.wait_for(asyncio.gather(*[settle(payments[0]) for _ in range(20)]), timeout=30)
    async with mall_mysql_sessions() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(MallConsumption)
                .where(MallConsumption.order_id.in_([context[1] for context in contexts]))
            )
            == 4
        )
        assert (await db.get(PerformancePeriodVersion, "2026-09")).revision == 4
        assert (
            await db.scalar(
                select(func.count())
                .select_from(MallPayment)
                .where(
                    MallPayment.status == "succeeded", MallPayment.id.in_([p[0] for p in payments])
                )
            )
            == 4
        )


async def test_twenty_same_payment_preparations_keep_one_stable_request(
    mall_mysql_sessions, monkeypatch
):
    enable(monkeypatch)
    actor, identity, version = await local_order(mall_mysql_sessions)

    async def prepare():
        async with mall_mysql_sessions() as db:
            payment = await prepare_payment(
                db,
                actor,
                identity,
                VersionAction(expectedVersion=version),
                key="mysql-20-identical-payment-intents",
            )
            await db.commit()
            return payment.id

    identities = await asyncio.wait_for(asyncio.gather(*[prepare() for _ in range(20)]), timeout=30)
    assert len(set(identities)) == 1
    async with mall_mysql_sessions() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(MallPayment)
                .where(MallPayment.order_id == identity)
            )
            == 1
        )


async def test_verified_close_and_success_race_keeps_money_and_one_stock_outcome(
    mall_mysql_sessions, monkeypatch
):
    from src.integrations.wechat_pay_types import VerifiedClose
    from src.models.mall_catalog import MallSku
    from src.models.mall_trade import MallOrder, MallOrderItem
    from src.models.user import User
    from src.services.mall_payment_service import apply_verified_close

    enable(monkeypatch)
    actor, identity, version = await local_order(mall_mysql_sessions)
    async with mall_mysql_sessions() as db:
        payment = await prepare_payment(
            db,
            actor,
            identity,
            VersionAction(expectedVersion=version),
            key="mysql-success-close-race",
        )
        payment_id = payment.id
        fact = PaymentFact(
            "wx-test",
            "test-merchant",
            payment.out_trade_no,
            "SUCCESS",
            payment.amount_cent,
            "CNY",
            "race-" + uuid4().hex,
            datetime(2026, 11, 4),
            payment.amount_cent,
            (await db.get(User, actor.actor_id)).openid,
        )
        close = VerifiedClose(payment.out_trade_no, payment.mchid_snapshot)
        await db.commit()

    async def apply(success):
        async with mall_mysql_sessions() as db:
            if success:
                await apply_verified_payment(db, payment_id, fact)
            else:
                await apply_verified_close(db, payment_id, close)
            await db.commit()

    await asyncio.wait_for(asyncio.gather(apply(True), apply(False)), timeout=30)
    async with mall_mysql_sessions() as db:
        order = await db.get(MallOrder, identity)
        payment = await db.get(MallPayment, payment_id)
        item = (
            await db.scalars(select(MallOrderItem).where(MallOrderItem.order_id == identity))
        ).one()
        sku = await db.get(MallSku, item.sku_id)
        assert order.paid_amount_cent == payment.amount_cent and payment.status == "succeeded"
        assert sku.reserved_qty == 0
        assert (order.status, sku.available_qty) in {("pending_shipment", 9), ("closed", 10)}
        if order.status == "closed":
            assert payment.last_error_code == "paid_order_requires_manual_refund"
        assert (
            await db.scalar(
                select(func.count())
                .select_from(MallConsumption)
                .where(MallConsumption.order_id == identity)
            )
            == 1
        )


async def test_failure_after_source_write_rolls_back_money_stock_source_and_period(
    mall_mysql_sessions, monkeypatch
):

    import pytest

    from src.models.mall_catalog import MallSku
    from src.models.mall_trade import MallOrder, MallOrderItem
    from src.models.performance_settlement import PerformanceSettlement, SettlementStatus
    from src.models.user import User
    from src.services import mall_consumption_service as sources

    enable(monkeypatch)
    actor, identity, version = await local_order(mall_mysql_sessions)
    async with mall_mysql_sessions() as db:
        db.add(PerformanceSettlement(period="2026-10", status=SettlementStatus.REVIEWED))
        payment = await prepare_payment(
            db,
            actor,
            identity,
            VersionAction(expectedVersion=version),
            key="mysql-source-write-failure",
        )
        payment_id = payment.id
        fact = PaymentFact(
            "wx-test",
            "test-merchant",
            payment.out_trade_no,
            "SUCCESS",
            payment.amount_cent,
            "CNY",
            "failure-" + uuid4().hex,
            datetime(2026, 10, 31, 12),
            payment.amount_cent,
            (await db.get(User, actor.actor_id)).openid,
        )
        await db.commit()

    async def fail(*args, **kwargs):
        raise RuntimeError("injected source follow-up persistence failure")

    monkeypatch.setattr(sources, "enqueue_mall_job", fail)
    async with mall_mysql_sessions() as db:
        with pytest.raises(RuntimeError):
            await apply_verified_payment(db, payment_id, fact)
        await db.rollback()
    async with mall_mysql_sessions() as db:
        order = await db.get(MallOrder, identity)
        item = (
            await db.scalars(select(MallOrderItem).where(MallOrderItem.order_id == identity))
        ).one()
        sku = await db.get(MallSku, item.sku_id)
        assert (
            order.paid_amount_cent == 0
            and (await db.get(MallPayment, payment_id)).status == "creating"
        )
        assert (sku.available_qty, sku.reserved_qty) == (9, 1)
        assert (
            await db.scalar(
                select(func.count())
                .select_from(MallConsumption)
                .where(MallConsumption.order_id == identity)
            )
            == 0
        )
        assert await db.get(PerformancePeriodVersion, "2026-10") is None
