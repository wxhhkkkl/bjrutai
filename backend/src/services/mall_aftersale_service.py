"""Order-locked aftersale holds, review, return inspection and safe restocking."""

from copy import deepcopy
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select

from ..api.mall_deps import require_mall_admin_permission
from ..core.exceptions import ConflictException, ForbiddenException, NotFoundException
from ..models.audit import AuditLog
from ..models.mall_base import utc_now
from ..models.mall_catalog import MallSku, MallStockMovement
from ..models.mall_finance import MallPayment
from ..models.mall_operations import MallFile, MallSettings
from ..models.mall_trade import (
    MallAftersale,
    MallAftersaleItem,
    MallOrder,
    MallOrderItem,
)
from ..schemas.mall_aftersale import (
    AftersaleCreate,
    AftersaleDecision,
    ReturnReceipt,
    ReturnShipment,
)
from .mall_audit_service import record_mall_admin_audit
from .mall_command_service import complete_mall_command, reserve_mall_command
from .mall_notification_service import aftersale_status_label, notify_mall_buyer
from .mall_order_service import owned_order


async def _owned_aftersale(db, actor, identity, *, lock=False):
    row = await db.scalar(
        select(MallAftersale)
        .where(MallAftersale.id == identity, MallAftersale.buyer_user_id == actor.actor_id)
        .execution_options(populate_existing=True)
    )
    if actor.actor_type != "user" or row is None:
        raise NotFoundException(message="售后记录不存在")
    order = await owned_order(db, actor, row.order_id, lock=True)
    if lock:
        row = await db.scalar(
            select(MallAftersale)
            .where(MallAftersale.id == identity, MallAftersale.order_id == order.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    return order, row


async def _locked_order_items(db, order_id):
    rows = await db.scalars(
        select(MallOrderItem)
        .where(MallOrderItem.order_id == order_id)
        .order_by(MallOrderItem.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return list(rows)


async def _locked_aftersale(db, identity):
    row = await db.get(MallAftersale, identity, populate_existing=True)
    if row is None:
        raise NotFoundException(message="售后记录不存在")
    order = await db.scalar(
        select(MallOrder)
        .where(MallOrder.id == row.order_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if order is None:
        raise NotFoundException(message="商城订单不存在")
    row = await db.scalar(
        select(MallAftersale)
        .where(MallAftersale.id == identity, MallAftersale.order_id == order.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise NotFoundException(message="售后记录不存在")
    return order, row


async def _admin(db, actor, permission):
    if actor.actor_type != "admin":
        raise ForbiddenException(message="仅后台授权人员可处理售后")
    return await require_mall_admin_permission(
        {"sub": str(actor.actor_id), "user_type": "admin"},
        db,
        permission,
        current=True,
    )


def _audit_user(db, actor, action, aftersale):
    db.add(
        AuditLog(
            user_id=actor.actor_id,
            action=action,
            entity_type="mall_aftersale",
            entity_id=str(aftersale.id),
            detail={"status": aftersale.status, "version": aftersale.version},
        )
    )


async def _replay(db, intent, *, order_id=None):
    if intent.created:
        return None
    if intent.command.status != "completed" or not intent.command.entity_id:
        raise ConflictException(message="原售后请求仍在处理中，请查询原记录")
    row = await db.get(MallAftersale, intent.command.entity_id, populate_existing=True)
    if row is None or (order_id is not None and row.order_id != order_id):
        raise ConflictException(message="原售后请求关联不一致")
    return row


async def _verify_proofs(db, actor, order, proof_file_ids):
    if not proof_file_ids:
        return
    files = (
        await db.scalars(
            select(MallFile)
            .where(MallFile.id.in_([int(value) for value in proof_file_ids]))
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
    ).all()
    by_id = {str(row.id): row for row in files}
    if len(by_id) != len(proof_file_ids):
        raise ConflictException(message="售后凭证不存在或尚未核验")
    for identity in proof_file_ids:
        row = by_id[identity]
        if (
            row.owner_actor_type != actor.actor_type
            or row.owner_actor_id != actor.actor_id
            or row.order_id != order.id
            or row.purpose != "aftersale_proof"
            or row.status not in {"verified", "bound"}
        ):
            raise ForbiddenException(message="售后凭证与本人或订单不匹配")


def _return_window_expired(order):
    policy = order.policy_snapshot or {}
    days = policy.get("aftersaleDays")
    anchor = order.received_at or order.shipped_at
    return (
        type(days) is int
        and days > 0
        and anchor is not None
        and anchor < utc_now() - timedelta(days=days)
    )


async def _payment_is_verified(db, order):
    payment = await db.scalar(
        select(MallPayment)
        .where(
            MallPayment.id == order.active_payment_id,
            MallPayment.order_id == order.id,
        )
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    if (
        order.status not in {"pending_shipment", "pending_receipt", "completed"}
        or not order.paid_amount_cent
        or payment is None
        or payment.status != "succeeded"
        or payment.amount_cent != order.paid_amount_cent
        or payment.confirmed_at is None
    ):
        raise ConflictException(message="订单尚无可核实的成功收款，不能申请售后")
    return payment


def _auto_refund_eligible(order, aftersale, items):
    """Unshipped physical goods may be refunded without manual merchant review."""
    if (
        aftersale.status != "submitted"
        or aftersale.method != "refund_only"
        or order.status != "pending_shipment"
        or order.shipped_at is not None
    ):
        return False
    if (order.policy_snapshot or {}).get("deliveryMethod") == "virtual":
        return False
    return all(
        (item.product_snapshot or {}).get("deliveryMethod", "express") != "virtual"
        for item in items
    )


async def apply_aftersale(db, actor, data: AftersaleCreate, *, key):
    """Reserve the request once against a locked, verified paid order."""
    if actor.actor_type != "user":
        raise ForbiddenException(message="后台账号不能代替买家提交售后")
    order = await owned_order(db, actor, int(data.order_id), lock=True)
    payload = {"orderId": data.order_id, **data.model_dump(mode="json")}
    intent = await reserve_mall_command(
        db, actor=actor, action="createMallAftersale", key=key, payload=payload
    )
    replay = await _replay(db, intent, order_id=order.id)
    if replay:
        return replay
    if order.version != data.expected_order_version:
        raise ConflictException(message="订单版本已变化，请重新读取订单")
    await _payment_is_verified(db, order)
    await _verify_proofs(db, actor, order, data.proof_file_ids)
    items = await _locked_order_items(db, order.id)
    items_by_id = {item.id: item for item in items}
    if not items:
        raise ConflictException(message="订单商品明细缺失，请联系商家处理")

    selected = []
    goods_cent = 0
    requested = {int(line.order_item_id): line.quantity for line in data.items}
    for identity, quantity in requested.items():
        line = items_by_id.get(identity)
        if line is None:
            raise NotFoundException(message="申请商品不属于此订单")
        if data.method == "return_refund" and line.product_snapshot.get("supportsReturn") is False:
            raise ConflictException(message="所选商品不支持退货退款，可申请仅退款")
        remaining = line.quantity - line.refunded_quantity - line.aftersale_reserved_quantity
        if quantity > remaining:
            raise ConflictException(message="申请数量超过可售后数量")
        amount = line.unit_price_cent * quantity
        if amount <= 0 or amount > line.line_amount_cent - line.refunded_goods_cent:
            raise ConflictException(message="申请商品退款金额超过原订单可退金额")
        selected.append((line, quantity, amount))
        goods_cent += amount

    if data.scope == "freight_only":
        if order.shipped_at is not None or order.status != "pending_shipment":
            raise ConflictException(message="仅运费申请仅支持未发货订单")
        if order.refunded_freight_cent or order.freight_amount_cent <= order.refund_reserved_cent:
            raise ConflictException(message="订单没有可申请的运费退款余额")
        freight_cent = order.freight_amount_cent - order.refunded_freight_cent
    else:
        freight_cent = 0
        all_remaining = all(
            (line.id in requested and requested[line.id] == line.quantity - line.refunded_quantity)
            for line in items
            if line.quantity > line.refunded_quantity
        ) and all(line.aftersale_reserved_quantity == 0 for line in items)
        if (
            order.status == "pending_shipment"
            and order.shipped_at is None
            and all_remaining
            and not order.refunded_freight_cent
        ):
            freight_cent = order.freight_amount_cent

    total_cent = goods_cent + freight_cent
    if total_cent <= 0:
        raise ConflictException(message="售后金额必须大于零")
    remaining_cent = (
        order.paid_amount_cent
        - order.refunded_goods_cent
        - order.refunded_freight_cent
        - order.refund_reserved_cent
    )
    if total_cent > remaining_cent:
        raise ConflictException(message="申请金额超过原订单可退款余额")

    expired = _return_window_expired(order)
    row = MallAftersale(
        aftersale_no="A" + uuid4().hex[:31],
        order_id=order.id,
        buyer_user_id=actor.actor_id,
        method=data.method,
        status="disputed" if expired else "submitted",
        reason=data.reason,
        description=data.description,
        proof_file_ids=[int(value) for value in data.proof_file_ids],
        goods_refund_cent=goods_cent,
        freight_refund_cent=freight_cent,
        reserved_refund_cent=0 if expired else total_cent,
    )
    db.add(row)
    await db.flush()
    for line, quantity, amount in selected:
        db.add(
            MallAftersaleItem(
                aftersale_id=row.id,
                order_item_id=line.id,
                quantity=quantity,
                goods_refund_cent=amount,
                stock_return_quantity=0,
                active_slot=None if expired else 1,
            )
        )
        if not expired:
            line.aftersale_reserved_quantity += quantity
            line.version += 1
    if not expired:
        order.refund_reserved_cent += total_cent
    else:
        row.audit_reason = "超过订单售后窗口，需商家人工核实"
    row.version += 1
    order.version += 1
    _audit_user(
        db,
        actor,
        "mall_aftersale_submitted" if not expired else "mall_aftersale_manual_review",
        row,
    )
    if _auto_refund_eligible(order, row, items):
        from .mall_refund_service import queue_refund_request

        row.status = "awaiting_refund"
        # No admin requested this refund: policy queued it from the buyer's
        # own request, so the requester is recorded as absent rather than
        # falsely attributed to an admin account.
        await queue_refund_request(
            db, order=order, aftersale=row, requested_by=None
        )
        _audit_user(db, actor, "mall_aftersale_auto_refund_requested", row)
        await notify_mall_buyer(
            db,
            buyer_user_id=order.buyer_user_id,
            event_key=f"mall:aftersale:{row.id}:auto-refund",
            title="商城退款已自动受理",
            summary=f"订单号 {order.order_no} 未发货，退款已自动提交，将原路退回。",
            target=f"/pages/mall-aftersale-detail/index?id={row.id}",
        )
    await complete_mall_command(db, intent, entity_type="mall_aftersale", entity_id=row.id)
    await db.flush()
    return row


async def _release_hold(db, order, aftersale):
    aftersale_items = (
        await db.scalars(
            select(MallAftersaleItem)
            .where(MallAftersaleItem.aftersale_id == aftersale.id)
            .order_by(MallAftersaleItem.order_item_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).all()
    order_items = {item.id: item for item in await _locked_order_items(db, order.id)}
    if aftersale.reserved_refund_cent:
        if order.refund_reserved_cent < aftersale.reserved_refund_cent:
            raise ConflictException(message="退款占用与订单汇总不一致，请核实")
        order.refund_reserved_cent -= aftersale.reserved_refund_cent
        aftersale.reserved_refund_cent = 0
    for line in aftersale_items:
        item = order_items.get(line.order_item_id)
        if item is None or item.aftersale_reserved_quantity < line.quantity:
            raise ConflictException(message="商品售后数量占用不一致，请核实")
        item.aftersale_reserved_quantity -= line.quantity
        item.version += 1
        line.active_slot = None
        line.version += 1


async def _aftersale_command(db, actor, name, key, payload, identity):
    intent = await reserve_mall_command(db, actor=actor, action=name, key=key, payload=payload)
    if intent.created:
        return intent, None
    if intent.command.status != "completed" or not intent.command.entity_id:
        raise ConflictException(message="原售后操作仍在处理中，请查询原记录")
    if intent.command.entity_id != identity:
        raise ConflictException(message="原售后操作关联不一致")
    row = await db.get(MallAftersale, identity, populate_existing=True)
    if row is None:
        raise ConflictException(message="原售后记录不存在")
    return intent, row


async def _finish_admin_action(db, actor, action, aftersale, intent):
    await record_mall_admin_audit(
        db,
        actor=actor,
        action=action,
        entity_type="mall_aftersale",
        entity_id=str(aftersale.id),
        detail={"status": aftersale.status, "version": aftersale.version},
    )
    await complete_mall_command(db, intent, entity_type="mall_aftersale", entity_id=aftersale.id)
    await db.flush()
    return aftersale


async def decide_aftersale(db, actor, identity, data: AftersaleDecision, *, key):
    actor = await _admin(db, actor, "mall.aftersales.review")
    order, aftersale = await _locked_aftersale(db, identity)
    payload = {"aftersaleId": identity, **data.model_dump(mode="json")}
    intent, replay = await _aftersale_command(
        db, actor, "decideMallAftersale", key, payload, identity
    )
    if replay:
        return replay
    if aftersale.version != data.expected_version or aftersale.status != "submitted":
        raise ConflictException(message="售后状态或版本已变化")
    if data.decision == "reject":
        await _release_hold(db, order, aftersale)
        aftersale.status = "rejected"
        aftersale.audit_reason = data.reason
    else:
        requested_freight = (
            aftersale.freight_refund_cent
            if data.freight_refund_cent is None
            else data.freight_refund_cent
        )
        remaining_freight = order.freight_amount_cent - order.refunded_freight_cent
        if requested_freight > remaining_freight:
            raise ConflictException(message="批准运费超过订单原运费余额")
        updated_total = aftersale.goods_refund_cent + requested_freight
        order_capacity = (
            order.paid_amount_cent
            - order.refunded_goods_cent
            - order.refunded_freight_cent
            - order.refund_reserved_cent
            + aftersale.reserved_refund_cent
        )
        if updated_total > order_capacity:
            raise ConflictException(message="批准金额超过原订单可退款余额")
        order.refund_reserved_cent += updated_total - aftersale.reserved_refund_cent
        aftersale.freight_refund_cent = requested_freight
        aftersale.reserved_refund_cent = updated_total
        aftersale.audit_reason = data.reason
        aftersale.audit_by = actor.actor_id
        if aftersale.method == "return_refund":
            settings = await db.get(MallSettings, 1, populate_existing=True)
            if settings is None or not settings.return_address_snapshot:
                raise ConflictException(message="退货地址尚未配置，不能通过退货申请")
            if (
                data.return_address_version is not None
                and data.return_address_version != settings.version
            ):
                raise ConflictException(message="退货地址已变化，请重新确认")
            snapshots = (
                await db.scalars(
                    select(MallOrderItem.product_snapshot)
                    .join(MallAftersaleItem, MallAftersaleItem.order_item_id == MallOrderItem.id)
                    .where(MallAftersaleItem.aftersale_id == aftersale.id)
                    .order_by(MallOrderItem.id)
                )
            ).all()
            fallback = settings.return_instructions or ""
            by_product = dict.fromkeys(
                (snapshot["name"], (snapshot.get("returnInstructions") or "").strip() or fallback)
                for snapshot in snapshots
            )
            descriptions = {description for _, description in by_product}
            instructions = (
                next(iter(descriptions), fallback)
                if len(descriptions) <= 1
                else "\n".join(
                    f"{name}：{description}" for name, description in by_product if description
                )
            )
            aftersale.return_address_snapshot = {
                **deepcopy(settings.return_address_snapshot),
                "settingsVersion": settings.version,
                "instructions": instructions,
            }
            aftersale.status = "awaiting_return"
        else:
            aftersale.status = "awaiting_refund"
    aftersale.version += 1
    order.version += 1
    await _finish_admin_action(db, actor, "mall_aftersale_decided", aftersale, intent)
    await notify_mall_buyer(
        db,
        buyer_user_id=order.buyer_user_id,
        event_key=f"mall:aftersale:{aftersale.id}:status:{aftersale.version}",
        title="商城售后进度已更新",
        summary=(
            f"订单号 {order.order_no} 的售后状态已更新为“"
            f"{aftersale_status_label(aftersale.status)}”。"
        ),
        target=f"/pages/mall-aftersale-detail/index?id={aftersale.id}",
    )
    return aftersale


async def withdraw_aftersale(db, actor, identity, data, *, key):
    order, aftersale = await _owned_aftersale(db, actor, identity, lock=True)
    payload = {"aftersaleId": identity, **data.model_dump(mode="json")}
    intent, replay = await _aftersale_command(
        db, actor, "withdrawMallAftersale", key, payload, identity
    )
    if replay:
        return replay
    if aftersale.version != data.expected_version or aftersale.status not in {
        "submitted",
        "awaiting_return",
    }:
        raise ConflictException(message="资金已提交或售后阶段不允许撤回")
    if aftersale.status == "awaiting_return" and aftersale.return_sent_at is not None:
        raise ConflictException(message="已寄回商品不能撤回，请联系商家处理")
    await _release_hold(db, order, aftersale)
    aftersale.status = "withdrawn"
    aftersale.audit_reason = data.reason
    aftersale.version += 1
    order.version += 1
    _audit_user(db, actor, "mall_aftersale_withdrawn", aftersale)
    await complete_mall_command(db, intent, entity_type="mall_aftersale", entity_id=aftersale.id)
    await db.flush()
    return aftersale


async def submit_return_shipment(db, actor, identity, data: ReturnShipment, *, key):
    order, aftersale = await _owned_aftersale(db, actor, identity, lock=True)
    payload = {"aftersaleId": identity, **data.model_dump(mode="json")}
    intent, replay = await _aftersale_command(
        db, actor, "submitMallReturnShipment", key, payload, identity
    )
    if replay:
        return replay
    if aftersale.version != data.expected_version or aftersale.status != "awaiting_return":
        raise ConflictException(message="当前售后阶段不能登记退货运单")
    aftersale.return_company = data.courier_code
    aftersale.return_tracking_no = data.tracking_no
    aftersale.return_sent_at = utc_now()
    aftersale.status = "awaiting_receipt"
    aftersale.version += 1
    order.version += 1
    _audit_user(db, actor, "mall_return_shipment_submitted", aftersale)
    await complete_mall_command(db, intent, entity_type="mall_aftersale", entity_id=aftersale.id)
    await db.flush()
    await notify_mall_buyer(
        db,
        buyer_user_id=order.buyer_user_id,
        event_key=f"mall:aftersale:{aftersale.id}:status:{aftersale.version}",
        title="商城退货物流已登记",
        summary=f"订单号 {order.order_no} 的退货物流已登记，等待商家验收。",
        target=f"/pages/mall-aftersale-detail/index?id={aftersale.id}",
    )
    return aftersale


async def receive_return(db, actor, identity, data: ReturnReceipt, *, key):
    actor = await _admin(db, actor, "mall.returns.receive")
    order, aftersale = await _locked_aftersale(db, identity)
    payload = {"aftersaleId": identity, **data.model_dump(mode="json")}
    intent, replay = await _aftersale_command(
        db, actor, "receiveMallReturn", key, payload, identity
    )
    if replay:
        return replay
    if aftersale.version != data.expected_version or aftersale.status != "awaiting_receipt":
        raise ConflictException(message="当前售后阶段不能验收退货")
    lines = (
        await db.scalars(
            select(MallAftersaleItem)
            .where(MallAftersaleItem.aftersale_id == aftersale.id)
            .order_by(MallAftersaleItem.order_item_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).all()
    if not lines:
        raise ConflictException(message="退货申请缺少商品明细")
    requested = {line.id: line for line in lines}
    sellable = {int(row.aftersale_item_id): row.quantity for row in data.sellable_items}
    if any(identity not in requested for identity in sellable):
        raise ConflictException(message="验收商品不属于此售后")
    if any(quantity > requested[identity].quantity for identity, quantity in sellable.items()):
        raise ConflictException(message="可售验收数量超过申请退货数量")
    accepted = sum(sellable.values())
    total = sum(line.quantity for line in lines)
    if data.result == "accepted" and accepted != total:
        raise ConflictException(message="全部验收合格时须覆盖申请的全部商品数量")
    if data.result == "partially_accepted" and not 0 < accepted < total:
        raise ConflictException(message="部分验收须有合格数量且少于申请数量")
    if data.result == "disputed" and sellable:
        raise ConflictException(message="争议验收不能同时回库商品")

    if data.result == "disputed":
        aftersale.status = "disputed"
    else:
        order_items = {row.id: row for row in await _locked_order_items(db, order.id)}
        for aftersale_item in lines:
            order_item = order_items.get(aftersale_item.order_item_id)
            if order_item is None:
                raise ConflictException(message="退货关联订单明细已丢失")
            order_item.returned_quantity += aftersale_item.quantity
            order_item.version += 1
            qty = sellable.get(aftersale_item.id, 0)
            aftersale_item.stock_return_quantity = qty
            aftersale_item.inspection_reason = data.reason
            aftersale_item.version += 1
            if qty:
                sku = await db.scalar(
                    select(MallSku)
                    .where(MallSku.id == order_item.sku_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                if sku is None:
                    raise ConflictException(message="退货商品规格不存在")
                before = {"available": sku.available_qty, "reserved": sku.reserved_qty}
                sku.available_qty += qty
                sku.version += 1
                db.add(
                    MallStockMovement(
                        sku_id=sku.id,
                        event_key=f"aftersale:{aftersale_item.id}:sellable-return",
                        order_item_id=order_item.id,
                        aftersale_item_id=aftersale_item.id,
                        kind="return",
                        available_delta=qty,
                        reserved_delta=0,
                        before=before,
                        after={"available": sku.available_qty, "reserved": sku.reserved_qty},
                        actor_type="admin",
                        actor_id=actor.actor_id,
                        reason=data.reason,
                    )
                )
        aftersale.status = "awaiting_refund"
    aftersale.received_at = utc_now()
    aftersale.receipt_result = data.result
    aftersale.audit_reason = data.reason
    aftersale.audit_by = actor.actor_id
    aftersale.version += 1
    order.version += 1
    await _finish_admin_action(db, actor, "mall_return_received", aftersale, intent)
    await notify_mall_buyer(
        db,
        buyer_user_id=order.buyer_user_id,
        event_key=f"mall:aftersale:{aftersale.id}:status:{aftersale.version}",
        title="商城退货验收结果已更新",
        summary=(
            f"订单号 {order.order_no} 的售后状态已更新为“"
            f"{aftersale_status_label(aftersale.status)}”。"
        ),
        target=f"/pages/mall-aftersale-detail/index?id={aftersale.id}",
    )
    return aftersale
