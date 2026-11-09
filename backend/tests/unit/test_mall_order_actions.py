"""Buyer cancellation and pre-dispatch address changes use the original trade facts."""

from copy import deepcopy
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from src.core.exceptions import ConflictException, NotFoundException
from src.models.mall_base import utc_now
from src.models.mall_catalog import MallStockMovement
from src.models.mall_operations import MallJob
from src.schemas.mall_catalog import VersionAction
from src.schemas.mall_checkout import AddressWrite
from src.services.mall_address_service import save_address
from src.services.mall_order_service import create_order
from tests.mall_checkout_fixtures import ADDRESS
from tests.unit.test_mall_order_service import intent
from tests.unit.test_mall_payment_service import payable, success


async def unattempted(db, monkeypatch):
    actor, settings, _, skus, address, body = await intent(db, monkeypatch)
    order = await create_order(db, actor, body, key="order-actions-create-001")
    await db.commit()
    return actor, settings, skus, address, order


@pytest.mark.asyncio
async def test_cancel_never_attempted_closes_once_and_replays_after_version_change(
    db_session, monkeypatch
):
    from src.schemas.mall_checkout import OrderCancel
    from src.services.mall_order_action_service import cancel_order

    actor, _, skus, _, order = await unattempted(db_session, monkeypatch)
    data = OrderCancel(expectedVersion=order.version, reason="暂时不需要")
    command = await cancel_order(db_session, actor, order.id, data, key="cancel-order-intent-001")
    await db_session.commit()
    again = await cancel_order(db_session, actor, order.id, data, key="cancel-order-intent-001")
    assert command.id == again.id and order.status == "closed"
    assert order.close_requested_at and order.close_request_reason == "暂时不需要"
    assert [(s.available_qty, s.reserved_qty) for s in skus] == [(10, 0), (10, 0)]
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(MallStockMovement)
            .where(MallStockMovement.kind == "release")
        )
        == 2
    )


@pytest.mark.asyncio
async def test_cancel_attempted_is_durable_blocks_even_original_payment_replay(
    db_session, monkeypatch
):
    from src.schemas.mall_checkout import OrderCancel
    from src.services.mall_order_action_service import cancel_order
    from src.services.mall_payment_service import prepare_payment

    actor, order, skus, payment = await payable(db_session, monkeypatch)
    await cancel_order(
        db_session,
        actor,
        order.id,
        OrderCancel(expectedVersion=order.version, reason="取消购买"),
        key="cancel-attempted-intent-001",
    )
    await db_session.commit()
    assert order.status == "pending_payment" and order.close_requested_at
    assert skus[0].reserved_qty == 1
    assert await db_session.scalar(select(MallJob.id).where(MallJob.kind == "mall_order_close"))
    with pytest.raises(ConflictException):
        await prepare_payment(
            db_session,
            actor,
            order.id,
            VersionAction(expectedVersion=1),
            key="payment-prepare-intent-001",
        )
    assert payment.out_trade_no and payment.status == "creating"


@pytest.mark.asyncio
async def test_paid_cancel_is_rejected_and_conflicting_idempotency_key_is_rejected(
    db_session, monkeypatch
):
    from src.schemas.mall_checkout import OrderCancel
    from src.services.mall_order_action_service import cancel_order
    from src.services.mall_payment_service import apply_verified_payment

    actor, order, _, payment = await payable(db_session, monkeypatch)
    await apply_verified_payment(db_session, payment.id, success(payment, order))
    await db_session.commit()
    with pytest.raises(ConflictException):
        await cancel_order(
            db_session,
            actor,
            order.id,
            OrderCancel(expectedVersion=order.version, reason="已支付不能直接取消"),
            key="cancel-paid-intent-001",
        )


@pytest.mark.asyncio
async def test_address_change_uses_original_rules_and_preserves_money_stock_and_snapshots(
    db_session, monkeypatch
):
    from src.schemas.mall_checkout import OrderAddressChange
    from src.services.mall_order_action_service import change_order_address

    actor, settings, skus, _, order = await unattempted(db_session, monkeypatch)
    next_address = await save_address(
        db_session,
        actor,
        AddressWrite(
            **{
                **ADDRESS,
                "recipientName": "另一测试收件人",
                "addressLine": "另一虚构路456号",
            }
        ),
    )
    original_policy = deepcopy(order.policy_snapshot)
    settings.freight_cent = 9000
    settings.blocked_regions = ["110000"]
    await db_session.commit()
    data = OrderAddressChange(
        expectedVersion=order.version, addressId=str(next_address.id), reason="换收货地点"
    )
    result = await change_order_address(
        db_session, actor, order.id, data, key="change-address-intent-001"
    )
    await db_session.commit()
    assert result.address_snapshot["addressLine"] == "另一虚构路456号"
    assert result.policy_snapshot == original_policy
    assert result.freight_amount_cent == 1000 and result.payable_amount_cent == 21000
    assert [(s.available_qty, s.reserved_qty) for s in skus] == [(9, 1), (8, 2)]
    assert (
        await change_order_address(
            db_session, actor, order.id, data, key="change-address-intent-001"
        )
    ).id == order.id


