"""Invoice requests and verified invoice facts; tax issuance stays external."""

import re
from datetime import timezone
from uuid import uuid4

from sqlalchemy import select

from ..api.mall_deps import MallActor, require_mall_admin_permission
from ..core.exceptions import (
    ConflictException,
    ForbiddenException,
    NotFoundException,
    ValidationException,
)
from ..models.audit import AuditLog
from ..models.mall_base import utc_now
from ..models.mall_finance import MallInvoice, MallInvoiceRequest, MallPayment
from ..models.mall_operations import MallFile
from ..models.mall_trade import MallOrder
from ..schemas.mall_aftersale import ReasonAction
from ..schemas.mall_catalog import VersionAction
from ..schemas.mall_invoice import (
    InvoiceCreate,
    InvoiceFileReplace,
    InvoiceIssueRecord,
    InvoicePatch,
    RedInvoiceRecord,
    RedPendingUpdate,
)
from .mall_audit_service import record_mall_admin_audit
from .mall_command_service import complete_mall_command, reserve_mall_command
from .mall_consent_service import record_mall_notice_acknowledgement
from .mall_job_service import enqueue_mall_job
from .mall_notification_service import notify_mall_buyer
from .mall_order_service import owned_order
from .mall_settings_service import get_mall_settings

_PAID_ORDER_STATUSES = {"pending_shipment", "pending_receipt", "completed"}
_EDITABLE_REQUEST_STATUSES = {"submitted", "needs_info"}


def _utc_naive(value):
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


async def _admin(db, actor: MallActor) -> MallActor:
    if actor.actor_type != "admin":
        raise ForbiddenException(message="仅后台开票人员可处理发票")
    return await require_mall_admin_permission(
        {"sub": str(actor.actor_id), "user_type": "admin"},
        db,
        "mall.invoices.write",
        current=True,
    )


