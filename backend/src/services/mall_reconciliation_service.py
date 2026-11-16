"""Evidence-backed daily reconciliation without mutating payment facts."""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.mall_deps import MallActor, require_mall_admin_permission
from ..core.config import get_settings
from ..core.exceptions import (
    ConflictException,
    ForbiddenException,
    NotFoundException,
    ValidationException,
)
from ..models.mall_base import utc_now
from ..models.mall_finance import (
    MallPayment,
    MallReconciliationBatch,
    MallReconciliationDifference,
    MallRefund,
)
from ..models.mall_operations import MallFile
from ..models.mall_trade import MallOrder
from ..models.user import AdminAccount, AdminStatus
from ..schemas.mall_aftersale import ReasonAction
from ..schemas.mall_reconciliation import DifferenceCreate, DifferenceUpdate, ReconciliationCreate
from .mall_audit_service import record_mall_admin_audit
from .mall_catalog_query_service import _page
from .mall_command_service import complete_mall_command, reserve_mall_command
from .mall_order_text import safe_order_text

_BUSINESS_ZONE = ZoneInfo("Asia/Shanghai")


async def _require_admin(db: AsyncSession, actor: MallActor, permission: str) -> MallActor:
    if actor.actor_type != "admin":
        raise ForbiddenException(message="仅后台财务人员可执行商城对账操作")
    return await require_mall_admin_permission(
        {"sub": str(actor.actor_id), "user_type": "admin"},
        db,
        permission,
        current=True,
    )


def _day_utc_range(business_date: date) -> tuple[datetime, datetime]:
    """Return the Beijing business day as a half-open UTC-naive interval."""
    try:
        local_start = datetime.combine(business_date, time.min, tzinfo=_BUSINESS_ZONE)
        local_end = local_start + timedelta(days=1)
    except (OverflowError, ValueError) as exc:
        raise ValidationException(message="对账日期超出支持范围") from exc
    return (
        local_start.astimezone(timezone.utc).replace(tzinfo=None),
        local_end.astimezone(timezone.utc).replace(tzinfo=None),
    )


def _clean_note(value: str) -> str:
    note = safe_order_text(value).strip()
    if not note:
        raise ValidationException(message="处理说明不能为空")
    return note[:1000]


def _append_resolution(current: str | None, reason: str) -> str:
    note = _clean_note(reason)
    combined = f"{current}\n{note}" if current else note
    return combined[-1000:]


def serialize_reconciliation(batch: MallReconciliationBatch, *, open_difference_count: int) -> dict:
    return {
        "id": str(batch.id),
        "businessDate": batch.business_date.isoformat(),
        "status": batch.status,
        "expectedPaidCent": batch.expected_paid_cent,
        "expectedRefundCent": batch.expected_refund_cent,
        "localPaidCent": batch.local_paid_cent,
        "localRefundCent": batch.local_refund_cent,
        "openDifferenceCount": open_difference_count,
        "version": batch.version,
    }


def serialize_difference(difference: MallReconciliationDifference) -> dict:
    return {
        "id": str(difference.id),
        "batchId": str(difference.batch_id),
        "orderId": str(difference.order_id) if difference.order_id is not None else None,
        "externalReference": difference.external_reference,
        "differenceType": difference.difference_type,
        "expectedCent": difference.expected_cent,
        "actualCent": difference.actual_cent,
        "status": difference.status,
        "assignedTo": str(difference.assigned_to) if difference.assigned_to is not None else None,
        "resolution": difference.resolution,
        "evidenceFileIds": [str(value) for value in (difference.evidence_file_ids or [])],
        "version": difference.version,
    }


async def _batch_by_id(db: AsyncSession, identity: int, *, lock: bool = False):
    statement = select(MallReconciliationBatch).where(MallReconciliationBatch.id == identity)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    batch = await db.scalar(statement)
    if batch is None:
        raise NotFoundException(message="对账批次不存在")
    return batch


async def _open_difference_counts(db: AsyncSession, batch_ids: list[int]) -> dict[int, int]:
    if not batch_ids:
        return {}
    rows = (
        await db.execute(
            select(
                MallReconciliationDifference.batch_id,
                func.count(MallReconciliationDifference.id),
            )
            .where(
                MallReconciliationDifference.batch_id.in_(batch_ids),
                MallReconciliationDifference.status != "closed",
            )
            .group_by(MallReconciliationDifference.batch_id)
        )
    ).all()
    return {int(batch_id): int(count) for batch_id, count in rows}


