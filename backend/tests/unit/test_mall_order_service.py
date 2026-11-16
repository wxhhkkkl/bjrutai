from datetime import timedelta

import pytest
from sqlalchemy import func, select, text

from src.core.config import get_settings
from src.core.exceptions import ConflictException
from src.models.mall_base import utc_now
from src.models.mall_catalog import MallSku, MallStockMovement
from src.models.mall_operations import MallCommand, MallJob
from src.models.mall_trade import MallOrder, MallOrderItem
from src.schemas.mall_checkout import AddressWrite, OrderCreate, QuoteRequest
from src.services.mall_address_service import save_address
from src.services.mall_checkout_service import quote_order
from tests.mall_checkout_fixtures import ADDRESS, checkout_seed


async def intent(db, monkeypatch):
    monkeypatch.setattr(get_settings(), "mall_enabled", True)
    monkeypatch.setattr(get_settings(), "mall_purchase_enabled", True)
    actor, settings, product, skus = await checkout_seed(db)
    address = await save_address(db, actor, AddressWrite(**ADDRESS))
    quote = await quote_order(
        db,
        actor,
        QuoteRequest(
            addressId=str(address.id),
            items=[
                {"skuId": str(skus[0].id), "quantity": 1},
                {"skuId": str(skus[1].id), "quantity": 2},
            ],
        ),
    )
    await db.commit()
    # SQLite's legacy driver does not start a physical transaction for SELECT;
    # make the test's outer transaction real before command savepoints begin.
    await db.execute(text("BEGIN"))
    return (
        actor,
        settings,
        product,
        skus,
        address,
        OrderCreate(
            quoteToken=quote["quoteToken"],
            consentVersion="mall-test-v1",
            consentConfirmed=True,
            invoiceIntent=True,
            buyerNote="周末方便收货",
        ),
    )


@pytest.mark.asyncio
async def test_order_reserves_once_snapshots_and_schedules_expiry(db_session, monkeypatch):
    from src.models.consent import ConsentRecord
    from src.services.mall_order_service import create_order

    actor, settings, product, skus, address, body = await intent(db_session, monkeypatch)
    order = await create_order(db_session, actor, body, key="order-unit-intent-001")
    await db_session.commit()
    assert order.payable_amount_cent == 21000 and order.paid_amount_cent == 0
    assert order.status == "pending_payment" and order.active_payment_id is None
    assert [(s.available_qty, s.reserved_qty) for s in skus] == [(9, 1), (8, 2)]
    items = (
        await db_session.scalars(select(MallOrderItem).where(MallOrderItem.order_id == order.id))
    ).all()
    assert [i.line_amount_cent for i in items] == [10000, 10000]
    consent = await db_session.get(ConsentRecord, order.consent_record_id)
    assert consent.scene.value == "mall_checkout" and consent.scopes == {
        "mall_payment": True,
        "mall_fulfillment": True,
        "mall_order": True,
        "order_amount": True,
        "payment_status": True,
        "channel_transaction_reference": True,
        "delivery_status": True,
        "recipient_contact": True,
        "delivery_address": True,
        "courier_tracking": True,
    }
    jobs = (
        await db_session.scalars(
            select(MallJob).where(
                MallJob.entity_id == order.id, MallJob.kind == "mall_order_expire"
            )
        )
    ).all()
    assert len(jobs) == 1 and jobs[0].next_run_at == order.expires_at
    frozen_address = dict(order.address_snapshot)
    frozen_product = dict(items[0].product_snapshot)
    product.name = "改后的名称"
    address.address_line = "改后的虚构地址"
    skus[0].sale_price_cent = 20000
    await db_session.commit()
    # A lost success response may be retried even after the old quote expires.
    from src.services import mall_checkout_service as quotes

    monkeypatch.setattr(quotes, "utc_now", lambda: utc_now() + timedelta(minutes=6))
    monkeypatch.setattr(get_settings(), "mall_purchase_enabled", False)
    replay = await create_order(db_session, actor, body, key="order-unit-intent-001")
    assert replay.id == order.id
    assert order.address_snapshot == frozen_address and items[0].product_snapshot == frozen_product
    assert [(s.available_qty, s.reserved_qty) for s in skus] == [(9, 1), (8, 2)]
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(MallStockMovement)
            .where(MallStockMovement.kind == "reserve")
        )
        == 2
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["consent", "price", "stock", "closed"])
async def test_invalid_order_intent_cannot_create_partial_order(db_session, monkeypatch, change):
    from src.core.exceptions import ForbiddenException
    from src.services.mall_order_service import create_order

    actor, _, _, skus, _, body = await intent(db_session, monkeypatch)
    if change == "consent":
        body = body.model_copy(update={"consent_version": "old-version"})
    elif change == "price":
        skus[1].sale_price_cent += 1
        skus[1].version += 1
    elif change == "stock":
        skus[1].available_qty = 0
    else:
        monkeypatch.setattr(get_settings(), "mall_purchase_enabled", False)
    await db_session.flush()
    with pytest.raises((ConflictException, ForbiddenException)):
        await create_order(db_session, actor, body, key="order-invalid-intent-001")
    await db_session.rollback()
    assert await db_session.scalar(select(func.count()).select_from(MallOrder)) == 0
    assert await db_session.scalar(select(func.count()).select_from(MallOrderItem)) == 0


