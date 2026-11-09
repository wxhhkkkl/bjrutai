"""One synthetic order is the source for return, invoice, performance and finance facts."""

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select

from src.api.mall_deps import MallActor
from src.core.config import get_settings
from src.models.binding import BindingStatus, Customer
from src.models.commission_result import CommissionResult
from src.models.mall_base import utc_now
from src.models.mall_consumption import MallConsumption
from src.models.mall_finance import (
    MallInvoice,
    MallInvoiceRequest,
    MallPayment,
    MallReconciliationBatch,
    MallRefund,
)
from src.models.mall_operations import MallFile, MallSettings
from src.models.mall_trade import MallAftersale, MallAftersaleItem, MallOrder, MallOrderItem
from src.models.performance_adjustment import (
    PerformanceAdjustment,
    PerformanceAdjustmentApplication,
)
from src.models.performance_evidence import PerformanceEvidence
from src.models.performance_rule import RuleType
from src.models.user import User
from src.schemas.mall_aftersale import (
    AftersaleCreate,
    AftersaleDecision,
    ReasonAction,
    ReturnReceipt,
    ReturnShipment,
)
from src.schemas.mall_catalog import VersionAction
from src.schemas.mall_fulfillment import ShipmentCreate
from src.schemas.mall_reconciliation import ReconciliationCreate
from src.services import commission_service, settlement_service
from src.services.mall_aftersale_service import (
    apply_aftersale,
    decide_aftersale,
    receive_return,
    submit_return_shipment,
)
from src.services.mall_attribution_service import attribute_mall_consumption
from src.services.mall_payment_service import apply_verified_payment, prepare_payment
from src.services.mall_reconciliation_service import close_reconciliation, create_reconciliation
from src.services.mall_refund_service import apply_verified_refund, execute_refund
from src.services.mall_shipment_service import ship_order
from src.services.performance_adjustment_service import (
    propose_adjustment,
    review_performance_adjustment,
)
from tests.conftest import (
    auth_header,
    make_access_token,
    seed_hierarchy_node,
    seed_promoter,
    seed_user,
)
from tests.contract.test_admin_mall_orders import admin
from tests.mall_checkout_fixtures import ADDRESS, checkout_seed
from tests.mall_consumption_fixtures import add_bill, add_performance_rule
from tests.unit.test_mall_payment_service import success
from tests.unit.test_mall_refund_service import refund_fact


async def _performance_context_for_buyer(db, buyer_id: int, *, identity: str) -> dict:
    promoter_user_id = await seed_user(
        db,
        openid=f"e2e-promoter-{identity}",
        user_type="promoter",
        name="商城绩效推广员",
    )
    org_id = await seed_hierarchy_node(db, name=f"商城绩效组织-{identity}")
    distributor_id = await seed_promoter(db, user_id=promoter_user_id, node_id=org_id)
    customer = Customer(
        user_id=buyer_id,
        distributor_id=distributor_id,
        name="商城绩效客户",
        phone="13800138000",
        phone_masked="138****8000",
        id_card_encrypted="synthetic-ciphertext",
        id_card_masked="110***********1234",
        binding_status=BindingStatus.BOUND,
        bound_at=datetime(2026, 1, 1),
        version=1,
    )
    db.add(customer)
    await db.flush()
    return {
        "personUserId": promoter_user_id,
        "distributorId": distributor_id,
        "orgId": org_id,
        "buyerUserId": buyer_id,
        "customerId": customer.id,
    }


def _verified_file(*, purpose: str, owner_id: int, order_id: int | None, label: str, body: bytes):
    suffix = uuid4().hex
    return MallFile(
        object_key=f"mall/verified/{purpose}/{label}-{suffix}",
        purpose=purpose,
        owner_actor_type="admin",
        owner_actor_id=owner_id,
        order_id=order_id,
        mime="application/pdf" if purpose == "invoice_pdf" else "text/csv",
        size=len(body),
        sha256=sha256(body).hexdigest(),
        status="verified",
        expires_at=utc_now() - timedelta(seconds=1),
    )


def _business_date(timestamp: datetime) -> date:
    return timestamp.replace(tzinfo=timezone.utc).astimezone(ZoneInfo("Asia/Shanghai")).date()


def _next_period(period: str) -> str:
    year, month = (int(part) for part in period.split("-"))
    month += 1
    if month == 13:
        year += 1
        month = 1
    return f"{year:04d}-{month:02d}"


