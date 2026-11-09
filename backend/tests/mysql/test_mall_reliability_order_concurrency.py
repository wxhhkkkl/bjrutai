"""Real InnoDB order transactions; no channel or production database calls."""

import asyncio
from time import perf_counter
from uuid import uuid4

from sqlalchemy import func, select

from src.api.mall_deps import MallActor
from src.core.config import get_settings
from src.core.exceptions import ConflictException
from src.models.mall_catalog import MallSku, MallStockMovement
from src.models.mall_operations import MallCommand
from src.models.mall_trade import MallOrder, MallOrderItem
from src.schemas.mall_checkout import AddressWrite, OrderCreate, QuoteRequest
from src.services.mall_address_service import save_address
from src.services.mall_checkout_service import quote_order
from src.services.mall_order_service import create_order
from tests.conftest import seed_user
from tests.mall_checkout_fixtures import ADDRESS, checkout_seed


async def prepare_buyers(sessions, count, quantities, *, reverse=False):
    async with sessions() as setup:
        _, _, _, skus = await checkout_seed(setup)
        for sku in skus:
            sku.available_qty = quantities
        sku_ids = [sku.id for sku in skus]
        await setup.commit()
    requests = []
    for number in range(count):
        async with sessions() as db:
            user = await seed_user(db, user_type="personal", openid=f"order-race-{uuid4().hex}")
            actor = MallActor("user", user, frozenset())
            address = await save_address(db, actor, AddressWrite(**ADDRESS))
            chosen = sku_ids if reverse else sku_ids[:1]
            if reverse and number % 2:
                chosen = list(reversed(chosen))
            quote = await quote_order(
                db,
                actor,
                QuoteRequest(
                    addressId=str(address.id),
                    items=[{"skuId": str(identity), "quantity": 1} for identity in chosen],
                ),
            )
            requests.append(
                (
                    actor,
                    OrderCreate(
                        quoteToken=quote["quoteToken"],
                        consentVersion="mall-test-v1",
                        consentConfirmed=True,
                    ),
                )
            )
            await db.commit()
    return sku_ids, requests


async def attempt(sessions, actor, body, key):
    async with sessions() as db:
        try:
            order = await create_order(db, actor, body, key=key)
            await db.commit()
            return order.id
        except ConflictException:
            await db.rollback()
            return None


async def test_one_hundred_requests_for_last_unit_create_one_order(
    mall_mysql_sessions, monkeypatch
):
    monkeypatch.setattr(get_settings(), "mall_enabled", True)
    monkeypatch.setattr(get_settings(), "mall_purchase_enabled", True)
    ids, requests = await prepare_buyers(mall_mysql_sessions, 100, 1)
    started = perf_counter()
    results = await asyncio.wait_for(
        asyncio.gather(
            *[
                attempt(mall_mysql_sessions, actor, body, f"last-unit-order-{index:04d}")
                for index, (actor, body) in enumerate(requests)
            ]
        ),
        timeout=60,
    )
    elapsed = perf_counter() - started
    print(
        "T129 measure: last-unit race 100 concurrent requests "
        f"elapsed={elapsed:.3f}s throughput={100 / elapsed:.1f} requests/s"
    )
    assert sum(identity is not None for identity in results) == 1
    async with mall_mysql_sessions() as db:
        sku = await db.get(MallSku, ids[0])
        assert sku.available_qty == 0 and sku.reserved_qty == 1
        assert (
            await db.scalar(
                select(func.count())
                .select_from(MallOrderItem)
                .where(MallOrderItem.sku_id == ids[0])
            )
            == 1
        )
        assert (
            await db.scalar(
                select(func.count())
                .select_from(MallStockMovement)
                .where(MallStockMovement.sku_id == ids[0], MallStockMovement.kind == "reserve")
            )
            == 1
        )