@pytest.mark.asyncio
async def test_order_failure_rolls_back_all_rows_and_stock(db_session, monkeypatch):
    from src.services import mall_order_service as orders

    actor, _, _, skus, _, body = await intent(db_session, monkeypatch)
    identities = [s.id for s in skus]

    async def broken_queue(*args, **kwargs):
        raise RuntimeError("simulated persistence failure")

    monkeypatch.setattr(orders, "enqueue_mall_job", broken_queue)
    with pytest.raises(RuntimeError):
        await orders.create_order(db_session, actor, body, key="order-failure-intent-001")
    await db_session.rollback()
    assert await db_session.scalar(select(func.count()).select_from(MallOrder)) == 0
    assert await db_session.scalar(select(func.count()).select_from(MallOrderItem)) == 0
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(MallCommand)
            .where(MallCommand.action == "createMallOrder")
        )
        == 0
    )
    assert await db_session.scalar(select(func.count()).select_from(MallStockMovement)) == 0
    assert [
        (s.available_qty, s.reserved_qty)
        for s in await db_session.scalars(
            select(MallSku).where(MallSku.id.in_(identities)).order_by(MallSku.id)
        )
    ] == [(10, 0), (10, 0)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payment_status", [None, "creating", "pending", "unknown", "succeeded", "closed", "failed"]
)
async def test_never_paid_close_is_idempotent_and_refuses_any_channel_history(
    db_session, monkeypatch, payment_status
):
    from src.models.mall_finance import MallPayment
    from src.services.mall_order_service import close_never_paid_order, create_order

    actor, _, _, skus, _, body = await intent(db_session, monkeypatch)
    order = await create_order(db_session, actor, body, key="order-close-intent-001")
    if payment_status:
        payment = MallPayment(
            order_id=order.id,
            out_trade_no="test-never-paid-close",
            status=payment_status,
            amount_cent=order.payable_amount_cent,
            appid_snapshot="test",
            mchid_snapshot="test",
            expires_at=order.expires_at,
        )
        db_session.add(payment)
        await db_session.flush()
        # Even a missing active pointer must not hide payment attempt history.
        order.active_payment_id = None
        await db_session.commit()
        with pytest.raises(ConflictException, match="渠道"):
            await close_never_paid_order(
                db_session, actor, order.id, expected_version=order.version
            )
        assert skus[0].reserved_qty == 1 and order.status == "pending_payment"
    else:
        await db_session.commit()
        await close_never_paid_order(db_session, actor, order.id, expected_version=order.version)
        await db_session.commit()
        await close_never_paid_order(db_session, actor, order.id, expected_version=1)
        assert order.status == "closed" and order.closed_at
        assert [(s.available_qty, s.reserved_qty) for s in skus] == [(10, 0), (10, 0)]
        assert (
            await db_session.scalar(
                select(func.count())
                .select_from(MallStockMovement)
                .where(MallStockMovement.kind == "release")
            )
            == 2
        )