@pytest.mark.asyncio
async def test_one_order_closes_purchase_return_invoice_performance_and_reconciliation(
    client, db_session, monkeypatch
):
    settings = get_settings()
    monkeypatch.setattr(settings, "mall_enabled", True)
    monkeypatch.setattr(settings, "mall_purchase_enabled", True)
    monkeypatch.setattr(settings, "wechat_app_id", "wx-test")
    monkeypatch.setattr(settings, "mall_wechat_mchid", "test-merchant", raising=False)

    buyer, _, _, skus = await checkout_seed(db_session)
    identity = uuid4().hex
    buyer_openid = f"e2e-buyer-{identity}"
    buyer_row = await db_session.get(User, buyer.actor_id)
    buyer_row.openid = buyer_openid
    await db_session.commit()
    buyer_headers = auth_header(make_access_token(user_id=buyer.actor_id, user_type="personal"))

    address_response = await client.post(
        "/api/v1/mall/addresses",
        headers={**buyer_headers, "Idempotency-Key": f"e2e-address-{identity}"},
        json=ADDRESS,
    )
    assert address_response.status_code == 200, address_response.text
    quote_response = await client.post(
        "/api/v1/mall/checkout/quote",
        headers=buyer_headers,
        json={
            "addressId": address_response.json()["data"]["id"],
            "items": [{"skuId": str(row.id), "quantity": 1} for row in skus],
        },
    )
    assert quote_response.status_code == 200, quote_response.text
    order_response = await client.post(
        "/api/v1/mall/orders",
        headers={**buyer_headers, "Idempotency-Key": f"e2e-order-{identity}"},
        json={
            "quoteToken": quote_response.json()["data"]["quoteToken"],
            "consentVersion": "mall-test-v1",
            "consentConfirmed": True,
        },
    )
    assert order_response.status_code == 200, order_response.text
    order = await db_session.get(MallOrder, int(order_response.json()["data"]["id"]))
    payment = await prepare_payment(
        db_session,
        buyer,
        order.id,
        VersionAction(expectedVersion=order.version),
        key=f"e2e-prepare-payment-{identity}",
    )
    paid_at = utc_now()
    paid_fact = replace(
        success(payment, order, paid_at=paid_at),
        transaction_id=f"SYN-E2E-TXN-{identity[:24]}",
        openid=buyer_openid,
    )
    await apply_verified_payment(db_session, payment.id, paid_fact)
    await db_session.commit()
    await db_session.refresh(order)
    source = await db_session.scalar(
        select(MallConsumption).where(MallConsumption.order_id == order.id)
    )
    assert source is not None and source.status == "unassigned"

    permissions = [
        "mall.attribution.write",
        "mall.invoices.read",
        "mall.invoices.write",
        "mall.shipments.write",
        "mall.aftersales.review",
        "mall.returns.receive",
        "mall.refunds.execute",
        "mall.reconciliations.read",
        "mall.reconciliations.write",
    ]
    admin_id, _, finance_headers = await admin(db_session, permissions)
    finance = MallActor("admin", admin_id, frozenset(permissions))

    # Freeze the original period without the unassigned mall source, then backfill
    # the verified historical binding and reconcile its delta independently.
    context = await _performance_context_for_buyer(db_session, buyer.actor_id, identity=identity)
    bill_at = paid_at.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    await add_bill(db_session, context, 800000, bill_at)
    await add_performance_rule(
        db_session,
        context,
        tiers=[{"minCent": 1, "maxCent": None, "ratio": 0.05}],
    )
    await settlement_service.settle(db_session, source.business_period, operator_id=admin_id)
    await settlement_service.review_settlement(
        db_session, source.business_period, operator_id=admin_id
    )
    anchor = await db_session.scalar(
        select(PerformanceEvidence).where(
            PerformanceEvidence.period == source.business_period,
            PerformanceEvidence.distributor_id == context["distributorId"],
            PerformanceEvidence.rule_type == RuleType.INTRA_ORG.value,
        )
    )
    original_result = await db_session.scalar(
        select(CommissionResult).where(
            CommissionResult.period == source.business_period,
            CommissionResult.distributor_id == context["distributorId"],
            CommissionResult.rule_type == RuleType.INTRA_ORG,
        )
    )
    assert anchor is not None and original_result is not None
    assert original_result.base_cent == 800000 and original_result.commission_cent == 40000

    attribution = await attribute_mall_consumption(
        db_session,
        actor=finance,
        consumption_id=source.id,
        expected_version=source.source_version,
        distributor_id=context["distributorId"],
        customer_id=context["customerId"],
        evidence_file_ids=[],
        reason="支付日前已生效的合成绑定记录，纳入本地闭环验收",
        idempotency_key=f"e2e-attribute-{identity}",
    )
    assert attribution.handling == "adjustment_pending"
    positive_adjustment = await db_session.scalar(
        select(PerformanceAdjustment).where(
            PerformanceAdjustment.evidence_id == anchor.id,
            PerformanceAdjustment.trigger_source_id == source.id,
        )
    )
    assert positive_adjustment is not None
    assert positive_adjustment.delta_cent == round(order.goods_amount_cent * 0.05)
    await review_performance_adjustment(
        db_session,
        adjustment_id=positive_adjustment.id,
        expected_version=positive_adjustment.version,
        admin_id=admin_id,
    )
    next_period = _next_period(source.business_period)
    await commission_service.compute_commission(db_session, next_period)
    await settlement_service.review_settlement(db_session, next_period, operator_id=admin_id)
    await commission_service.redeem_commission_points(
        db_session,
        next_period,
        context["distributorId"],
        RuleType.INTRA_ORG.value,
        operator_id=admin_id,
    )
    await db_session.refresh(positive_adjustment)
    assert positive_adjustment.remaining_cent == 0
    redeemed_result = await db_session.scalar(
        select(CommissionResult).where(
            CommissionResult.period == next_period,
            CommissionResult.distributor_id == context["distributorId"],
            CommissionResult.rule_type == RuleType.INTRA_ORG,
        )
    )
    assert redeemed_result is not None and redeemed_result.origin_kind == "adjustment_only"
    assert redeemed_result.redeemed_points_x100 == round(order.goods_amount_cent * 0.05)

    invoice_response = await client.post(
        "/api/v1/mall/invoice-requests",
        headers={**buyer_headers, "Idempotency-Key": f"e2e-invoice-request-{identity}"},
        json={
            "orderId": str(order.id),
            "expectedOrderVersion": order.version,
            "buyerType": "personal",
            "title": "闭环合成测试个人",
            "invoiceType": "digital_normal",
            "consentVersion": "mall-test-v1",
            "consentConfirmed": True,
        },
    )
    assert invoice_response.status_code == 200, invoice_response.text
    invoice_request = invoice_response.json()["data"]
    claim = await client.post(
        f"/api/v1/admin/mall/invoice-requests/{invoice_request['id']}/claim",
        headers={**finance_headers, "Idempotency-Key": f"e2e-invoice-claim-{identity}"},
        json={"expectedVersion": invoice_request["version"]},
    )
    assert claim.status_code == 200, claim.text
    blue_file = _verified_file(
        purpose="invoice_pdf",
        owner_id=admin_id,
        order_id=order.id,
        label="blue",
        body=f"synthetic blue invoice {identity}".encode(),
    )
    db_session.add(blue_file)
    await db_session.commit()
    blue_response = await client.post(
        f"/api/v1/admin/mall/invoice-requests/{invoice_request['id']}/record",
        headers={**finance_headers, "Idempotency-Key": f"e2e-invoice-record-{identity}"},
        json={
            "expectedVersion": claim.json()["data"]["version"],
            "invoiceNo": f"SYN-E2E-BLUE-{identity[:16]}",
            "issuedAt": utc_now().isoformat() + "Z",
            "sellerIdentity": "SYNTHETIC-SELLER",
            "totalCent": order.paid_amount_cent,
            "fileId": str(blue_file.id),
            "reason": "仅为本地合成税务事实",
        },
    )
    assert blue_response.status_code == 200, blue_response.text
    blue = blue_response.json()["data"]

    await db_session.refresh(order)
    await ship_order(
        db_session,
        finance,
        order.id,
        ShipmentCreate(
            expectedVersion=order.version,
            courierCode="sf",
            trackingNo=f"SF{identity[:10].upper()}",
        ),
        key=f"e2e-ship-{identity}",
    )
    mall_settings = await db_session.get(MallSettings, 1)
    mall_settings.return_address_snapshot = {
        "recipientName": "合成验收退货联系人",
        "addressLine": "本地合成测试仓地址",
    }
    await db_session.refresh(order)
    order_lines = (
        await db_session.scalars(
            select(MallOrderItem)
            .where(MallOrderItem.order_id == order.id)
            .order_by(MallOrderItem.id)
        )
    ).all()
    aftersale = await apply_aftersale(
        db_session,
        buyer,
        AftersaleCreate(
            orderId=str(order.id),
            expectedOrderVersion=order.version,
            method="return_refund",
            items=[
                {"orderItemId": str(line.id), "quantity": line.quantity} for line in order_lines
            ],
            reason="虚构的全量退货验收",
        ),
        key=f"e2e-aftersale-{identity}",
    )
    aftersale = await decide_aftersale(
        db_session,
        finance,
        aftersale.id,
        AftersaleDecision(
            expectedVersion=aftersale.version,
            decision="approve",
            reason="合成全量退货通过",
        ),
        key=f"e2e-aftersale-approve-{identity}",
    )
    aftersale = await submit_return_shipment(
        db_session,
        buyer,
        aftersale.id,
        ReturnShipment(
            expectedVersion=aftersale.version,
            courierCode="sf",
            trackingNo=f"RT{identity[:10].upper()}",
        ),
        key=f"e2e-return-shipment-{identity}",
    )
    return_lines = (
        await db_session.scalars(
            select(MallAftersaleItem)
            .where(MallAftersaleItem.aftersale_id == aftersale.id)
            .order_by(MallAftersaleItem.id)
        )
    ).all()
    aftersale = await receive_return(
        db_session,
        finance,
        aftersale.id,
        ReturnReceipt(
            expectedVersion=aftersale.version,
            result="accepted",
            sellableItems=[
                {"aftersaleItemId": str(line.id), "quantity": line.quantity}
                for line in return_lines
            ],
            reason="合成验收商品完好",
        ),
        key=f"e2e-return-receipt-{identity}",
    )
    refund = await execute_refund(
        db_session,
        finance,
        aftersale.id,
        VersionAction(expectedVersion=aftersale.version),
        key=f"e2e-refund-submit-{identity}",
    )
    refund_success_at = utc_now()
    verified_refund = replace(
        refund_fact(refund, payment),
        transaction_id=payment.channel_transaction_id,
        channel_refund_id=f"SYN-E2E-REF-{identity[:20]}",
        success_at=refund_success_at,
    )
    await apply_verified_refund(db_session, refund.id, verified_refund)
    await db_session.commit()
    await db_session.refresh(source)
    assert aftersale.status == "completed"
    assert refund.status == "succeeded" and refund.total_cent == order.goods_amount_cent
    assert source.successful_goods_refund_cent == source.original_goods_cent
    assert source.performance_base_cent == 0

    negative_adjustment = await propose_adjustment(
        db_session,
        anchor.id,
        trigger_source_type="mall",
        trigger_source_id=source.id,
        trigger_version=source.source_version,
    )
    await review_performance_adjustment(
        db_session,
        adjustment_id=negative_adjustment.id,
        expected_version=negative_adjustment.version,
        admin_id=admin_id,
    )
    assert negative_adjustment.delta_cent == -round(order.goods_amount_cent * 0.05)
    assert positive_adjustment.trigger_version < negative_adjustment.trigger_version

    blue_model = await db_session.get(MallInvoice, int(blue["id"]), populate_existing=True)
    await db_session.refresh(blue_model)
    assert blue_model.status == "red_pending"
    red_file = _verified_file(
        purpose="invoice_pdf",
        owner_id=admin_id,
        order_id=order.id,
        label="red",
        body=f"synthetic red invoice {identity}".encode(),
    )
    db_session.add(red_file)
    await db_session.commit()
    red_response = await client.post(
        f"/api/v1/admin/mall/invoices/{blue['id']}/red-record",
        headers={**finance_headers, "Idempotency-Key": f"e2e-red-record-{identity}"},
        json={
            "expectedVersion": blue_model.version,
            "invoiceNo": f"SYN-E2E-RED-{identity[:16]}",
            "issuedAt": utc_now().isoformat() + "Z",
            "totalCent": refund.total_cent,
            "fileId": str(red_file.id),
            "reason": "对应本地合成成功退款金额",
        },
    )
    assert red_response.status_code == 200, red_response.text
    red = red_response.json()["data"]
    assert red["originalInvoiceId"] == blue["id"] and red["totalCent"] == refund.total_cent

    # A Beijing-day batch is closed for each day touched by the confirmed payment
    # or refund. This remains deterministic when a run straddles local midnight.
    paid_day = _business_date(order.paid_at)
    refund_day = _business_date(refund.confirmed_at)
    totals = {paid_day: {"paid": payment.amount_cent, "refund": 0}}
    if refund_day in totals:
        totals[refund_day]["refund"] += refund.total_cent
    else:
        totals[refund_day] = {"paid": 0, "refund": refund.total_cent}
    batches = []
    for day, amounts in sorted(totals.items()):
        statement_content = (
            "synthetic local acceptance statement\n"
            f"business_date={day.isoformat()}\n"
            f"order_id={order.id}\n"
            f"payment_no={payment.out_trade_no}\n"
            f"refund_no={refund.out_refund_no}\n"
        ).encode()
        statement = _verified_file(
            purpose="reconciliation_evidence",
            owner_id=admin_id,
            order_id=None,
            label=f"day-{day.isoformat()}",
            body=statement_content,
        )
        db_session.add(statement)
        await db_session.flush()
        batch = await create_reconciliation(
            db_session,
            finance,
            ReconciliationCreate(
                businessDate=day,
                statementFileId=str(statement.id),
                expectedPaidCent=amounts["paid"],
                expectedRefundCent=amounts["refund"],
                evidenceNote="本地合成订单和渠道日账单事实，不代表真实商户账单",
            ),
            key=f"e2e-reconciliation-{identity}-{day.isoformat()}",
        )
        closed = await close_reconciliation(
            db_session,
            finance,
            batch.id,
            ReasonAction(expectedVersion=batch.version, reason="合成账单与本地成功事实一致"),
            key=f"e2e-reconciliation-close-{identity}-{day.isoformat()}",
        )
        batches.append(closed)
    await db_session.commit()

    await db_session.refresh(order)
    await db_session.refresh(payment)
    await db_session.refresh(refund)
    await db_session.refresh(source)
    invoices = (
        await db_session.scalars(
            select(MallInvoice).where(MallInvoice.order_id == order.id).order_by(MallInvoice.id)
        )
    ).all()
    adjustments = (
        await db_session.scalars(
            select(PerformanceAdjustment)
            .where(PerformanceAdjustment.evidence_id == anchor.id)
            .order_by(PerformanceAdjustment.id)
        )
    ).all()
    assert order.active_payment_id == payment.id and payment.order_id == order.id
    assert order.status == "closed" and order.refunded_goods_cent == order.goods_amount_cent
    assert refund.order_id == order.id and refund.payment_id == payment.id
    assert aftersale.order_id == order.id and refund.aftersale_id == aftersale.id
    assert source.order_id == order.id
    invoice_request_model = await db_session.get(MallInvoiceRequest, int(invoice_request["id"]))
    assert invoice_request_model is not None and invoice_request_model.order_id == order.id
    assert len(invoices) == 2 and invoices[1].original_invoice_id == invoices[0].id
    assert all(row.request_id == invoice_request_model.id for row in invoices)
    assert invoices[0].status == "partially_red" and invoices[1].kind == "red"
    assert invoices[0].total_cent - invoices[1].total_cent == (
        order.paid_amount_cent - refund.total_cent
    )
    assert [row.delta_cent for row in adjustments] == [
        round(order.goods_amount_cent * 0.05),
        -round(order.goods_amount_cent * 0.05),
    ]
    assert all(
        row.trigger_source_type == "mall" and row.trigger_source_id == source.id
        for row in adjustments
    )
    applications = (
        await db_session.scalars(
            select(PerformanceAdjustmentApplication).where(
                PerformanceAdjustmentApplication.adjustment_id == positive_adjustment.id
            )
        )
    ).all()
    assert applications and sum(row.settled_cent for row in applications) == round(
        order.goods_amount_cent * 0.05
    )
    assert len(batches) in (1, 2) and all(row.status == "closed" for row in batches)
    assert sum(row.local_paid_cent for row in batches) == payment.amount_cent
    assert sum(row.local_refund_cent for row in batches) == refund.total_cent
    assert (
        await db_session.scalar(
            select(func.count()).select_from(MallPayment).where(MallPayment.order_id == order.id)
        )
        == 1
    )
    assert (
        await db_session.scalar(
            select(func.count()).select_from(MallRefund).where(MallRefund.order_id == order.id)
        )
        == 1
    )
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(MallConsumption)
            .where(MallConsumption.order_id == order.id)
        )
        == 1
    )
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(MallInvoiceRequest)
            .where(MallInvoiceRequest.order_id == order.id)
        )
        == 1
    )
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(MallAftersale)
            .where(MallAftersale.order_id == order.id)
        )
        == 1
    )
    assert await db_session.scalar(
        select(func.count())
        .select_from(MallReconciliationBatch)
        .where(MallReconciliationBatch.id.in_([row.id for row in batches]))
    ) == len(batches)
