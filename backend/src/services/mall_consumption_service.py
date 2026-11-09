"""One source per paid order, preserving the existing partial-refund rule."""

from datetime import timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from ..core.exceptions import ConflictException
from ..models.binding import BindingStatus, Customer
from ..models.distributor import Distributor, DistributorStatus
from ..models.mall_base import utc_now
from ..models.mall_consumption import MallConsumption
from ..models.organization import Organization, OrgStatus
from ..models.performance_settlement import PerformanceSettlement, SettlementStatus
from ..models.user import ActivationStatus, User
from .mall_job_service import enqueue_mall_job
from .performance_period_service import bump_period


def performance_base(original_goods_cent, successful_goods_refund_cent):
    if (
        type(original_goods_cent) is not int
        or type(successful_goods_refund_cent) is not int
        or not 0 <= successful_goods_refund_cent <= original_goods_cent
    ):
        raise ValueError("invalid goods refund amounts")
    return 0 if successful_goods_refund_cent == original_goods_cent else original_goods_cent


async def record_paid_order(db, order):
    """Caller already holds the order lock; never match a customer by phone."""
    if order.paid_amount_cent != order.payable_amount_cent or order.paid_at is None:
        raise ConflictException(message="未核实足额收款，不得计入商城消费")
    # The parent order serializes this unique source. An absent child-range lock
    # would deadlock concurrent source inserts while they wait on the period row.
    existing = (
        await db.execute(
            select(MallConsumption)
            .where(MallConsumption.order_id == order.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if existing:
        if (existing.buyer_user_id, existing.original_goods_cent, existing.paid_at) != (
            order.buyer_user_id,
            order.goods_amount_cent,
            order.paid_at,
        ):
            raise ConflictException(message="商城消费原始事实不一致")
        return existing
    period = (
        order.paid_at.replace(tzinfo=timezone.utc)
        .astimezone(ZoneInfo("Asia/Shanghai"))
        .strftime("%Y-%m")
    )
    coordination = await bump_period(db, period)
    customer = (
        await db.execute(
            select(Customer)
            .where(Customer.user_id == order.buyer_user_id)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    distributor = None
    org = None
    evidence = {"capturedAt": utc_now().isoformat() + "Z", "basis": "no_verified_binding"}
    if customer and customer.binding_status == BindingStatus.BOUND and customer.distributor_id:
        candidate = (
            await db.execute(
                select(Distributor)
                .where(Distributor.id == customer.distributor_id)
                .with_for_update(read=True)
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        candidate_org = (
            (
                await db.execute(
                    select(Organization)
                    .where(Organization.id == candidate.org_id)
                    .with_for_update(read=True)
                    .execution_options(populate_existing=True)
                )
            ).scalar_one_or_none()
            if candidate
            else None
        )
        candidate_user = (
            await db.get(User, candidate.user_id, populate_existing=True) if candidate else None
        )
        if (
            customer.bound_at
            and customer.bound_at <= order.paid_at
            and candidate
            and candidate.status == DistributorStatus.ACTIVE
            and candidate_user
            and candidate_user.activation_status == ActivationStatus.ACTIVE
            and candidate_org
            and candidate_org.status == OrgStatus.ACTIVE
        ):
            distributor, org = candidate, candidate_org
            evidence.update(
                basis="existing_authorized_binding",
                customerVersion=customer.version,
                boundAt=customer.bound_at.isoformat() + "Z",
            )
    source = MallConsumption(
        order_id=order.id,
        buyer_user_id=order.buyer_user_id,
        customer_id=customer.id if distributor else None,
        attributed_distributor_id=distributor.id if distributor else None,
        trade_org_id=org.id if org else None,
        paid_at=order.paid_at,
        business_period=period,
        original_goods_cent=order.goods_amount_cent,
        successful_goods_refund_cent=0,
        performance_base_cent=performance_base(order.goods_amount_cent, 0),
        status="assigned" if distributor else "unassigned",
        attribution_evidence=evidence,
        name_snapshots={"customer": customer.name, "organization": org.name} if distributor else {},
    )
    db.add(source)
    order.business_period = period
    await db.flush()
    reviewed = await db.scalar(
        select(PerformanceSettlement.id)
        .where(
            PerformanceSettlement.period == period,
            PerformanceSettlement.status == SettlementStatus.REVIEWED,
        )
        .with_for_update(read=True)
    )
    if coordination.status != "open" or reviewed:
        job = await enqueue_mall_job(
            db,
            kind="mall_consumption_frozen_source",
            entity_type="mall_consumption",
            entity_id=source.id,
            entity_version=source.version,
            dedupe_key=f"mall-frozen-source:{source.id}",
        )
        job.status = "manual"
    return source
