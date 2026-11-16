"""Evidence-based attribution for previously unassigned mall consumption."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.mall_deps import MallActor
from ..core.exceptions import (
    ConflictException,
    ForbiddenException,
    NotFoundException,
    ValidationException,
)
from ..models.binding import BindingStatus, Customer
from ..models.distributor import Distributor, DistributorStatus
from ..models.mall_base import utc_now
from ..models.mall_consumption import MallConsumption
from ..models.mall_operations import MallFile
from ..models.organization import Organization, OrgStatus
from ..models.performance_evidence import PerformanceEvidence
from ..models.performance_rule import RuleType
from ..models.performance_settlement import PerformanceSettlement, SettlementStatus
from ..models.user import ActivationStatus, User
from .mall_audit_service import record_mall_admin_audit
from .mall_command_service import complete_mall_command, reserve_mall_command
from .mall_job_service import enqueue_mall_job
from .performance_period_service import lock_period


@dataclass(frozen=True)
class MallAttributionResult:
    source: MallConsumption
    handling: str


async def _frozen_anchors_for_distributor(
    db: AsyncSession, *, period: str, distributor_id: int
) -> list[PerformanceEvidence]:
    rows = (
        await db.scalars(
            select(PerformanceEvidence)
            .where(PerformanceEvidence.period == period)
            .order_by(PerformanceEvidence.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).all()
    return [
        row
        for row in rows
        if (row.rule_type == RuleType.INTRA_ORG.value and row.distributor_id == distributor_id)
        or (
            row.rule_type == RuleType.ORG_MANAGEMENT.value
            and distributor_id in (row.frozen_members or [])
        )
    ]


async def _load_customer(
    db: AsyncSession, *, source: MallConsumption, customer_id: int | None
) -> Customer | None:
    if customer_id is not None:
        customer = await db.scalar(
            select(Customer)
            .where(Customer.id == customer_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if customer is None:
            raise NotFoundException(message="客户不存在")
        if customer.user_id != source.buyer_user_id:
            raise ValidationException(message="客户与商城买家不匹配")
        return customer
    return await db.scalar(
        select(Customer)
        .where(Customer.user_id == source.buyer_user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def _load_verified_evidence_files(
    db: AsyncSession,
    *,
    actor: MallActor,
    source: MallConsumption,
    file_ids: list[int],
) -> list[MallFile]:
    if not file_ids:
        return []
    if len(set(file_ids)) != len(file_ids):
        raise ValidationException(message="凭证文件不可重复")
    files = (
        await db.scalars(
            select(MallFile)
            .where(MallFile.id.in_(sorted(file_ids)))
            .order_by(MallFile.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).all()
    if len(files) != len(file_ids):
        raise NotFoundException(message="归属核实凭证不存在")
    now = utc_now()
    for file in files:
        if file.owner_actor_type != "admin" or file.owner_actor_id != actor.actor_id:
            raise ForbiddenException(message="只能使用本人上传的归属核实凭证")
        if file.purpose != "attribution_evidence":
            raise ValidationException(message="文件用途不是商城归属核实凭证")
        if file.status not in {"verified", "bound"} or file.expires_at > now:
            raise ValidationException(message="归属核实凭证尚未核验")
        if file.order_id not in (None, source.order_id):
            raise ConflictException(message="归属核实凭证已关联其他订单")
    return files


async def attribute_mall_consumption(
    db: AsyncSession,
    *,
    actor: MallActor,
    consumption_id: int,
    expected_version: int,
    distributor_id: int,
    customer_id: int | None,
    evidence_file_ids: list[int],
    reason: str,
    idempotency_key: str,
) -> MallAttributionResult:
    """Assign an unassigned source without changing its original payment period."""
    if actor.actor_type != "admin" or "mall.attribution.write" not in actor.permissions:
        raise ForbiddenException(message="缺少商城消费归属核实权限")
    reason = (reason or "").strip()
    if not reason:
        raise ValidationException(message="归属核实原因不能为空")
    if len(reason) > 500:
        raise ValidationException(message="归属核实原因不能超过500字")
    if expected_version < 1 or distributor_id < 1 or consumption_id < 1:
        raise ValidationException(message="归属核实参数无效")

    payload = {
        "consumptionId": consumption_id,
        "expectedVersion": expected_version,
        "distributorId": distributor_id,
        "customerId": customer_id,
        "evidenceFileIds": sorted(evidence_file_ids),
        "reason": reason,
    }
    intent = await reserve_mall_command(
        db,
        actor=actor,
        action="attributeMallConsumption",
        key=idempotency_key,
        payload=payload,
    )
    if not intent.created:
        if intent.command.status != "completed":
            raise ConflictException(message="归属核实仍在处理中，请稍后查询")
        source = await db.get(MallConsumption, consumption_id, populate_existing=True)
        if source is None:
            raise NotFoundException(message="商城消费来源不存在")
        return MallAttributionResult(
            source=source,
            handling=intent.command.result_code or "completed",
        )

    initial = await db.get(MallConsumption, consumption_id, populate_existing=True)
    if initial is None:
        raise NotFoundException(message="商城消费来源不存在")
    period = initial.business_period
    period_row = await lock_period(db, period)
    source = await db.scalar(
        select(MallConsumption)
        .where(MallConsumption.id == consumption_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if source is None:
        raise NotFoundException(message="商城消费来源不存在")
    if source.business_period != period:
        raise ConflictException(message="商城消费原支付月份已变化，请刷新后重试")
    if source.status != "unassigned" or source.attributed_distributor_id is not None:
        raise ConflictException(message="仅未归属商城消费可以核实归属")
    if source.source_version != expected_version:
        raise ConflictException(message="商城消费来源已变化，请刷新后重试")

    distributor = await db.scalar(
        select(Distributor)
        .where(Distributor.id == distributor_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if distributor is None:
        raise NotFoundException(message="归属推广人员不存在")
    org = await db.get(Organization, distributor.org_id, populate_existing=True)
    user = await db.get(User, distributor.user_id, populate_existing=True)
    if (
        distributor.status != DistributorStatus.ACTIVE
        or org is None
        or org.status != OrgStatus.ACTIVE
        or user is None
        or user.activation_status != ActivationStatus.ACTIVE
    ):
        raise ValidationException(message="只能归属到有效的组织和推广人员")

    customer = await _load_customer(db, source=source, customer_id=customer_id)
    verified_binding = bool(
        customer
        and customer.binding_status == BindingStatus.BOUND
        and customer.distributor_id == distributor.id
        and customer.bound_at
        and customer.bound_at <= source.paid_at
    )
    files = await _load_verified_evidence_files(
        db,
        actor=actor,
        source=source,
        file_ids=evidence_file_ids,
    )
    if not verified_binding and not files:
        raise ValidationException(message="缺少支付时有效的授权绑定记录或已核验归属凭证")
    if (
        customer
        and customer.binding_status == BindingStatus.BOUND
        and customer.distributor_id not in (None, distributor.id)
        and customer.bound_at
        and customer.bound_at <= source.paid_at
    ):
        raise ConflictException(message="支付时客户已归属其他推广人员，需人工复核")

    settlement_status = await db.scalar(
        select(PerformanceSettlement.status)
        .where(PerformanceSettlement.period == period)
        .with_for_update()
    )
    frozen = period_row.status == "frozen" or settlement_status == SettlementStatus.REVIEWED
    if frozen:
        period_row.status = "frozen"
    elif period_row.status == "open":
        period_row.revision += 1
    else:
        raise ConflictException(message="绩效月份状态不允许归属核实")

    now = utc_now()
    source.customer_id = customer.id if customer else None
    source.attributed_distributor_id = distributor.id
    # trade_org_id is the payment-time organization snapshot; keep it immutable.
    source.status = "assigned"
    source.source_version += 1
    source.version += 1
    source.attribution_evidence = {
        "basis": "payment_time_binding" if verified_binding else "admin_verified_files",
        "verifiedAt": now.isoformat() + "Z",
        "verifiedBy": str(actor.actor_id),
        "reason": reason,
        "customerId": str(customer.id) if customer else None,
        "customerVersion": customer.version if verified_binding and customer else None,
        "boundAt": customer.bound_at.isoformat() + "Z" if verified_binding and customer else None,
        "evidenceFileIds": [str(file.id) for file in files],
    }
    for file in files:
        file.order_id = source.order_id
        file.status = "bound"
        file.version += 1

    handling = "ready_for_settlement"
    if frozen:
        anchors = await _frozen_anchors_for_distributor(
            db, period=period, distributor_id=distributor.id
        )
        if not anchors:
            job = await enqueue_mall_job(
                db,
                kind="mall_performance_attribution_candidate",
                entity_type="mall_consumption",
                entity_id=source.id,
                entity_version=source.source_version,
                dedupe_key=f"mall-performance-attribution:{source.id}:{source.source_version}",
            )
            job.status = "manual"
            job.last_error_code = "performance_evidence_missing"
            handling = "manual_required"
        else:
            from .performance_adjustment_service import propose_adjustment

            adjustments = []
            for anchor in anchors:
                adjustments.append(
                    await propose_adjustment(
                        db,
                        anchor.id,
                        trigger_source_type="mall",
                        trigger_source_id=source.id,
                        trigger_version=source.source_version,
                    )
                )
            handling = (
                "adjustment_pending"
                if all(row.status == "proposed" for row in adjustments)
                else "manual_required"
            )
    elif settlement_status == SettlementStatus.PENDING:
        from .commission_service import compute_commission
        from .performance_evidence_service import capture_period_evidence

        await compute_commission(db, period)
        await capture_period_evidence(db, period, period_row=period_row)
        handling = "recomputed"

    await record_mall_admin_audit(
        db,
        actor=actor,
        action="mall_consumption_attributed",
        entity_type="mall_consumption",
        entity_id=str(source.id),
        detail={
            "businessPeriod": period,
            "sourceVersion": source.source_version,
            "distributorId": str(distributor.id),
            "customerId": str(customer.id) if customer else None,
            "evidenceFileIds": [str(file.id) for file in files],
            "basis": source.attribution_evidence["basis"],
            "reason": reason,
            "performanceHandling": handling,
        },
    )
    await complete_mall_command(
        db, intent, entity_type="mall_consumption", entity_id=source.id, result_code=handling
    )
    await db.flush()
    return MallAttributionResult(source=source, handling=handling)
