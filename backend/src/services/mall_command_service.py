"""Persistent command idempotency for every mall write path."""

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.mall_deps import MallActor
from ..core.exceptions import ConflictException
from ..models.mall_operations import MallCommand

# Commands store the contract operationId as the action; unknown actions fail closed.
ADMIN_COMMAND_PERMISSIONS: dict[str, str] = {
    "createAdminMallCategory": "mall.products.write",
    "updateAdminMallCategory": "mall.products.write",
    "createAdminMallProduct": "mall.products.write",
    "updateAdminMallProduct": "mall.products.write",
    "setMallProductStatus": "mall.products.write",
    "copyMallProduct": "mall.products.write",
    "adjustMallStock": "mall.stock.write",
    "noteMallOrder": "mall.orders.write",
    "cancelAdminMallOrder": "mall.orders.write",
    "shipMallOrder": "mall.shipments.write",
    "releaseMallFulfillment": "mall.fulfillment.release",
    "correctMallTracking": "mall.shipments.write",
    "syncMallShipment": "mall.shipments.write",
    "decideMallAftersale": "mall.aftersales.review",
    "receiveMallReturn": "mall.returns.receive",
    "executeMallRefund": "mall.refunds.execute",
    "queryMallPayment": "mall.payments.query",
    "exportMallPayment": "mall.finance.export",
    "queryMallRefund": "mall.refunds.query",
    "exportMallRefund": "mall.finance.export",
    "retryMallRefund": "mall.refunds.execute",
    "releaseMallBilling": "mall.billing.release",
    "claimMallInvoice": "mall.invoices.write",
    "needMallInvoiceInfo": "mall.invoices.write",
    "recordMallInvoice": "mall.invoices.write",
    "replaceMallInvoiceFile": "mall.invoices.write",
    "recordMallRedInvoice": "mall.invoices.write",
    "markMallRedPending": "mall.invoices.write",
    "getAdminMallUploadTicket": "mall.files.write",
    "verifyAdminMallFile": "mall.files.write",
    "attributeMallConsumption": "mall.attribution.write",
    "reviewPerformanceAdjustment": "performance.settle",
    "rejectPerformanceAdjustment": "performance.settle",
    "reconcilePerformanceAdjustment": "performance.settle",
    "createMallReconciliation": "mall.reconciliations.write",
    "addMallDifference": "mall.reconciliations.write",
    "updateMallDifference": "mall.reconciliations.write",
    "closeMallReconciliation": "mall.reconciliations.write",
    "updateMallSettings": "mall.settings.write",
    "refreshMallLogistics": "mall.shipments.write",
}


@dataclass(frozen=True)
class MallCommandReservation:
    command: MallCommand
    created: bool


def canonical_payload_hash(payload: dict[str, Any]) -> str:
    """Hash canonical JSON without ever persisting the request body itself."""
    try:
        encoded = json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ConflictException(message="请求内容无法执行幂等校验") from exc
    return hashlib.sha256(encoded).hexdigest()


async def _find_command(
    db: AsyncSession,
    *,
    actor: MallActor,
    action: str,
    key: str,
    lock: bool = False,
) -> MallCommand | None:
    statement = select(MallCommand).where(
        MallCommand.actor_type == actor.actor_type,
        MallCommand.actor_id == actor.actor_id,
        MallCommand.action == action,
        MallCommand.key == key,
    )
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return (await db.execute(statement)).scalar_one_or_none()


async def reserve_mall_command(
    db: AsyncSession,
    *,
    actor: MallActor,
    action: str,
    key: str,
    payload: dict[str, Any],
) -> MallCommandReservation:
    """Create or safely replay a durable command intent.

    A unique index protects concurrent workers.  The nested transaction keeps a
    loser of the insert race from rolling back unrelated business work.
    """
    payload_hash = canonical_payload_hash(payload)
    existing = await _find_command(db, actor=actor, action=action, key=key)
    if existing is not None:
        if existing.payload_hash != payload_hash:
            raise ConflictException(message="幂等键对应的请求内容不一致")
        return MallCommandReservation(command=existing, created=False)

    command = MallCommand(
        actor_type=actor.actor_type,
        actor_id=actor.actor_id,
        action=action,
        key=key,
        payload_hash=payload_hash,
        status="running",
    )
    try:
        async with db.begin_nested():
            db.add(command)
            await db.flush()
    except IntegrityError:
        existing = await _find_command(db, actor=actor, action=action, key=key, lock=True)
        if existing is None:
            raise
        if existing.payload_hash != payload_hash:
            raise ConflictException(message="幂等键对应的请求内容不一致")
        return MallCommandReservation(command=existing, created=False)
    return MallCommandReservation(command=command, created=True)


async def complete_mall_command(
    db: AsyncSession,
    reservation: MallCommandReservation,
    *,
    entity_type: str,
    entity_id: int,
    result_code: str = "ok",
) -> MallCommand:
    """Store a safe reference to the completed result in the same transaction."""
    command = reservation.command
    command.status = "completed"
    command.entity_type = entity_type
    command.entity_id = entity_id
    command.result_code = result_code
    db.add(command)
    await db.flush()
    return command
