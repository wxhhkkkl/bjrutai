"""Aftersale quantity, money and physical-return facts stay independent."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from src.api.mall_deps import MallActor
from src.core.exceptions import ConflictException
from src.models.mall_base import utc_now
from src.models.mall_catalog import MallStockMovement
from src.models.mall_operations import MallSettings
from src.models.mall_trade import MallAftersale, MallAftersaleItem, MallOrderItem
from src.models.role import Role
from src.models.user import admin_account_roles
from tests.conftest import seed_admin
from tests.unit.test_mall_payment_service import payable, success


async def paid_order(db, monkeypatch):
    from src.services.mall_payment_service import apply_verified_payment

    actor, order, skus, payment = await payable(db, monkeypatch)
    await apply_verified_payment(db, payment.id, success(payment, order))
    await db.commit()
    await db.refresh(order)
    items = (
        await db.scalars(
            select(MallOrderItem)
            .where(MallOrderItem.order_id == order.id)
            .order_by(MallOrderItem.id)
        )
    ).all()
    return actor, order, skus, items


async def admin_actor(db, permissions):
    admin_id = await seed_admin(db, username="aftersale-" + uuid4().hex)
    role = Role(name="aftersale-role-" + uuid4().hex, permissions={"permissions": permissions})
    db.add(role)
    await db.flush()
    await db.execute(
        admin_account_roles.insert().values(admin_account_id=admin_id, role_id=role.id)
    )
    await db.commit()
    return MallActor("admin", admin_id, frozenset(permissions))


def request(order, item, *, quantity=1, method="refund_only", scope="goods"):
    from src.schemas.mall_aftersale import AftersaleCreate

    return AftersaleCreate(
        orderId=str(order.id),
        expectedOrderVersion=order.version,
        method=method,
        scope=scope,
        items=[{"orderItemId": str(item.id), "quantity": quantity}] if scope == "goods" else [],
        reason="商品与页面描述不一致",
    )


@pytest.mark.asyncio
async def test_apply_reserves_original_line_and_money_once_and_replays(db_session, monkeypatch):
    from src.services.mall_aftersale_service import apply_aftersale

    actor, order, skus, items = await paid_order(db_session, monkeypatch)
    line = items[1]  # 2 × 5,000 cents; keep the first product fulfillable.
    data = request(order, line, quantity=1)
    first = await apply_aftersale(db_session, actor, data, key="aftersale-apply-intent-001")
    replay = await apply_aftersale(db_session, actor, data, key="aftersale-apply-intent-001")
    await db_session.commit()

    assert first.id == replay.id and first.status == "submitted"
    assert first.goods_refund_cent == first.reserved_refund_cent == 5000
    assert first.freight_refund_cent == 0
    assert order.refund_reserved_cent == 5000
    assert line.aftersale_reserved_quantity == 1 and line.refunded_quantity == 0
    assert [(sku.available_qty, sku.reserved_qty) for sku in skus] == [(9, 0), (8, 0)]
    assert await db_session.scalar(select(func.count()).select_from(MallAftersaleItem)) == 1
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(MallStockMovement)
            .where(MallStockMovement.kind == "sale")
        )
        == 2
    )


@pytest.mark.asyncio
async def test_duplicate_line_and_over_remaining_quantity_or_money_are_rejected(
    db_session, monkeypatch
):
    from src.services.mall_aftersale_service import apply_aftersale

    actor, order, _, items = await paid_order(db_session, monkeypatch)
    line = items[1]
    await apply_aftersale(
        db_session, actor, request(order, line, quantity=1), key="aftersale-first-intent-001"
    )
    await db_session.commit()

    with pytest.raises(ConflictException):
        await apply_aftersale(
            db_session,
            actor,
            request(order, line, quantity=2),
            key="aftersale-overlap-intent-001",
        )
    assert line.aftersale_reserved_quantity == 1
    assert order.refund_reserved_cent == 5000


@pytest.mark.asyncio
async def test_rejection_releases_holds_and_allows_reapplication_with_history(
    db_session, monkeypatch
):
    from src.schemas.mall_aftersale import AftersaleDecision
    from src.services.mall_aftersale_service import apply_aftersale, decide_aftersale

    buyer, order, _, items = await paid_order(db_session, monkeypatch)
    line = items[1]
    first = await apply_aftersale(
        db_session, buyer, request(order, line), key="aftersale-reject-create-001"
    )
    operator = await admin_actor(db_session, ["mall.aftersales.review"])
    rejected = await decide_aftersale(
        db_session,
        operator,
        first.id,
        AftersaleDecision(expectedVersion=first.version, decision="reject", reason="缺少必要凭证"),
        key="aftersale-reject-decision-001",
    )
    await db_session.commit()
    assert rejected.status == "rejected" and rejected.audit_reason == "缺少必要凭证"
    assert order.refund_reserved_cent == 0 and line.aftersale_reserved_quantity == 0
    assert (await db_session.scalar(select(MallAftersaleItem))).active_slot is None

    second = await apply_aftersale(
        db_session,
        buyer,
        request(order, line),
        key="aftersale-reapply-create-001",
    )
    assert second.id != first.id and second.status == "submitted"
    assert await db_session.scalar(select(func.count()).select_from(MallAftersale)) == 2


@pytest.mark.asyncio
async def test_return_acceptance_restocks_only_inspected_sellable_quantity(db_session, monkeypatch):
    from src.schemas.mall_aftersale import (
        AftersaleDecision,
        ReturnReceipt,
        ReturnShipment,
        SellableReturnLine,
    )
    from src.services.mall_aftersale_service import (
        apply_aftersale,
        decide_aftersale,
        receive_return,
        submit_return_shipment,
    )

    buyer, order, skus, items = await paid_order(db_session, monkeypatch)
    line = items[1]
    operator = await admin_actor(db_session, ["mall.aftersales.review", "mall.returns.receive"])
    aftersale = await apply_aftersale(
        db_session,
        buyer,
        request(order, line, quantity=2, method="return_refund"),
        key="aftersale-return-create-001",
    )
    settings = await db_session.get(MallSettings, 1)
    settings.return_address_snapshot = {
        "recipientName": "商城退货收件人",
        "addressLine": "北京虚构退货地址",
    }
    aftersale = await decide_aftersale(
        db_session,
        operator,
        aftersale.id,
        AftersaleDecision(expectedVersion=aftersale.version, decision="approve", reason="同意退货"),
        key="aftersale-return-approve-001",
    )
    assert aftersale.status == "awaiting_return"
    before_available = skus[1].available_qty
    aftersale = await submit_return_shipment(
        db_session,
        buyer,
        aftersale.id,
        ReturnShipment(
            expectedVersion=aftersale.version,
            courierCode="yuantong",
            trackingNo="YT202611060099",
        ),
        key="aftersale-return-waybill-001",
    )
    assert aftersale.status == "awaiting_receipt"
    aftersale_item = await db_session.scalar(
        select(MallAftersaleItem).where(MallAftersaleItem.aftersale_id == aftersale.id)
    )
    accepted = await receive_return(
        db_session,
        operator,
        aftersale.id,
        ReturnReceipt(
            expectedVersion=aftersale.version,
            result="partially_accepted",
            sellableItems=[SellableReturnLine(aftersaleItemId=str(aftersale_item.id), quantity=1)],
            reason="一件完好，一件破损",
        ),
        key="aftersale-return-receive-001",
    )
    await db_session.commit()

    assert accepted.status == "awaiting_refund" and accepted.receipt_result == "partially_accepted"
    await db_session.refresh(aftersale_item)
    assert aftersale_item.stock_return_quantity == 1
    assert skus[1].available_qty == before_available + 1
    assert skus[1].reserved_qty == 0 and items[1].reservation_status == "sold"
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(MallStockMovement)
            .where(MallStockMovement.kind == "return")
        )
        == 1
    )


@pytest.mark.asyncio
async def test_withdraw_before_financial_submission_releases_hold_but_unknown_never_does(
    db_session, monkeypatch
):
    from src.schemas.mall_aftersale import ReasonAction
    from src.services.mall_aftersale_service import apply_aftersale, withdraw_aftersale

    buyer, order, _, items = await paid_order(db_session, monkeypatch)
    line = items[1]
    aftersale = await apply_aftersale(
        db_session, buyer, request(order, line), key="aftersale-withdraw-create-001"
    )
    withdrawn = await withdraw_aftersale(
        db_session,
        buyer,
        aftersale.id,
        ReasonAction(expectedVersion=aftersale.version, reason="重新考虑"),
        key="aftersale-withdraw-before-submit-001",
    )
    assert withdrawn.status == "withdrawn" and order.refund_reserved_cent == 0

    again = await apply_aftersale(
        db_session, buyer, request(order, line), key="aftersale-unknown-create-001"
    )
    again.status = "refunding"
    with pytest.raises(ConflictException):
        await withdraw_aftersale(
            db_session,
            buyer,
            again.id,
            ReasonAction(expectedVersion=again.version, reason="资金请求已提交"),
            key="aftersale-withdraw-unknown-001",
        )
    assert order.refund_reserved_cent == 5000 and line.aftersale_reserved_quantity == 1


@pytest.mark.asyncio
async def test_out_of_window_request_is_recorded_for_manual_review_without_reserving_money(
    db_session, monkeypatch
):
    from src.services.mall_aftersale_service import apply_aftersale

    buyer, order, _, items = await paid_order(db_session, monkeypatch)
    order.status = "completed"
    order.received_at = utc_now() - timedelta(days=30)
    order.policy_snapshot = {**(order.policy_snapshot or {}), "aftersaleDays": 15}
    await db_session.flush()

    aftersale = await apply_aftersale(
        db_session,
        buyer,
        request(order, items[1]),
        key="aftersale-window-manual-001",
    )
    assert aftersale.status == "disputed"
    assert aftersale.reserved_refund_cent == 0
    assert order.refund_reserved_cent == 0 and items[1].aftersale_reserved_quantity == 0


@pytest.mark.asyncio
async def test_freight_only_request_reserves_only_original_freight(db_session, monkeypatch):
    from src.services.mall_aftersale_service import apply_aftersale

    buyer, order, _, items = await paid_order(db_session, monkeypatch)
    data = request(order, items[0], scope="freight_only")
    aftersale = await apply_aftersale(db_session, buyer, data, key="aftersale-freight-only-001")
    assert aftersale.goods_refund_cent == 0
    assert aftersale.freight_refund_cent == aftersale.reserved_refund_cent == 1000
    assert order.refund_reserved_cent == 1000
