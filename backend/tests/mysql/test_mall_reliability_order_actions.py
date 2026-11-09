"""Order mutation races in independent InnoDB sessions, without real channel calls."""

import asyncio
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select, text

from src.core.exceptions import ConflictException
from src.models.consent import ConsentRecord
from src.models.mall_base import utc_now
from src.models.mall_catalog import MallSku, MallStockMovement
from src.models.mall_finance import MallPayment
from src.models.mall_operations import MallJob
from src.models.mall_trade import MallOrder, MallOrderItem
from src.schemas.mall_catalog import VersionAction
from src.schemas.mall_checkout import AddressWrite, OrderAddressChange, OrderCancel
from src.services.mall_address_service import save_address
from src.services.mall_order_action_service import cancel_order, change_order_address
from src.services.mall_order_expiry_service import order_handlers
from src.services.mall_payment_service import prepare_payment
from src.tasks.mall_tasks import run_mall_worker_once
from tests.mall_checkout_fixtures import ADDRESS
from tests.mysql.test_mall_reliability_payments import enable, local_order


async def stock(db, identity):
    item = await db.scalar(select(MallOrderItem).where(MallOrderItem.order_id == identity))
    return await db.get(MallSku, item.sku_id)


async def defer_this_cases_payment_double(db, identity):
    # These tests do not own a payment channel double. Leave their jobs intact,
    # but outside the due window so later tests' per-payment doubles cannot claim them.
    jobs = (
        await db.scalars(
            select(MallJob).where(
                MallJob.kind == "mall_payment_create",
                MallJob.entity_id.in_(
                    select(MallPayment.id).where(MallPayment.order_id == identity)
                ),
            )
        )
    ).all()
    for job in jobs:
        job.next_run_at = utc_now() + timedelta(days=1)
    await db.commit()


async def test_cancel_and_payment_preparation_cannot_release_a_live_request(
    mall_mysql_sessions, monkeypatch
):
    enable(monkeypatch)
    actor, identity, version = await local_order(mall_mysql_sessions)

    async def race(cancel):
        async with mall_mysql_sessions() as db:
            try:
                if cancel:
                    await cancel_order(
                        db,
                        actor,
                        identity,
                        OrderCancel(expectedVersion=version, reason="取消"),
                        key="mysql-order-action-cancel-001",
                    )
                else:
                    await prepare_payment(
                        db,
                        actor,
                        identity,
                        VersionAction(expectedVersion=version),
                        key="mysql-order-action-payment-001",
                    )
                await db.commit()
                return True
            except ConflictException:
                await db.rollback()
                return False

    outcomes = await asyncio.wait_for(asyncio.gather(race(True), race(False)), timeout=20)
    assert outcomes.count(True) == 1
    async with mall_mysql_sessions() as db:
        order = await db.get(MallOrder, identity)
        if not order.close_requested_at:
            await cancel_order(
                db,
                actor,
                identity,
                OrderCancel(expectedVersion=order.version, reason="取消"),
                key="mysql-order-action-cancel-002",
            )
            await db.commit()
        payments = (
            await db.scalars(select(MallPayment).where(MallPayment.order_id == identity))
        ).all()
        sku = await stock(db, identity)
        assert order.close_requested_at
        if payments:
            assert (
                len(payments) == 1 and order.status == "pending_payment" and sku.reserved_qty == 1
            )
        else:
            assert order.status == "closed" and sku.reserved_qty == 0 and sku.available_qty == 10
        await defer_this_cases_payment_double(db, identity)