async def test_twenty_retries_share_one_order_and_do_not_upgrade_shared_locks(
    mall_mysql_sessions, monkeypatch
):
    monkeypatch.setattr(get_settings(), "mall_enabled", True)
    monkeypatch.setattr(get_settings(), "mall_purchase_enabled", True)
    ids, requests = await prepare_buyers(mall_mysql_sessions, 1, 10)
    actor, body = requests[0]
    started = perf_counter()
    results = await asyncio.wait_for(
        asyncio.gather(
            *[
                attempt(mall_mysql_sessions, actor, body, "same-order-twenty-retries")
                for _ in range(20)
            ]
        ),
        timeout=20,
    )
    elapsed = perf_counter() - started
    print(f"T129 measure: 20 concurrent idempotent replays elapsed={elapsed:.3f}s")
    assert None not in results and len(set(results)) == 1
    async with mall_mysql_sessions() as db:
        sku = await db.get(MallSku, ids[0])
        assert (sku.available_qty, sku.reserved_qty) == (9, 1)
        assert (
            await db.scalar(
                select(func.count())
                .select_from(MallCommand)
                .where(
                    MallCommand.actor_id == actor.actor_id, MallCommand.action == "createMallOrder"
                )
            )
            == 1
        )


async def test_reverse_multisku_requests_have_fixed_lock_order_and_no_partial_order(
    mall_mysql_sessions, monkeypatch
):
    monkeypatch.setattr(get_settings(), "mall_enabled", True)
    monkeypatch.setattr(get_settings(), "mall_purchase_enabled", True)
    ids, requests = await prepare_buyers(mall_mysql_sessions, 2, 2, reverse=True)
    started = perf_counter()
    results = await asyncio.wait_for(
        asyncio.gather(
            *[
                attempt(mall_mysql_sessions, actor, body, f"reverse-sku-order-{index:04d}")
                for index, (actor, body) in enumerate(requests)
            ]
        ),
        timeout=20,
    )
    elapsed = perf_counter() - started
    print(f"T129 measure: reverse-order multi-SKU race (2 buyers) elapsed={elapsed:.3f}s")
    assert sum(identity is not None for identity in results) == 1  # second quote became stale
    async with mall_mysql_sessions() as db:
        rows = (await db.scalars(select(MallSku).where(MallSku.id.in_(ids)))).all()
        assert all((row.available_qty, row.reserved_qty) == (1, 1) for row in rows)


async def test_failed_commit_stage_leaves_no_command_order_item_or_stock(
    mall_mysql_sessions, monkeypatch
):
    import pytest

    from src.services import mall_order_service as orders

    monkeypatch.setattr(get_settings(), "mall_enabled", True)
    monkeypatch.setattr(get_settings(), "mall_purchase_enabled", True)
    ids, requests = await prepare_buyers(mall_mysql_sessions, 1, 10, reverse=True)
    actor, body = requests[0]

    async def broken(*args, **kwargs):
        raise RuntimeError("injected queue persistence failure")

    monkeypatch.setattr(orders, "enqueue_mall_job", broken)
    async with mall_mysql_sessions() as db:
        with pytest.raises(RuntimeError):
            await orders.create_order(db, actor, body, key="failed-transaction-mysql")
        await db.rollback()
    async with mall_mysql_sessions() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(MallOrder)
                .where(MallOrder.buyer_user_id == actor.actor_id)
            )
            == 0
        )
        assert (
            await db.scalar(
                select(func.count())
                .select_from(MallCommand)
                .where(
                    MallCommand.actor_id == actor.actor_id, MallCommand.action == "createMallOrder"
                )
            )
            == 0
        )
        assert (
            await db.scalar(
                select(func.count()).select_from(MallOrderItem).where(MallOrderItem.sku_id.in_(ids))
            )
            == 0
        )
        rows = (await db.scalars(select(MallSku).where(MallSku.id.in_(ids)))).all()
        assert all((row.available_qty, row.reserved_qty) == (10, 0) for row in rows)