@pytest.mark.parametrize(
    "invalid",
    [
        "blocked",
        "freight",
        "shipped",
        "cancelled",
        "archived",
        "consent",
        "alien",
        "aftersale",
        "expired",
        "consent_scene",
    ],
)
@pytest.mark.asyncio
async def test_address_change_rejects_invalid_state_without_mutating(
    db_session, monkeypatch, invalid
):
    from src.models.consent import ConsentRecord
    from src.schemas.mall_checkout import OrderAddressChange
    from src.services.mall_order_action_service import change_order_address

    actor, _, _, address, order = await unattempted(db_session, monkeypatch)
    if invalid == "blocked":
        order.policy_snapshot = {**order.policy_snapshot, "blockedRegionCodes": ["110000"]}
    if invalid == "freight":
        order.policy_snapshot = {**order.policy_snapshot, "freightCent": 3000}
    if invalid == "shipped":
        order.shipped_at = utc_now()
    if invalid == "cancelled":
        order.close_requested_at = utc_now()
    if invalid == "archived":
        address.archived_at = utc_now()
    if invalid == "consent":
        (await db_session.get(ConsentRecord, address.consent_record_id)).status = "revoked"
    if invalid == "alien":
        address.user_id = actor.actor_id + 50000
    if invalid == "expired":
        order.expires_at = utc_now() - timedelta(seconds=1)
    if invalid == "consent_scene":
        from src.models.consent import ConsentScene

        (await db_session.get(ConsentRecord, address.consent_record_id)).scene = (
            ConsentScene.REGISTRATION
        )
    if invalid == "aftersale":
        from src.models.mall_trade import MallAftersale

        db_session.add(
            MallAftersale(
                aftersale_no="active-aftersale-test",
                order_id=order.id,
                buyer_user_id=actor.actor_id,
                method="refund_only",
                reason="处理中",
            )
        )
    await db_session.commit()
    before = deepcopy(order.address_snapshot)
    with pytest.raises((ConflictException, NotFoundException)):
        await change_order_address(
            db_session,
            actor,
            order.id,
            OrderAddressChange(
                expectedVersion=order.version, addressId=str(address.id), reason="修正"
            ),
            key="invalid-address-intent-001",
        )
    assert order.address_snapshot == before


@pytest.mark.asyncio
async def test_paid_pre_dispatch_address_change_keeps_original_payment(db_session, monkeypatch):
    from src.schemas.mall_checkout import OrderAddressChange
    from src.services.mall_order_action_service import change_order_address
    from src.services.mall_payment_service import apply_verified_payment

    actor, order, _, payment = await payable(db_session, monkeypatch)
    await apply_verified_payment(db_session, payment.id, success(payment, order))
    await db_session.commit()
    address = await save_address(
        db_session, actor, AddressWrite(**{**ADDRESS, "phone": "13900001111"})
    )
    await db_session.commit()
    amount = order.paid_amount_cent
    await change_order_address(
        db_session,
        actor,
        order.id,
        OrderAddressChange(
            expectedVersion=order.version, addressId=str(address.id), reason="修改联系信息"
        ),
        key="paid-order-address-intent-001",
    )
    assert order.paid_amount_cent == amount and order.status == "pending_shipment"
    assert order.active_payment_id == payment.id and payment.status == "succeeded"


def test_close_intent_migration_has_a_lossless_downgrade_guard(monkeypatch):
    import importlib.util
    from pathlib import Path
    from unittest.mock import MagicMock

    path = (
        Path(__file__).resolve().parents[2] / "migrations/versions/028_mall_order_close_intent.py"
    )
    spec = importlib.util.spec_from_file_location("mall_close_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    operations = MagicMock()
    operations.get_bind.return_value.scalar.return_value = 1
    monkeypatch.setattr(module, "op", operations)
    with pytest.raises(RuntimeError, match="lossy downgrade"):
        module.downgrade()
    operations.drop_column.assert_not_called()