async def _verified_statement_file(db: AsyncSession, actor: MallActor, identity: int) -> MallFile:
    file = await db.scalar(
        select(MallFile)
        .where(MallFile.id == identity)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if file is None:
        raise NotFoundException(message="对账账单文件不存在")
    if (
        file.owner_actor_type != "admin"
        or file.owner_actor_id != actor.actor_id
        or file.purpose != "reconciliation_evidence"
        or file.status != "verified"
        or file.order_id is not None
    ):
        raise ValidationException(message="账单必须是本人上传并核验通过的对账证据")
    return file


async def _verified_evidence_files(
    db: AsyncSession,
    actor: MallActor,
    identities: list[int],
    *,
    require_owner: bool,
) -> list[MallFile]:
    if not identities:
        return []
    files = (
        await db.scalars(
            select(MallFile)
            .where(MallFile.id.in_(identities))
            .order_by(MallFile.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).all()
    if len(files) != len(set(identities)):
        raise ValidationException(message="差异证据文件不存在")
    for file in files:
        if (
            file.purpose != "reconciliation_evidence"
            or file.status != "verified"
            or file.order_id is not None
            or (
                require_owner
                and (file.owner_actor_type != "admin" or file.owner_actor_id != actor.actor_id)
            )
        ):
            raise ValidationException(message="差异证据必须为已核验的商城对账文件")
    return files


async def _validate_assignee(db: AsyncSession, identity: str | None) -> int | None:
    if identity is None:
        return None
    account = await db.get(AdminAccount, int(identity), populate_existing=True)
    if account is None or account.status != AdminStatus.ACTIVE:
        raise ValidationException(message="差异只能指派给有效后台账号")
    return account.id


async def _command_replay(db: AsyncSession, reservation, model, *, entity_type: str):
    command = reservation.command
    if reservation.created:
        return None
    if command.status != "completed" or command.entity_type != entity_type or not command.entity_id:
        raise ConflictException(message="原对账操作仍在处理中")
    entity = await db.get(model, command.entity_id, populate_existing=True)
    if entity is None:
        raise ConflictException(message="原对账操作结果不存在，请核查审计记录")
    return entity


async def create_reconciliation(
    db: AsyncSession,
    actor: MallActor,
    data: ReconciliationCreate,
    *,
    key: str,
) -> MallReconciliationBatch:
    actor = await _require_admin(db, actor, "mall.reconciliations.write")
    reservation = await reserve_mall_command(
        db,
        actor=actor,
        action="createMallReconciliation",
        key=key,
        payload=data.model_dump(mode="json"),
    )
    replay = await _command_replay(
        db, reservation, MallReconciliationBatch, entity_type="mall_reconciliation_batch"
    )
    if replay is not None:
        return replay

    statement_file = await _verified_statement_file(db, actor, int(data.statement_file_id))
    seller_identity = (get_settings().mall_wechat_mchid or "").strip()
    if not seller_identity:
        raise ValidationException(message="支付商户主体未配置，不能创建对账批次")
    start_at, end_at = _day_utc_range(data.business_date)

    local_paid = await db.scalar(
        select(func.coalesce(func.sum(MallPayment.amount_cent), 0))
        .join(MallOrder, MallOrder.id == MallPayment.order_id)
        .where(
            MallPayment.status == "succeeded",
            MallPayment.currency == "CNY",
            MallPayment.mchid_snapshot == seller_identity,
            MallOrder.paid_at.is_not(None),
            MallOrder.paid_at >= start_at,
            MallOrder.paid_at < end_at,
        )
    )
    local_refund = await db.scalar(
        select(func.coalesce(func.sum(MallRefund.total_cent), 0))
        .join(MallPayment, MallPayment.id == MallRefund.payment_id)
        .where(
            MallRefund.status == "succeeded",
            MallPayment.currency == "CNY",
            MallPayment.mchid_snapshot == seller_identity,
            MallRefund.confirmed_at >= start_at,
            MallRefund.confirmed_at < end_at,
        )
    )

    duplicate = await db.scalar(
        select(MallReconciliationBatch.id).where(
            MallReconciliationBatch.business_date == data.business_date,
            MallReconciliationBatch.channel == "wechat",
            MallReconciliationBatch.seller_identity == seller_identity,
            MallReconciliationBatch.statement_sha256 == statement_file.sha256,
        )
    )
    if duplicate:
        raise ConflictException(message="该渠道账单已登记，不能重复创建对账批次")

    batch = MallReconciliationBatch(
        business_date=data.business_date,
        channel="wechat",
        seller_identity=seller_identity,
        status="draft",
        statement_file_id=statement_file.id,
        statement_sha256=statement_file.sha256,
        expected_paid_cent=data.expected_paid_cent,
        expected_refund_cent=data.expected_refund_cent,
        local_paid_cent=int(local_paid or 0),
        local_refund_cent=int(local_refund or 0),
        evidence_note=_clean_note(data.evidence_note),
        created_by=actor.actor_id,
    )
    try:
        async with db.begin_nested():
            db.add(batch)
            await db.flush()
    except IntegrityError as exc:
        raise ConflictException(message="同一渠道账单不能重复登记") from exc
    await complete_mall_command(
        db,
        reservation,
        entity_type="mall_reconciliation_batch",
        entity_id=batch.id,
    )
    await record_mall_admin_audit(
        db,
        actor=actor,
        action="mall_reconciliation_created",
        entity_type="mall_reconciliation_batch",
        entity_id=str(batch.id),
        detail={
            "businessDate": data.business_date.isoformat(),
            "sellerIdentity": seller_identity,
            "statementFileId": str(statement_file.id),
            "statementSha256": statement_file.sha256,
            "expectedPaidCent": batch.expected_paid_cent,
            "expectedRefundCent": batch.expected_refund_cent,
            "localPaidCent": batch.local_paid_cent,
            "localRefundCent": batch.local_refund_cent,
        },
    )
    return batch


async def list_reconciliations(db: AsyncSession, actor: MallActor, *, cursor=None, page_size=20):
    actor = await _require_admin(db, actor, "mall.reconciliations.read")
    if type(page_size) is not int or not 1 <= page_size <= 100:
        raise ValidationException(message="分页大小必须在1到100之间")
    batches, next_cursor, total = await _page(
        db,
        select(MallReconciliationBatch),
        MallReconciliationBatch,
        MallReconciliationBatch.id,
        mode=f"admin-mall-reconciliations:{actor.actor_id}",
        cursor=cursor,
        page_size=page_size,
        descending=True,
    )
    counts = await _open_difference_counts(db, [row.id for row in batches])
    return {
        "items": [
            serialize_reconciliation(row, open_difference_count=counts.get(row.id, 0))
            for row in batches
        ],
        "nextCursor": next_cursor,
        "total": total,
    }


async def get_reconciliation(db: AsyncSession, actor: MallActor, identity: int) -> dict:
    await _require_admin(db, actor, "mall.reconciliations.read")
    batch = await _batch_by_id(db, identity)
    count = await db.scalar(
        select(func.count(MallReconciliationDifference.id)).where(
            MallReconciliationDifference.batch_id == batch.id,
            MallReconciliationDifference.status != "closed",
        )
    )
    return serialize_reconciliation(batch, open_difference_count=int(count or 0))


async def add_difference(
    db: AsyncSession,
    actor: MallActor,
    batch_identity: int,
    data: DifferenceCreate,
    *,
    key: str,
) -> MallReconciliationDifference:
    actor = await _require_admin(db, actor, "mall.reconciliations.write")
    batch = await _batch_by_id(db, batch_identity, lock=True)
    reservation = await reserve_mall_command(
        db,
        actor=actor,
        action="addMallDifference",
        key=key,
        payload={"batchId": batch_identity, **data.model_dump(mode="json")},
    )
    replay = await _command_replay(
        db,
        reservation,
        MallReconciliationDifference,
        entity_type="mall_reconciliation_difference",
    )
    if replay is not None:
        if replay.batch_id != batch.id:
            raise ConflictException(message="原差异记录与当前批次不一致")
        return replay
    if batch.status == "closed":
        raise ConflictException(message="已关闭的对账批次不能新增差异")

    order_id = int(data.order_id) if data.order_id else None
    if order_id is not None:
        order_exists = await db.scalar(select(MallOrder.id).where(MallOrder.id == order_id))
        if order_exists is None:
            raise NotFoundException(message="差异关联订单不存在")
    assignee_id = await _validate_assignee(db, data.assigned_to)
    difference = MallReconciliationDifference(
        batch_id=batch.id,
        order_id=order_id,
        external_reference=(data.external_reference or None),
        difference_type=data.difference_type,
        expected_cent=data.expected_cent,
        actual_cent=data.actual_cent,
        status="open",
        assigned_to=assignee_id,
        resolution=_clean_note(data.reason),
        evidence_file_ids=[],
    )
    db.add(difference)
    batch.status = "processing"
    batch.version += 1
    await db.flush()
    await complete_mall_command(
        db,
        reservation,
        entity_type="mall_reconciliation_difference",
        entity_id=difference.id,
    )
    await record_mall_admin_audit(
        db,
        actor=actor,
        action="mall_reconciliation_difference_added",
        entity_type="mall_reconciliation_difference",
        entity_id=str(difference.id),
        detail={
            "batchId": str(batch.id),
            "differenceType": difference.difference_type,
            "expectedCent": difference.expected_cent,
            "actualCent": difference.actual_cent,
        },
    )
    return difference


async def list_differences(
    db: AsyncSession, actor: MallActor, batch_identity: int, *, cursor=None, page_size=20
):
    actor = await _require_admin(db, actor, "mall.reconciliations.read")
    await _batch_by_id(db, batch_identity)
    if type(page_size) is not int or not 1 <= page_size <= 100:
        raise ValidationException(message="分页大小必须在1到100之间")
    rows, next_cursor, total = await _page(
        db,
        select(MallReconciliationDifference).where(
            MallReconciliationDifference.batch_id == batch_identity
        ),
        MallReconciliationDifference,
        MallReconciliationDifference.id,
        mode=f"admin-mall-reconciliation-differences:{actor.actor_id}:{batch_identity}",
        cursor=cursor,
        page_size=page_size,
        descending=False,
    )
    return {
        "items": [serialize_difference(row) for row in rows],
        "nextCursor": next_cursor,
        "total": total,
    }


async def update_difference(
    db: AsyncSession,
    actor: MallActor,
    identity: int,
    data: DifferenceUpdate,
    *,
    key: str,
) -> MallReconciliationDifference:
    actor = await _require_admin(db, actor, "mall.reconciliations.write")
    initial = await db.get(MallReconciliationDifference, identity, populate_existing=True)
    if initial is None:
        raise NotFoundException(message="对账差异不存在")
    batch = await _batch_by_id(db, initial.batch_id, lock=True)
    difference = await db.scalar(
        select(MallReconciliationDifference)
        .where(
            MallReconciliationDifference.id == identity,
            MallReconciliationDifference.batch_id == batch.id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if difference is None:
        raise NotFoundException(message="对账差异不存在")
    reservation = await reserve_mall_command(
        db,
        actor=actor,
        action="updateMallDifference",
        key=key,
        payload={"differenceId": identity, **data.model_dump(mode="json")},
    )
    replay = await _command_replay(
        db,
        reservation,
        MallReconciliationDifference,
        entity_type="mall_reconciliation_difference",
    )
    if replay is not None:
        if replay.id != difference.id or replay.batch_id != batch.id:
            raise ConflictException(message="原差异操作与当前对象不一致")
        return replay
    if batch.status == "closed" or difference.status == "closed":
        raise ConflictException(message="已关闭的对账记录不能再次变更")
    if difference.version != data.expected_version:
        raise ConflictException(message="差异版本已变化，请重新读取")

    allowed = {
        "open": {"processing"},
        "processing": {"review"},
        "review": {"closed"},
    }
    if data.target_status not in allowed.get(difference.status, set()):
        raise ConflictException(message="差异状态只能按指派、复核、关闭顺序流转")

    if data.target_status == "processing":
        assignee_id = await _validate_assignee(db, data.assigned_to)
        if assignee_id is None:
            raise ValidationException(message="开始处理前必须指派负责人")
        difference.assigned_to = assignee_id

    incoming_ids = [int(value) for value in data.evidence_file_ids]
    if incoming_ids:
        await _verified_evidence_files(db, actor, incoming_ids, require_owner=True)
    merged_ids = list(dict.fromkeys([*(difference.evidence_file_ids or []), *incoming_ids]))
    if data.target_status in {"review", "closed"}:
        if not merged_ids:
            raise ConflictException(message="差异复核及关闭必须附已核验的处理证据")
        await _verified_evidence_files(
            db,
            actor,
            [int(value) for value in merged_ids],
            require_owner=False,
        )

    difference.status = data.target_status
    difference.resolution = _append_resolution(difference.resolution, data.reason)
    difference.evidence_file_ids = merged_ids
    difference.version += 1
    if data.target_status == "review":
        difference.reviewed_at = utc_now()
        batch.status = "review"
        batch.reviewed_by = actor.actor_id
        batch.reviewed_at = difference.reviewed_at
        batch.version += 1
    elif data.target_status == "closed":
        difference.resolved_at = utc_now()
        batch.version += 1
    else:
        batch.status = "processing"
        batch.version += 1
    await db.flush()
    await complete_mall_command(
        db,
        reservation,
        entity_type="mall_reconciliation_difference",
        entity_id=difference.id,
    )
    await record_mall_admin_audit(
        db,
        actor=actor,
        action="mall_reconciliation_difference_updated",
        entity_type="mall_reconciliation_difference",
        entity_id=str(difference.id),
        detail={
            "batchId": str(batch.id),
            "status": difference.status,
            "version": difference.version,
            "assignedTo": str(difference.assigned_to) if difference.assigned_to else None,
            "evidenceFileIds": [str(value) for value in merged_ids],
        },
    )
    return difference


async def close_reconciliation(
    db: AsyncSession,
    actor: MallActor,
    identity: int,
    data: ReasonAction,
    *,
    key: str,
) -> MallReconciliationBatch:
    actor = await _require_admin(db, actor, "mall.reconciliations.write")
    batch = await _batch_by_id(db, identity, lock=True)
    reservation = await reserve_mall_command(
        db,
        actor=actor,
        action="closeMallReconciliation",
        key=key,
        payload={"batchId": identity, **data.model_dump(mode="json")},
    )
    replay = await _command_replay(
        db, reservation, MallReconciliationBatch, entity_type="mall_reconciliation_batch"
    )
    if replay is not None:
        return replay
    if batch.status == "closed":
        raise ConflictException(message="对账批次已经关闭")
    if batch.version != data.expected_version:
        raise ConflictException(message="对账批次版本已变化，请重新读取")

    statement_file = await db.scalar(
        select(MallFile)
        .where(MallFile.id == batch.statement_file_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        statement_file is None
        or statement_file.status != "verified"
        or statement_file.purpose != "reconciliation_evidence"
        or statement_file.sha256 != batch.statement_sha256
    ):
        raise ConflictException(message="原始账单证据已失效或摘要发生变化，不能关闭")

    differences = (
        await db.scalars(
            select(MallReconciliationDifference)
            .where(MallReconciliationDifference.batch_id == batch.id)
            .order_by(MallReconciliationDifference.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).all()
    if any(row.status != "closed" for row in differences):
        raise ConflictException(message="仍有未决差异，不能关闭日对账")
    for row in differences:
        evidence_ids = [int(value) for value in (row.evidence_file_ids or [])]
        if not row.resolved_at or not row.reviewed_at or not evidence_ids:
            raise ConflictException(message="差异缺少复核、处理证据或关闭记录")
        await _verified_evidence_files(db, actor, evidence_ids, require_owner=False)

    totals_match = (
        batch.expected_paid_cent == batch.local_paid_cent
        and batch.expected_refund_cent == batch.local_refund_cent
    )
    if not totals_match and not differences:
        raise ConflictException(message="渠道金额与本地成功事实不一致，必须登记并处理差异")

    batch.status = "closed"
    batch.reviewed_by = actor.actor_id
    batch.reviewed_at = utc_now()
    batch.version += 1
    await db.flush()
    await complete_mall_command(
        db,
        reservation,
        entity_type="mall_reconciliation_batch",
        entity_id=batch.id,
    )
    await record_mall_admin_audit(
        db,
        actor=actor,
        action="mall_reconciliation_closed",
        entity_type="mall_reconciliation_batch",
        entity_id=str(batch.id),
        detail={
            "businessDate": batch.business_date.isoformat(),
            "version": batch.version,
            "reason": _clean_note(data.reason),
            "differenceCount": len(differences),
        },
    )
    return batch