async def test_aftersale_application_and_dispatch_race_allow_only_one_stale_version_winner(
    mall_mysql_sessions, monkeypatch
):
    from datetime import datetime, timedelta

    from src.integrations.wechat_pay_types import PaymentFact
    from src.models.mall_base import utc_now
    from src.models.mall_operations import MallJob
    from src.models.mall_trade import MallAftersale, MallShipment
    from src.models.user import User
    from src.schemas.mall_aftersale import AftersaleCreate
    from src.schemas.mall_catalog import VersionAction
    from src.schemas.mall_fulfillment import ShipmentCreate
    from src.services.mall_aftersale_service import apply_aftersale
    from src.services.mall_payment_service import apply_verified_payment, prepare_payment
    from src.services.mall_shipment_service import ship_order
    from tests.mysql.test_mall_reliability_payments import enable, local_order
    from tests.unit.test_mall_aftersale_service import admin_actor

    enable(monkeypatch)
    buyer, identity, version = await local_order(mall_mysql_sessions)
    async with mall_mysql_sessions() as db:
        payment = await prepare_payment(
            db,
            buyer,
            identity,
            VersionAction(expectedVersion=version),
            key="mysql-aftersale-dispatch-payment-" + uuid4().hex,
        )
        user = await db.get(User, buyer.actor_id)
        await apply_verified_payment(
            db,
            payment.id,
            PaymentFact(
                "wx-test",
                "test-merchant",
                payment.out_trade_no,
                "SUCCESS",
                payment.amount_cent,
                "CNY",
                "aftersale-dispatch-" + uuid4().hex,
                datetime(2026, 11, 6),
                payment.amount_cent,
                user.openid,
            ),
        )
        # Keep this paid fixture's create job from being claimed by later tests
        # that intentionally exercise a different fake payment channel.
        jobs = (
            await db.scalars(
                select(MallJob).where(
                    MallJob.kind == "mall_payment_create",
                    MallJob.entity_id == payment.id,
                    MallJob.entity_type == "mall_payment",
                )
            )
        ).all()
        for job in jobs:
            job.next_run_at = utc_now() + timedelta(days=1)
        await db.commit()

    async with mall_mysql_sessions() as db:
        order = await db.get(MallOrder, identity)
        item = (
            await db.scalars(select(MallOrderItem).where(MallOrderItem.order_id == identity))
        ).one()
        current_version = order.version
        application = AftersaleCreate(
            orderId=str(identity),
            expectedOrderVersion=current_version,
            method="refund_only",
            items=[{"orderItemId": str(item.id), "quantity": 1}],
            reason="并发验收场景的退款申请",
        )
        await db.commit()

    async with mall_mysql_sessions() as db:
        operator = await admin_actor(db, ["mall.shipments.write"])
    shipment = ShipmentCreate(
        expectedVersion=current_version,
        courierCode="sf",
        trackingNo="RACE" + uuid4().hex[:8].upper(),
    )

    async def apply():
        async with mall_mysql_sessions() as db:
            try:
                row = await apply_aftersale(
                    db,
                    buyer,
                    application,
                    key="mysql-aftersale-dispatch-apply-" + uuid4().hex,
                )
                await db.commit()
                return ("aftersale", row.id)
            except ConflictException:
                await db.rollback()
                return None

    async def dispatch():
        async with mall_mysql_sessions() as db:
            try:
                row = await ship_order(
                    db,
                    operator,
                    identity,
                    shipment,
                    key="mysql-aftersale-dispatch-ship-" + uuid4().hex,
                )
                await db.commit()
                return ("shipment", row.id)
            except ConflictException:
                await db.rollback()
                return None

    outcomes = await asyncio.wait_for(asyncio.gather(apply(), dispatch()), timeout=30)
    winners = [result for result in outcomes if result]
    assert len(winners) == 1
    async with mall_mysql_sessions() as db:
        order = await db.get(MallOrder, identity)
        item = (
            await db.scalars(select(MallOrderItem).where(MallOrderItem.order_id == identity))
        ).one()
        aftersale_count = await db.scalar(
            select(func.count())
            .select_from(MallAftersale)
            .where(MallAftersale.order_id == identity)
        )
        shipment_count = await db.scalar(
            select(func.count()).select_from(MallShipment).where(MallShipment.order_id == identity)
        )
        assert aftersale_count + shipment_count == 1
        if winners[0][0] == "aftersale":
            assert order.status == "pending_shipment" and order.refund_reserved_cent > 0
            assert item.aftersale_reserved_quantity == 1 and shipment_count == 0
        else:
            assert order.status == "pending_receipt" and order.refund_reserved_cent == 0
            assert item.aftersale_reserved_quantity == 0 and aftersale_count == 0
