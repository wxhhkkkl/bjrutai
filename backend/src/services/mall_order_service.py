"""Atomic local orders. Caller commits or rolls back; no external I/O here."""

from copy import deepcopy
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import delete, select

from ..core.exceptions import ConflictException, NotFoundException
from ..models.audit import AuditLog
from ..models.mall_base import utc_now
from ..models.mall_catalog import MallProduct, MallSku, MallStockMovement
from ..models.mall_operations import MallSettings
from ..models.mall_trade import MallCartItem, MallOrder, MallOrderItem
from .mall_address_service import lock_buyer, owned_address
from .mall_checkout_service import validate_quote
from .mall_command_service import complete_mall_command, reserve_mall_command
from .mall_consent_service import record_mall_notice_acknowledgement
from .mall_job_service import enqueue_mall_job


async def owned_order(db, actor, identity, *, lock=False):
    statement = (
        select(MallOrder)
        .where(MallOrder.id == identity, MallOrder.buyer_user_id == actor.actor_id)
        .execution_options(populate_existing=True)
    )
    if lock:
        statement = statement.with_for_update()
    row = (await db.execute(statement)).scalar_one_or_none()
    if actor.actor_type != "user" or row is None:
        raise NotFoundException(message="订单不存在")
    return row


async def _current(db, model, identity, *, write=False):
    return (
        await db.execute(
            select(model)
            .where(model.id == identity)
            .with_for_update(read=not write)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


def audit_order(db, actor, order, action):
    db.add(
        AuditLog(
            user_id=actor.actor_id,
            action=action,
            entity_type="mall_order",
            entity_id=str(order.id),
            detail={"version": order.version, "status": order.status},
        )
    )


async def create_order(db, actor, data, *, key):
    await lock_buyer(db, actor)
    intent = await reserve_mall_command(
        db,
        actor=actor,
        action="createMallOrder",
        key=key,
        payload=data.model_dump(mode="json", exclude={"consent_confirmed"}),
    )
    if not intent.created:
        if intent.command.status != "completed":
            raise ConflictException(message="原订单仍在处理中")
        # Authorization is live, but the original quote need not still be valid.
        return await owned_order(db, actor, intent.command.entity_id)
    if data.consent_confirmed is not True:
        raise ConflictException(message="请确认订单及支付、配送资料用途后再提交")
    body, quote = await validate_quote(db, actor, data.quote_token, reserve_stock=True)
    if data.consent_version != quote["policyVersion"]:
        raise ConflictException(message="商城告知版本已变化，请重新确认")
    settings = await _current(db, MallSettings, 1)
    address = (
        await owned_address(db, actor, int(body.address_id), lock=True)
        if quote["requiresAddress"]
        else None
    )
    delivery_method = quote["deliveryMethod"]
    scope_keys = {
        "order_amount",
        "payment_status",
        "channel_transaction_reference",
        "delivery_status",
    }
    if delivery_method == "virtual":
        scope_keys.add("virtual_delivery_content")
    else:
        scope_keys.update({"recipient_contact", "delivery_address", "courier_tracking"})
    consent = await record_mall_notice_acknowledgement(
        db,
        actor,
        purposes={"payment", "fulfillment"},
        version=data.consent_version,
        current_version=quote["policyVersion"],
        confirmed=data.consent_confirmed,
        scope_keys=scope_keys,
    )
    order = MallOrder(
        order_no="M" + uuid4().hex[:31],
        buyer_user_id=actor.actor_id,
        goods_amount_cent=quote["goodsAmountCent"],
        freight_amount_cent=quote["freightAmountCent"],
        payable_amount_cent=quote["payableAmountCent"],
        buyer_note=data.buyer_note,
        expires_at=utc_now() + timedelta(minutes=settings.payment_minutes),
        consent_record_id=consent.id,
        address_snapshot=(
            {
                "id": str(address.id),
                "version": address.version,
                "recipientName": address.recipient_name,
                "phone": address.phone,
                "phoneMasked": address.phone_masked,
                "regionCodes": [address.province_code, address.city_code, address.district_code],
                "regionNames": list(address.region_names or []),
                "addressLine": address.address_line,
            }
            if address
            else {}
        ),
        policy_snapshot={
            "version": settings.version,
            "policyVersion": quote["policyVersion"],
            "deliveryMethod": delivery_method,
            "freightMode": (
                "none"
                if delivery_method == "virtual"
                else "fixed" if quote["freightAmountCent"] else "free"
            ),
            "freightCent": quote["freightAmountCent"],
            "blockedRegionCodes": quote["blockedRegionCodes"],
            "paymentMinutes": settings.payment_minutes,
            "autoReceiveDays": settings.auto_receive_days,
            "aftersaleDays": settings.aftersale_days,
            "invoiceIntent": data.invoice_intent,
        },
    )
    db.add(order)
    await db.flush()
    for line in quote["items"]:  # Already locked exclusively in ascending SKU ID order.
        sku = await _current(db, MallSku, int(line["skuId"]), write=True)
        product = await _current(db, MallProduct, sku.product_id)
        item = MallOrderItem(
            order_id=order.id,
            sku_id=sku.id,
            product_id=product.id,
            unit_price_cent=line["unitPriceCent"],
            quantity=line["quantity"],
            line_amount_cent=line["lineAmountCent"],
            reservation_status="reserved",
            product_snapshot={
                "name": product.name,
                "productType": line["productType"],
                "deliveryMethod": line["deliveryMethod"],
                "supportsReturn": product.supports_return,
                "returnInstructions": product.return_instructions,
                "skuCode": sku.sku_code,
                "options": deepcopy(sku.options),
                "optionsText": line["optionsText"],
                "coverFileId": str(product.cover_file_id) if product.cover_file_id else None,
            },
        )
        db.add(item)
        await db.flush()
        before = {"available": sku.available_qty, "reserved": sku.reserved_qty}
        sku.available_qty -= item.quantity
        sku.reserved_qty += item.quantity
        sku.version += 1
        db.add(
            MallStockMovement(
                sku_id=sku.id,
                order_item_id=item.id,
                event_key=f"order:{order.id}:reserve:{sku.id}",
                kind="reserve",
                available_delta=-item.quantity,
                reserved_delta=item.quantity,
                before=before,
                after={"available": sku.available_qty, "reserved": sku.reserved_qty},
                actor_type="user",
                actor_id=actor.actor_id,
                reason="下单占用",
            )
        )
    # Purchased lines leave the cart; unselected lines stay untouched.
    await db.execute(
        delete(MallCartItem).where(
            MallCartItem.user_id == actor.actor_id,
            MallCartItem.sku_id.in_([int(line["skuId"]) for line in quote["items"]]),
        )
    )
    job = await enqueue_mall_job(
        db,
        kind="mall_order_expire",
        entity_type="mall_order",
        entity_id=order.id,
        entity_version=order.version,
        dedupe_key=f"mall-order-expire:{order.id}",
    )
    job.next_run_at = order.expires_at
    audit_order(db, actor, order, "mall_order_created")
    await complete_mall_command(db, intent, entity_type="mall_order", entity_id=order.id)
    await db.flush()
    return order


async def close_never_paid_order(db, actor, identity, *, expected_version):
    """Only for an order with zero payment attempts. Channel history needs T046."""
    from .mall_order_close_service import close_never_paid_order as close

    return await close(db, actor, identity, expected_version=expected_version)
