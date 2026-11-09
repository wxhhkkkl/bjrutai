"""Synthetic source rows shared by mall-performance projection tests."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select

from src.models.bill import Bill, TransactionStatus
from src.models.binding import BindingStatus, Customer
from src.models.mall_consumption import MallConsumption
from src.models.mall_trade import MallOrder
from tests.conftest import seed_hierarchy_node, seed_promoter, seed_user


async def performance_context(db):
    identity = uuid4().hex
    person_user_id = await seed_user(
        db, openid=f"mall-performance-person-{identity}", user_type="promoter", name="核算推广员"
    )
    org_id = await seed_hierarchy_node(db, name=f"核算组织-{identity}")
    distributor_id = await seed_promoter(db, user_id=person_user_id, node_id=org_id)
    buyer_user_id = await seed_user(
        db, openid=f"mall-performance-buyer-{identity}", user_type="personal", name="商城买家"
    )
    customer = Customer(
        user_id=buyer_user_id,
        distributor_id=distributor_id,
        name="商城客户",
        phone="13800138000",
        phone_masked="138****8000",
        id_card_encrypted="test-ciphertext",
        id_card_masked="110***********1234",
        binding_status=BindingStatus.BOUND,
        bound_at=datetime(2026, 1, 1),
        version=1,
    )
    db.add(customer)
    await db.flush()
    return {
        "personUserId": person_user_id,
        "distributorId": distributor_id,
        "orgId": org_id,
        "buyerUserId": buyer_user_id,
        "customerId": customer.id,
    }


async def add_bill(db, context, amount_cent, paid_at, *, status=TransactionStatus.PAID):
    identity = uuid4().hex
    bill = Bill(
        customer_id=context["customerId"],
        transaction_id=f"mall-projection-bill-{identity}",
        transaction_time=paid_at,
        total_amount_cent=amount_cent,
        paid_amount_cent=amount_cent,
        transaction_status=status,
    )
    db.add(bill)
    await db.flush()
    return bill


async def add_mall_source(
    db,
    context,
    amount_cent,
    paid_at,
    *,
    attributed=True,
    successful_goods_refund_cent=0,
    performance_base_cent=None,
):
    identity = uuid4().hex
    paid_instant = (
        paid_at.replace(tzinfo=timezone.utc)
        if paid_at.tzinfo is None
        else paid_at.astimezone(timezone.utc)
    )
    business_period = paid_instant.astimezone(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m")
    order = MallOrder(
        order_no=f"M{identity[:24]}",
        buyer_user_id=context["buyerUserId"],
        status="pending_shipment",
        currency="CNY",
        goods_amount_cent=amount_cent,
        freight_amount_cent=500,
        payable_amount_cent=amount_cent + 500,
        paid_amount_cent=amount_cent + 500,
        address_snapshot={"recipientName": "测试买家", "phoneMasked": "138****8000"},
        policy_snapshot={"attribution": "snapshot"},
        expires_at=paid_at + timedelta(minutes=30),
        paid_at=paid_at,
        business_period=business_period,
    )
    db.add(order)
    await db.flush()
    base_cent = performance_base_cent
    if base_cent is None:
        base_cent = 0 if successful_goods_refund_cent == amount_cent else amount_cent
    source = MallConsumption(
        order_id=order.id,
        buyer_user_id=context["buyerUserId"],
        customer_id=context["customerId"] if attributed else None,
        attributed_distributor_id=context["distributorId"] if attributed else None,
        trade_org_id=context["orgId"] if attributed else None,
        name_snapshots={"customer": "商城客户", "organization": "核算组织"} if attributed else {},
        paid_at=paid_at,
        business_period=business_period,
        original_goods_cent=amount_cent,
        successful_goods_refund_cent=successful_goods_refund_cent,
        performance_base_cent=base_cent,
        status="assigned" if attributed else "unassigned",
        attribution_evidence=(
            {"basis": "test_fixture"} if attributed else {"basis": "no_verified_binding"}
        ),
    )
    db.add(source)
    await db.flush()
    return order, source


async def add_performance_rule(
    db,
    context,
    *,
    rule_type="intra_org",
    tiers=None,
    version=1,
    status="active",
):
    from src.models.performance_rule import PerformanceRule, RuleStatus, RuleType

    rule = PerformanceRule(
        org_id=context["orgId"],
        rule_type=RuleType(rule_type),
        tiers=tiers or [{"minCent": 0, "maxCent": None, "ratio": 0.08}],
        status=RuleStatus(status),
        version=version,
    )
    db.add(rule)
    await db.flush()
    return rule


async def add_frozen_evidence(
    db,
    context,
    *,
    period="2026-07",
    rule_type="intra_org",
    rule_snapshot=None,
    result_id=None,
    original_base_cent=0,
    legacy_base_cent=None,
    mall_base_cent=0,
    original_commission_cent=0,
    result_presence="not_generated",
    result_absence_reason="below_first_tier",
    evidence_status="complete",
):
    from src.models.performance_evidence import PerformanceEvidence
    from src.models.performance_settlement import PerformanceSettlement, SettlementStatus
    from src.services.performance_period_service import lock_period

    settlement = await db.scalar(
        select(PerformanceSettlement).where(PerformanceSettlement.period == period)
    )
    if settlement is None:
        settlement = PerformanceSettlement(period=period, status=SettlementStatus.REVIEWED)
        db.add(settlement)
        await db.flush()
    else:
        settlement.status = SettlementStatus.REVIEWED

    period_row = await lock_period(db, period)
    period_row.status = "frozen"

    evidence = PerformanceEvidence(
        settlement_id=settlement.id,
        evidence_key=f"{period}:{context['distributorId']}:{rule_type}",
        result_id=result_id,
        period=period,
        distributor_id=context["distributorId"],
        rule_type=rule_type,
        org_id=context["orgId"],
        frozen_members=[context["distributorId"]],
        organization_path_snapshot=[context["orgId"]],
        rule_source="org" if rule_snapshot else "missing",
        rule_snapshot=rule_snapshot or {},
        algorithm_version="mall-performance-v1",
        legacy_base_cent=(original_base_cent if legacy_base_cent is None else legacy_base_cent),
        mall_base_cent=mall_base_cent,
        original_base_cent=original_base_cent,
        original_commission_cent=original_commission_cent,
        result_presence=result_presence,
        result_absence_reason=result_absence_reason,
        input_digest="e" * 64,
        frozen_at=datetime(2026, 8, 1),
        evidence_status=evidence_status,
    )
    db.add(evidence)
    await db.flush()
    return evidence
