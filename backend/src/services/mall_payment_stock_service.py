"""One conversion/release per reserved item after a verified payment fact."""

from sqlalchemy import select

from ..core.exceptions import ConflictException
from ..models.mall_catalog import MallSku, MallStockMovement
from ..models.mall_trade import MallOrderItem
from .mall_order_service import _current


async def locked_stock(db, order):
    items = (
        await db.scalars(
            select(MallOrderItem)
            .where(MallOrderItem.order_id == order.id)
            .order_by(MallOrderItem.sku_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).all()
    skus = {item.sku_id: await _current(db, MallSku, item.sku_id, write=True) for item in items}
    return items, skus


def is_reserved(items, skus):
    return bool(items) and all(
        item.reservation_status == "reserved" and skus[item.sku_id].reserved_qty >= item.quantity
        for item in items
    )


def stock_event(db, order, payment, items, skus, *, release):
    if not is_reserved(items, skus):
        raise ConflictException(message="付款关联的库存占用事实不一致")
    kind = "release" if release else "sale"
    for item in items:
        sku = skus[item.sku_id]
        before = {"available": sku.available_qty, "reserved": sku.reserved_qty}
        sku.reserved_qty -= item.quantity
        if release:
            sku.available_qty += item.quantity
        sku.version += 1
        item.reservation_status = "released" if release else "sold"
        item.version += 1
        db.add(
            MallStockMovement(
                sku_id=sku.id,
                order_item_id=item.id,
                event_key=f"payment:{payment.id}:{kind}:{sku.id}",
                kind=kind,
                available_delta=item.quantity if release else 0,
                reserved_delta=-item.quantity,
                before=before,
                after={"available": sku.available_qty, "reserved": sku.reserved_qty},
                actor_type="system",
                actor_id=0,
                reason="渠道关单核实释放" if release else "渠道收款核实转已售",
            )
        )