async def test_expiry_and_cancel_release_one_reservation_once(mall_mysql_sessions, monkeypatch):
    enable(monkeypatch)
    actor, identity, version = await local_order(mall_mysql_sessions)
    async with mall_mysql_sessions() as db:
        order = await db.get(MallOrder, identity)
        job = await db.scalar(
            select(MallJob).where(
                MallJob.kind == "mall_order_expire", MallJob.entity_id == identity
            )
        )
        order.expires_at = job.next_run_at = utc_now() - timedelta(seconds=1)
        await db.commit()

    async def cancel():
        async with mall_mysql_sessions() as db:
            try:
                await cancel_order(
                    db,
                    actor,
                    identity,
                    OrderCancel(expectedVersion=version, reason="取消"),
                    key="mysql-expiry-cancel-001",
                )
                await db.commit()
            except ConflictException:
                await db.rollback()

    await asyncio.wait_for(
        asyncio.gather(
            cancel(),
            *[
                run_mall_worker_once(
                    mall_mysql_sessions, handlers=order_handlers(mall_mysql_sessions), enabled=True
                )
                for _ in range(12)
            ],
        ),
        timeout=30,
    )
    async with mall_mysql_sessions() as db:
        assert (await db.get(MallOrder, identity)).status == "closed"
        sku = await stock(db, identity)
        assert sku.available_qty == 10 and sku.reserved_qty == 0
        assert (
            await db.scalar(
                select(func.count())
                .select_from(MallStockMovement)
                .where(
                    MallStockMovement.order_item_id.in_(
                        select(MallOrderItem.id).where(MallOrderItem.order_id == identity)
                    ),
                    MallStockMovement.kind == "release",
                )
            )
            == 1
        )


async def test_address_change_and_dispatch_share_parent_version_and_preserve_paid_amount(
    mall_mysql_sessions, monkeypatch
):
    from src.integrations.wechat_pay_types import PaymentFact
    from src.models.user import User
    from src.services.mall_payment_service import apply_verified_payment

    enable(monkeypatch)
    actor, identity, version = await local_order(mall_mysql_sessions)
    async with mall_mysql_sessions() as db:
        payment = await prepare_payment(
            db,
            actor,
            identity,
            VersionAction(expectedVersion=version),
            key="mysql-address-paid-" + uuid4().hex,
        )
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
                "address-paid-" + uuid4().hex,
                datetime(2026, 11, 4),
                payment.amount_cent,
                (await db.get(User, actor.actor_id)).openid,
            ),
        )
        order = await db.get(MallOrder, identity)
        paid, version = order.paid_amount_cent, order.version
        address = await save_address(
            db, actor, AddressWrite(**{**ADDRESS, "addressLine": "新的虚构地址"})
        )
        address_id = address.id
        await db.commit()

    async def change():
        async with mall_mysql_sessions() as db:
            try:
                await change_order_address(
                    db,
                    actor,
                    identity,
                    OrderAddressChange(
                        expectedVersion=version, addressId=str(address_id), reason="修改"
                    ),
                    key="mysql-address-change-race-001",
                )
                await db.commit()
                return True
            except ConflictException:
                await db.rollback()
                return False

    async def dispatch_lock_boundary():
        # Fulfillment is a later story. This double exercises its required order lock/version,
        # without pretending to create a real shipment or call WeChat shipping.
        async with mall_mysql_sessions() as db:
            order = await db.scalar(
                select(MallOrder)
                .where(MallOrder.id == identity)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if order.version != version:
                return False
            order.shipped_at, order.status, order.version = (
                utc_now(),
                "pending_receipt",
                order.version + 1,
            )
            await db.commit()
            return True

    results = await asyncio.wait_for(asyncio.gather(change(), dispatch_lock_boundary()), timeout=20)
    assert results.count(True) == 1
    async with mall_mysql_sessions() as db:
        order = await db.get(MallOrder, identity)
        assert order.paid_amount_cent == paid and order.payable_amount_cent == paid
        assert order.version == version + 1
        sku = await stock(db, identity)
        assert sku.available_qty == 9 and sku.reserved_qty == 0
        await defer_this_cases_payment_double(db, identity)


async def test_old_read_snapshot_cannot_accept_revoked_address_consent(
    mall_mysql_sessions, monkeypatch
):
    enable(monkeypatch)
    actor, identity, version = await local_order(mall_mysql_sessions)
    async with mall_mysql_sessions() as db:
        address = await save_address(db, actor, AddressWrite(**ADDRESS))
        address_id, consent_id = address.id, address.consent_record_id
        await db.commit()
    async with mall_mysql_sessions() as stale:
        await stale.scalar(text("SELECT COUNT(*) FROM consent_records"))
        async with mall_mysql_sessions() as writer:
            (await writer.get(ConsentRecord, consent_id)).status = "revoked"
            await writer.commit()
        import pytest

        with pytest.raises(ConflictException, match="告知"):
            await change_order_address(
                stale,
                actor,
                identity,
                OrderAddressChange(
                    expectedVersion=version, addressId=str(address_id), reason="修改"
                ),
                key="mysql-stale-address-consent-001",
            )
        await stale.rollback()