async def _locked_request_context(db, identity: int, *, actor: MallActor | None = None):
    initial_query = select(MallInvoiceRequest).where(MallInvoiceRequest.id == identity)
    if actor is not None and actor.actor_type == "user":
        initial_query = initial_query.where(MallInvoiceRequest.buyer_user_id == actor.actor_id)
    initial = await db.scalar(initial_query.execution_options(populate_existing=True))
    if initial is None:
        raise NotFoundException(message="开票申请不存在")
    order = await db.scalar(
        select(MallOrder)
        .where(MallOrder.id == initial.order_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if order is None:
        raise NotFoundException(message="商城订单不存在")
    statement = (
        select(MallInvoiceRequest)
        .where(MallInvoiceRequest.id == identity, MallInvoiceRequest.order_id == order.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if actor is not None and actor.actor_type == "user":
        statement = statement.where(MallInvoiceRequest.buyer_user_id == actor.actor_id)
    request = await db.scalar(statement)
    if request is None:
        raise NotFoundException(message="开票申请不存在")
    return order, request


async def _locked_invoice_context(db, identity: int):
    initial = await db.get(MallInvoice, identity, populate_existing=True)
    if initial is None:
        raise NotFoundException(message="发票记录不存在")
    order = await db.scalar(
        select(MallOrder)
        .where(MallOrder.id == initial.order_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if order is None:
        raise NotFoundException(message="商城订单不存在")
    invoice = await db.scalar(
        select(MallInvoice)
        .where(MallInvoice.id == identity, MallInvoice.order_id == order.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if invoice is None:
        raise NotFoundException(message="发票记录不存在")
    return order, invoice


async def _require_claimed_invoice_request(db, actor: MallActor, order, invoice):
    request = await db.get(MallInvoiceRequest, invoice.request_id, populate_existing=True)
    if (
        request is None
        or request.order_id != order.id
        or request.claimed_by != actor.actor_id
        or request.status not in {"delivered", "unknown"}
    ):
        raise ConflictException(message="请由当前领取该申请的财务人员继续办理")
    return request


async def _locked_payment(db, order):
    payment = await db.scalar(
        select(MallPayment)
        .where(MallPayment.id == order.active_payment_id, MallPayment.order_id == order.id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    if (
        order.status not in _PAID_ORDER_STATUSES
        or order.paid_amount_cent <= 0
        or payment is None
        or payment.status != "succeeded"
        or payment.amount_cent != order.paid_amount_cent
        or payment.confirmed_at is None
    ):
        raise ConflictException(message="订单没有可核实的成功收款，不能申请开票")
    return payment


def _user_audit(db, actor: MallActor, action: str, request: MallInvoiceRequest):
    db.add(
        AuditLog(
            user_id=actor.actor_id,
            action=action,
            entity_type="mall_invoice_request",
            entity_id=str(request.id),
            detail={"status": request.status, "version": request.version},
        )
    )


async def _record_invoice_notice(db, actor: MallActor, data, *, current_request=None):
    settings = await get_mall_settings(db)
    scope_keys = {"invoice_title", "tax_record"}
    supplied = getattr(data, "model_fields_set", set())
    tax_no = (
        data.tax_no
        if "tax_no" in supplied or current_request is None
        else current_request.tax_no
    )
    email = (
        data.email
        if "email" in supplied or current_request is None
        else current_request.email
    )
    if tax_no:
        scope_keys.add("tax_identifier")
    if email:
        scope_keys.add("delivery_email")
    return await record_mall_notice_acknowledgement(
        db,
        actor,
        purposes={"invoice"},
        version=data.consent_version,
        current_version=settings.policy_versions.get("policy", ""),
        confirmed=data.consent_confirmed,
        scope_keys=scope_keys,
    )


async def _replay_request(db, actor, intent, *, order_id=None):
    if intent.created:
        return None
    if intent.command.status != "completed" or not intent.command.entity_id:
        raise ConflictException(message="原开票请求仍在处理中，请查询原申请")
    row = await db.get(MallInvoiceRequest, intent.command.entity_id, populate_existing=True)
    if (
        row is None
        or (order_id is not None and row.order_id != order_id)
        or (actor.actor_type == "user" and row.buyer_user_id != actor.actor_id)
    ):
        raise ConflictException(message="原开票请求关联不一致")
    return row


def _same_buyer_request(row: MallInvoiceRequest, actor: MallActor, data: InvoiceCreate) -> bool:
    return (
        row.buyer_user_id == actor.actor_id
        and row.buyer_type == data.buyer_type
        and row.title == data.title
        and row.tax_no == (data.tax_no if data.buyer_type == "company" else None)
        and row.email == data.email
        and row.invoice_type == data.invoice_type
    )


async def create_invoice_request(db, actor: MallActor, data: InvoiceCreate, *, key: str):
    """Create one request from a verified, paid order snapshot."""
    if actor.actor_type != "user":
        raise ForbiddenException(message="仅小程序买家可提交开票申请")
    if data.buyer_type == "company" and not data.tax_no:
        raise ValidationException(message="企业抬头必须填写纳税人识别号")
    order = await owned_order(db, actor, int(data.order_id), lock=True)
    intent = await reserve_mall_command(
        db,
        actor=actor,
        action="createMallInvoiceRequest",
        key=key,
        payload=data.model_dump(mode="json"),
    )
    replay = await _replay_request(db, actor, intent, order_id=order.id)
    if replay is not None:
        return replay

    active = await db.scalar(
        select(MallInvoiceRequest)
        .where(MallInvoiceRequest.order_id == order.id, MallInvoiceRequest.active_slot == 1)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if active is not None:
        if not _same_buyer_request(active, actor, data):
            raise ConflictException(message="订单已有开票申请，请在原申请中更正资料")
        await complete_mall_command(
            db, intent, entity_type="mall_invoice_request", entity_id=active.id
        )
        await db.flush()
        return active

    if order.version != data.expected_order_version:
        raise ConflictException(message="订单版本已变化，请重新读取后申请开票")
    await _locked_payment(db, order)

    goods_cent = order.goods_amount_cent - order.refunded_goods_cent
    freight_cent = order.freight_amount_cent - order.refunded_freight_cent
    if goods_cent < 0 or freight_cent < 0 or goods_cent + freight_cent <= 0:
        raise ConflictException(message="订单可开票金额异常，请联系财务核实")
    if goods_cent + freight_cent > order.paid_amount_cent:
        raise ConflictException(message="订单开票金额超过成功收款金额")

    consent = await _record_invoice_notice(db, actor, data)

    request = MallInvoiceRequest(
        request_no="I" + uuid4().hex[:31],
        order_id=order.id,
        consent_record_id=consent.id,
        buyer_user_id=actor.actor_id,
        buyer_type=data.buyer_type,
        title=data.title,
        tax_no=data.tax_no if data.buyer_type == "company" else None,
        email=data.email,
        invoice_type=data.invoice_type,
        requested_goods_cent=goods_cent,
        requested_freight_cent=freight_cent,
        source_order_version=order.version + 1,
        status="submitted",
        active_slot=1,
    )
    db.add(request)
    await db.flush()
    order.current_invoice_request_id = request.id
    order.version += 1
    _user_audit(db, actor, "mall_invoice_request_created", request)
    await complete_mall_command(
        db, intent, entity_type="mall_invoice_request", entity_id=request.id
    )
    await db.flush()
    return request


async def _invoice_action(db, actor, action, key, payload, identity):
    intent = await reserve_mall_command(
        db, actor=actor, action=action, key=key, payload=payload
    )
    if intent.created:
        return intent, None
    if intent.command.status != "completed" or not intent.command.entity_id:
        raise ConflictException(message="原开票操作仍在处理中，请查询原申请")
    if intent.command.entity_id != identity:
        raise ConflictException(message="原开票操作关联不一致")
    request = await db.scalar(
        select(MallInvoiceRequest)
        .where(MallInvoiceRequest.id == identity)
        .execution_options(populate_existing=True)
    )
    if request is None:
        raise ConflictException(message="原开票申请不存在")
    return intent, request


async def _invoice_entity_action(db, actor, action, key, payload, identity, *, kind=None):
    intent = await reserve_mall_command(
        db, actor=actor, action=action, key=key, payload=payload
    )
    if intent.created:
        return intent, None
    if intent.command.status != "completed" or not intent.command.entity_id:
        raise ConflictException(message="原票据操作仍在处理中，请查询原发票")
    if intent.command.entity_id != identity and action != "recordMallRedInvoice":
        raise ConflictException(message="原票据操作关联不一致")
    row = await db.get(MallInvoice, intent.command.entity_id, populate_existing=True)
    if (
        row is None
        or (kind is not None and row.kind != kind)
        or (action == "recordMallRedInvoice" and row.original_invoice_id != identity)
    ):
        raise ConflictException(message="原票据操作关联不一致")
    return intent, row


async def update_invoice_request(
    db, actor: MallActor, identity: int, data: InvoicePatch, *, key: str
):
    if actor.actor_type != "user":
        raise ForbiddenException(message="仅申请人可更正开票资料")
    order, request = await _locked_request_context(db, identity, actor=actor)
    payload = {"requestId": identity, **data.model_dump(mode="json", exclude_unset=True)}
    intent, replay = await _invoice_action(
        db, actor, "updateMyMallInvoiceRequest", key, payload, identity
    )
    if replay is not None:
        if replay.buyer_user_id != actor.actor_id:
            raise ConflictException(message="原开票申请关联不一致")
        return replay
    if request.version != data.expected_version:
        raise ConflictException(message="开票申请版本已变化，请重新读取")
    if request.status not in _EDITABLE_REQUEST_STATUSES or (
        request.status == "submitted" and request.claimed_by is not None
    ):
        raise ConflictException(message="当前开票阶段不能更正资料")

    consent = await _record_invoice_notice(db, actor, data, current_request=request)

    supplied = data.model_fields_set
    if "title" in supplied:
        request.title = data.title
    if "tax_no" in supplied:
        if request.buyer_type == "company" and not data.tax_no:
            raise ConflictException(message="企业抬头必须保留纳税人识别号")
        if request.buyer_type == "personal" and data.tax_no:
            raise ConflictException(message="个人抬头不能填写纳税人识别号")
        request.tax_no = data.tax_no
    if "email" in supplied:
        request.email = data.email
    request.consent_record_id = consent.id
    request.status = "submitted"
    request.version += 1
    _user_audit(db, actor, "mall_invoice_request_updated", request)
    await complete_mall_command(
        db, intent, entity_type="mall_invoice_request", entity_id=request.id
    )
    await db.flush()
    return request


async def withdraw_invoice_request(
    db, actor: MallActor, identity: int, data: ReasonAction, *, key: str
):
    if actor.actor_type != "user":
        raise ForbiddenException(message="仅申请人可撤回开票申请")
    order, request = await _locked_request_context(db, identity, actor=actor)
    payload = {"requestId": identity, **data.model_dump(mode="json")}
    intent, replay = await _invoice_action(
        db, actor, "withdrawMallInvoiceRequest", key, payload, identity
    )
    if replay is not None:
        if replay.buyer_user_id != actor.actor_id:
            raise ConflictException(message="原开票申请关联不一致")
        return replay
    if request.version != data.expected_version or request.status not in _EDITABLE_REQUEST_STATUSES:
        raise ConflictException(message="开票已进入财务处理阶段，不能撤回")
    request.status = "withdrawn"
    request.active_slot = None
    request.version += 1
    if order.current_invoice_request_id == request.id:
        order.current_invoice_request_id = None
        order.version += 1
    _user_audit(db, actor, "mall_invoice_request_withdrawn", request)
    await complete_mall_command(
        db, intent, entity_type="mall_invoice_request", entity_id=request.id
    )
    await db.flush()
    return request


async def claim_invoice_request(
    db, actor: MallActor, identity: int, data: VersionAction, *, key: str
):
    actor = await _admin(db, actor)
    order, request = await _locked_request_context(db, identity)
    payload = {"requestId": identity, **data.model_dump(mode="json")}
    intent, replay = await _invoice_action(db, actor, "claimMallInvoice", key, payload, identity)
    if replay is not None:
        return replay
    if request.version != data.expected_version:
        raise ConflictException(message="开票申请版本已变化，请重新读取")
    if request.status == "issuing" and request.claimed_by == actor.actor_id:
        await complete_mall_command(
            db, intent, entity_type="mall_invoice_request", entity_id=request.id
        )
        return request
    if request.status != "submitted" or request.claimed_by not in {None, actor.actor_id}:
        raise ConflictException(message="当前申请已由其他财务处理或暂不可领取")
    request.claimed_by = actor.actor_id
    request.claimed_at = utc_now()
    request.status = "issuing"
    request.version += 1
    await record_mall_admin_audit(
        db,
        actor=actor,
        action="mall_invoice_request_claimed",
        entity_type="mall_invoice_request",
        entity_id=str(request.id),
        detail={"orderId": str(order.id), "status": request.status, "version": request.version},
    )
    await complete_mall_command(
        db, intent, entity_type="mall_invoice_request", entity_id=request.id
    )
    await db.flush()
    return request


async def need_invoice_info(
    db, actor: MallActor, identity: int, data: ReasonAction, *, key: str
):
    actor = await _admin(db, actor)
    order, request = await _locked_request_context(db, identity)
    payload = {"requestId": identity, **data.model_dump(mode="json")}
    intent, replay = await _invoice_action(db, actor, "needMallInvoiceInfo", key, payload, identity)
    if replay is not None:
        return replay
    if request.version != data.expected_version or request.status != "issuing":
        raise ConflictException(message="当前申请阶段或版本已变化")
    if request.claimed_by != actor.actor_id:
        raise ConflictException(message="请先领取该开票申请")
    request.status = "needs_info"
    request.version += 1
    await record_mall_admin_audit(
        db,
        actor=actor,
        action="mall_invoice_needs_info",
        entity_type="mall_invoice_request",
        entity_id=str(request.id),
        detail={
            "orderId": str(order.id),
            "reason": data.reason,
            "status": request.status,
            "version": request.version,
        },
    )
    await complete_mall_command(
        db, intent, entity_type="mall_invoice_request", entity_id=request.id
    )
    await db.flush()
    return request


async def _verified_issue_file(db, actor, request, file_id):
    file = await db.scalar(
        select(MallFile)
        .where(MallFile.id == file_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if file is None:
        raise ConflictException(message="已核验的发票PDF不存在")
    if file.owner_actor_type != "admin" or file.owner_actor_id != actor.actor_id:
        raise ForbiddenException(message="发票PDF必须由当前财务账号上传并核验")
    if (
        file.purpose != "invoice_pdf"
        or file.order_id != request.order_id
        or file.status != "verified"
        or file.invoice_id is not None
        or file.expires_at > utc_now()
        or file.mime != "application/pdf"
        or not 0 < file.size <= 10 * 1024 * 1024
        or re.fullmatch(r"[a-f0-9]{64}", file.sha256 or "") is None
    ):
        raise ConflictException(message="发票PDF未通过用途、归属或内容校验")
    return file


async def _recorded_invoice(db, data, request):
    existing = await db.scalar(
        select(MallInvoice)
        .where(
            MallInvoice.seller_identity == data.seller_identity,
            MallInvoice.invoice_no == data.invoice_no,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if existing is None:
        return None
    if (
        existing.kind == "blue"
        and existing.request_id == request.id
        and existing.order_id == request.order_id
        and existing.total_cent == data.total_cent
        and existing.file_id == int(data.file_id)
        and existing.replacement_for_id
        == (int(data.replacement_for_id) if data.replacement_for_id is not None else None)
        and existing.issued_at == _utc_naive(data.issued_at)
    ):
        return existing
    raise ConflictException(message="该销售主体下的票号已关联其他开票事实")


async def record_invoice_issue(
    db, actor: MallActor, identity: int, data: InvoiceIssueRecord, *, key: str
):
    """Persist the actual blue invoice even when local order/request state raced."""
    actor = await _admin(db, actor)
    order, request = await _locked_request_context(db, identity)
    payload = {"requestId": identity, **data.model_dump(mode="json")}
    intent = await reserve_mall_command(
        db, actor=actor, action="recordMallInvoice", key=key, payload=payload
    )
    if not intent.created:
        if intent.command.status != "completed" or not intent.command.entity_id:
            raise ConflictException(message="原开票回传仍在处理中，请查询票据")
        replay = await db.get(MallInvoice, intent.command.entity_id, populate_existing=True)
        if replay is None or replay.request_id != request.id or replay.kind != "blue":
            raise ConflictException(message="原开票回传关联不一致")
        return replay

    existing = await _recorded_invoice(db, data, request)
    if existing is not None:
        await complete_mall_command(
            db, intent, entity_type="mall_invoice", entity_id=existing.id
        )
        await db.flush()
        return existing

    replacement_for = None
    if data.replacement_for_id is not None:
        replacement_for = await db.scalar(
            select(MallInvoice)
            .where(
                MallInvoice.id == int(data.replacement_for_id),
                MallInvoice.order_id == order.id,
                MallInvoice.request_id == request.id,
                MallInvoice.kind == "blue",
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if replacement_for is None or replacement_for.status != "fully_red":
            raise ConflictException(message="旧蓝票尚未完全释放有效覆盖，不能重开")
        reds = (
            await db.scalars(
                select(MallInvoice)
                .where(
                    MallInvoice.original_invoice_id == replacement_for.id,
                    MallInvoice.kind == "red",
                    MallInvoice.status == "valid",
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
        if sum(row.total_cent for row in reds) != replacement_for.total_cent:
            raise ConflictException(message="旧蓝票红冲覆盖不完整，不能重开")
        if data.seller_identity != replacement_for.seller_identity:
            raise ConflictException(message="替代蓝票销售主体必须与原蓝票一致")
        if (
            request.version != data.expected_version
            or request.claimed_by != actor.actor_id
            or request.status not in {"delivered", "unknown"}
        ):
            raise ConflictException(message="重开发票申请版本或财务归属已变化")
        already_replaced = await db.scalar(
            select(MallInvoice.id).where(
                MallInvoice.replacement_for_id == replacement_for.id,
                MallInvoice.kind == "blue",
            )
        )
        if already_replaced is not None:
            raise ConflictException(message="旧蓝票已关联替代蓝票")
        effective_paid_cent = (
            order.paid_amount_cent - order.refunded_goods_cent - order.refunded_freight_cent
        )
        if effective_paid_cent <= 0 or data.total_cent != effective_paid_cent:
            raise ConflictException(message="重开金额必须等于已扣成功退款后的有效交易金额")
        state_matches = True
    else:
        # Only an unchanged, claimed request can be marked delivered. The inputs
        # to this operation represent an external tax fact, so a real issue is
        # still stored when an order/refund/correction won the local race.
        state_matches = (
            request.version == data.expected_version
            and request.status == "issuing"
            and request.claimed_by == actor.actor_id
            and request.source_order_version == order.version
            and order.current_invoice_request_id == request.id
        )
    amount_snapshot = request.requested_goods_cent + request.requested_freight_cent
    if data.total_cent != amount_snapshot and state_matches and replacement_for is None:
        raise ConflictException(message="票面金额与开票申请金额不一致")

    file = await _verified_issue_file(db, actor, request, int(data.file_id))
    issue_status = (
        "red_pending"
        if not state_matches and (order.refunded_goods_cent or order.refunded_freight_cent)
        else "valid"
    )
    issue = MallInvoice(
        request_id=request.id,
        order_id=order.id,
        kind="blue",
        seller_identity=data.seller_identity,
        invoice_no=data.invoice_no,
        issued_at=_utc_naive(data.issued_at),
        total_cent=data.total_cent,
        seller_snapshot={},
        file_id=file.id,
        status=issue_status,
        replacement_for_id=replacement_for.id if replacement_for is not None else None,
        issued_by=None,
        recorded_by=actor.actor_id,
    )
    db.add(issue)
    await db.flush()
    file.invoice_id = issue.id
    file.status = "bound"
    file.version += 1
    request.status = "delivered" if state_matches else "unknown"
    request.version += 1

    if not state_matches:
        review = await enqueue_mall_job(
            db,
            kind="mall_invoice_issue_review",
            entity_type="mall_invoice",
            entity_id=issue.id,
            entity_version=issue.version,
            dedupe_key=f"mall-invoice-issue-review:{issue.id}",
        )
        review.status = "manual"
        review.last_error_code = "invoice_state_changed_after_issue"

    await record_mall_admin_audit(
        db,
        actor=actor,
        action=(
            "mall_invoice_issue_recorded"
            if state_matches
            else "mall_invoice_issue_needs_review"
        ),
        entity_type="mall_invoice",
        entity_id=str(issue.id),
        detail={
            "requestId": str(request.id),
            "orderId": str(order.id),
            "totalCent": data.total_cent,
            "status": request.status,
            "reason": data.reason,
        },
    )
    await complete_mall_command(db, intent, entity_type="mall_invoice", entity_id=issue.id)
    await db.flush()
    if state_matches:
        await notify_mall_buyer(
            db,
            buyer_user_id=request.buyer_user_id,
            event_key=f"mall:invoice:{issue.id}:issued",
            title="商城电子发票已开具",
            summary=f"订单号 {order.order_no} 的电子发票已开具，可在发票详情中查看。",
            target=f"/pages/mall-invoice-detail/index?id={request.id}",
        )
    return issue


async def _recorded_red_invoice(db, data: RedInvoiceRecord, blue: MallInvoice):
    existing = await db.scalar(
        select(MallInvoice)
        .where(
            MallInvoice.seller_identity == blue.seller_identity,
            MallInvoice.invoice_no == data.invoice_no,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if existing is None:
        return None
    if (
        existing.kind == "red"
        and existing.original_invoice_id == blue.id
        and existing.order_id == blue.order_id
        and existing.total_cent == data.total_cent
        and existing.file_id == int(data.file_id)
        and existing.issued_at == _utc_naive(data.issued_at)
    ):
        return existing
    raise ConflictException(message="该销售主体下的票号已关联其他开票事实")


async def set_red_pending(
    db, actor: MallActor, identity: int, data: RedPendingUpdate, *, key: str
):
    """Record that finance must handle red issuance; this is not a tax fact."""
    actor = await _admin(db, actor)
    order, blue = await _locked_invoice_context(db, identity)
    await _require_claimed_invoice_request(db, actor, order, blue)
    payload = {"invoiceId": identity, **data.model_dump(mode="json")}
    intent, replay = await _invoice_entity_action(
        db,
        actor,
        "markMallRedPending",
        key,
        payload,
        identity,
        kind="blue",
    )
    if replay is not None:
        return replay
    if blue.version != data.expected_version:
        raise ConflictException(message="蓝票版本已变化，请重新读取")
    if blue.status not in {"valid", "red_pending", "awaiting_counterparty", "partially_red"}:
        raise ConflictException(message="当前蓝票已经全部红冲或不能继续办理")
    red_rows = (
        await db.scalars(
            select(MallInvoice)
            .where(
                MallInvoice.original_invoice_id == blue.id,
                MallInvoice.kind == "red",
                MallInvoice.status == "valid",
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).all()
    red_total = sum(row.total_cent for row in red_rows)
    if red_total >= blue.total_cent:
        raise ConflictException(message="蓝票已无可红冲的有效覆盖")
    blue.status = data.target_status
    blue.version += 1
    await record_mall_admin_audit(
        db,
        actor=actor,
        action="mall_invoice_red_pending",
        entity_type="mall_invoice",
        entity_id=str(blue.id),
        detail={
            "orderId": str(order.id),
            "targetStatus": data.target_status,
            "reason": data.reason,
            "version": blue.version,
        },
    )
    await complete_mall_command(db, intent, entity_type="mall_invoice", entity_id=blue.id)
    await db.flush()
    return blue


async def record_red_invoice(
    db, actor: MallActor, identity: int, data: RedInvoiceRecord, *, key: str
):
    """Save a real red invoice against the unreleased remainder of a blue invoice."""
    actor = await _admin(db, actor)
    order, blue = await _locked_invoice_context(db, identity)
    request = await _require_claimed_invoice_request(db, actor, order, blue)
    payload = {"invoiceId": identity, **data.model_dump(mode="json")}
    intent, replay = await _invoice_entity_action(
        db,
        actor,
        "recordMallRedInvoice",
        key,
        payload,
        identity,
        kind="red",
    )
    if replay is not None:
        return replay
    existing = await _recorded_red_invoice(db, data, blue)
    if existing is not None:
        await complete_mall_command(db, intent, entity_type="mall_invoice", entity_id=existing.id)
        await db.flush()
        return existing
    if blue.kind != "blue" or blue.version != data.expected_version:
        raise ConflictException(message="蓝票版本或票据类型已变化")
    if blue.status not in {"red_pending", "awaiting_counterparty"}:
        raise ConflictException(message="请先登记红冲待办或对方确认状态")

    file = await _verified_issue_file(db, actor, request, int(data.file_id))
    red_rows = (
        await db.scalars(
            select(MallInvoice)
            .where(
                MallInvoice.original_invoice_id == blue.id,
                MallInvoice.kind == "red",
                MallInvoice.status == "valid",
            )
            .order_by(MallInvoice.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).all()
    remaining_cent = blue.total_cent - sum(row.total_cent for row in red_rows)
    if remaining_cent <= 0 or data.total_cent > remaining_cent:
        raise ConflictException(message="红票金额超过原蓝票尚未释放的有效覆盖")

    red = MallInvoice(
        request_id=blue.request_id,
        order_id=order.id,
        kind="red",
        seller_identity=blue.seller_identity,
        invoice_no=data.invoice_no,
        issued_at=_utc_naive(data.issued_at),
        total_cent=data.total_cent,
        seller_snapshot=dict(blue.seller_snapshot or {}),
        file_id=file.id,
        status="valid",
        original_invoice_id=blue.id,
        replacement_for_id=None,
        issued_by=None,
        recorded_by=actor.actor_id,
    )
    db.add(red)
    await db.flush()
    file.invoice_id = red.id
    file.status = "bound"
    file.version += 1
    total_red_cent = sum(row.total_cent for row in red_rows) + red.total_cent
    blue.status = "fully_red" if total_red_cent == blue.total_cent else "partially_red"
    blue.version += 1
    await record_mall_admin_audit(
        db,
        actor=actor,
        action="mall_red_invoice_recorded",
        entity_type="mall_invoice",
        entity_id=str(red.id),
        detail={
            "requestId": str(request.id),
            "orderId": str(order.id),
            "originalInvoiceId": str(blue.id),
            "totalCent": red.total_cent,
            "originalRemainingCent": remaining_cent - red.total_cent,
            "reason": data.reason,
        },
    )
    await complete_mall_command(db, intent, entity_type="mall_invoice", entity_id=red.id)
    await db.flush()
    return red


async def replace_invoice_file(
    db, actor: MallActor, identity: int, data: InvoiceFileReplace, *, key: str
):
    """Replace a lost/damaged PDF while preserving the same tax invoice fact."""
    actor = await _admin(db, actor)
    order, invoice = await _locked_invoice_context(db, identity)
    request = await _require_claimed_invoice_request(db, actor, order, invoice)
    payload = {"invoiceId": identity, **data.model_dump(mode="json")}
    intent, replay = await _invoice_entity_action(
        db,
        actor,
        "replaceMallInvoiceFile",
        key,
        payload,
        identity,
        kind=invoice.kind,
    )
    if replay is not None:
        return replay
    if invoice.version != data.expected_version:
        raise ConflictException(message="发票版本已变化，请重新读取")
    if invoice.file_id == int(data.file_id):
        raise ConflictException(message="请上传重新核验的票据文件")
    file = await _verified_issue_file(db, actor, request, int(data.file_id))
    invoice.file_id = file.id
    invoice.version += 1
    file.invoice_id = invoice.id
    file.status = "bound"
    file.version += 1
    await record_mall_admin_audit(
        db,
        actor=actor,
        action="mall_invoice_file_replaced",
        entity_type="mall_invoice",
        entity_id=str(invoice.id),
        detail={
            "orderId": str(order.id),
            "kind": invoice.kind,
            "reason": data.reason,
            "version": invoice.version,
        },
    )
    await complete_mall_command(db, intent, entity_type="mall_invoice", entity_id=invoice.id)
    await db.flush()
    return invoice


async def request_invoice_correction(
    db, actor: MallActor, identity: int, data: ReasonAction, *, key: str
):
    """Queue a buyer correction request without editing a tax-issued invoice."""
    if actor.actor_type != "user":
        raise ForbiddenException(message="仅买家可提交发票更正诉求")
    initial = await db.scalar(
        select(MallInvoice)
        .join(MallOrder, MallOrder.id == MallInvoice.order_id)
        .where(MallInvoice.id == identity, MallOrder.buyer_user_id == actor.actor_id)
        .execution_options(populate_existing=True)
    )
    if initial is None:
        raise NotFoundException(message="发票记录不存在")
    order, invoice = await _locked_invoice_context(db, identity)
    if order.buyer_user_id != actor.actor_id:
        raise NotFoundException(message="发票记录不存在")
    payload = {"invoiceId": identity, **data.model_dump(mode="json")}
    intent = await reserve_mall_command(
        db,
        actor=actor,
        action="requestMallInvoiceCorrection",
        key=key,
        payload=payload,
    )
    if not intent.created:
        if intent.command.status != "completed" or intent.command.entity_id != invoice.id:
            raise ConflictException(message="原更正诉求仍在处理中或关联不一致")
        return intent.command
    if invoice.kind != "blue" or invoice.status == "fully_red":
        raise ConflictException(message="当前票据不能提交抬头更正诉求")
    if invoice.version != data.expected_version:
        raise ConflictException(message="发票版本已变化，请重新读取")
    request = await db.get(MallInvoiceRequest, invoice.request_id, populate_existing=True)
    if request is None or request.order_id != order.id:
        raise ConflictException(message="发票关联的开票申请不存在")

    job = await enqueue_mall_job(
        db,
        kind="mall_invoice_correction_review",
        entity_type="mall_invoice",
        entity_id=invoice.id,
        entity_version=invoice.version,
        dedupe_key=f"mall-invoice-correction:{invoice.id}",
    )
    job.status = "manual"
    job.last_error_code = "buyer_invoice_correction_requested"
    safe_reason = data.reason
    for private_value in (request.tax_no, request.email):
        if private_value:
            safe_reason = safe_reason.replace(private_value, "[已隐藏]")
    db.add(
        AuditLog(
            user_id=actor.actor_id,
            action="mall_invoice_correction_requested",
            entity_type="mall_invoice",
            entity_id=str(invoice.id),
            detail={
                "orderId": str(order.id),
                "reason": safe_reason,
                "invoiceVersion": invoice.version,
            },
        )
    )
    await complete_mall_command(db, intent, entity_type="mall_invoice", entity_id=invoice.id)
    await db.flush()
    return intent.command

