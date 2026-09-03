"""TDD coverage for the admin manual-consumption service."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from src.core.exceptions import ConflictException, ValidationException
from src.models.audit import AuditLog
from src.models.bill import Bill, TransactionStatus
from src.models.binding import BindingStatus
from src.schemas.admin_contribution import ManualConsumptionCreateRequest
from src.services.manual_consumption_service import (
    create_manual_consumption,
    search_eligible_customers,
)
from tests.conftest import seed_admin, seed_bound_customer_with_attribution


def _request(customer, *, amount=12880, note="线下收款补录", minutes_ago=1):
    return ManualConsumptionCreateRequest(
        customerId=str(customer.id),
        customerVersion=customer.version,
        consumedAt=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
        amountCent=amount,
        note=note,
    )


@pytest.mark.asyncio
async def test_search_returns_only_masked_bound_customer(db_session):
    seeded = await seed_bound_customer_with_attribution(db_session)

    result = await search_eligible_customers(db_session, keyword="138001", page_size=20)

    assert len(result["items"]) == 1
    item = result["items"][0]
    assert item["customerId"] == str(seeded["customer"].id)
    assert item["phoneMasked"] == "138****8000"
    assert item["idCardMasked"].endswith("1234")
    assert "13800138000" not in str(item)
    assert item["personName"] == "测试拓展人"
    assert item["orgName"] == "测试机构"

    seeded["customer"].binding_status = BindingStatus.UNBOUND
    await db_session.flush()
    assert (await search_eligible_customers(db_session, keyword="测试", page_size=20))["items"] == []


@pytest.mark.asyncio
async def test_create_manual_consumption_and_replay_once(db_session):
    admin_id = await seed_admin(db_session)
    seeded = await seed_bound_customer_with_attribution(db_session)
    data = _request(seeded["customer"])

    first = await create_manual_consumption(
        db_session,
        data=data,
        admin_id=admin_id,
        admin_username="admin",
        idempotency_key="manual-test-001",
        ip_address="127.0.0.1",
    )
    replay = await create_manual_consumption(
        db_session,
        data=data,
        admin_id=admin_id,
        admin_username="admin",
        idempotency_key="manual-test-001",
        ip_address="127.0.0.1",
    )

    assert first["replayed"] is False
    assert replay["replayed"] is True
    assert first["id"] == replay["id"]
    assert first["recordNo"].startswith("MANUAL-")
    assert first["source"] == "manual"
    assert first["status"] == "paid"
    assert first["amountCent"] == 12880
    assert first["personName"] == "测试拓展人"
    assert first["orgName"] == "测试机构"

    bill_count = (await db_session.execute(select(func.count(Bill.id)))).scalar_one()
    audit_count = (
        await db_session.execute(
            select(func.count(AuditLog.id)).where(AuditLog.action == "manual_consumption_create")
        )
    ).scalar_one()
    assert bill_count == 1
    assert audit_count == 1

    bill = (await db_session.execute(select(Bill))).scalar_one()
    assert bill.transaction_status == TransactionStatus.PAID
    assert bill.total_amount_cent == bill.paid_amount_cent == 12880
    assert bill.attributed_distributor_id == seeded["distributor"].id
    assert bill.attributed_org_id == seeded["org"].id


@pytest.mark.asyncio
async def test_same_idempotency_key_rejects_changed_content(db_session):
    admin_id = await seed_admin(db_session)
    seeded = await seed_bound_customer_with_attribution(db_session)
    original = _request(seeded["customer"])
    changed = original.model_copy(update={"amount_cent": 9900})

    await create_manual_consumption(
        db_session,
        data=original,
        admin_id=admin_id,
        admin_username="admin",
        idempotency_key="manual-conflict",
    )
    with pytest.raises(ConflictException) as exc_info:
        await create_manual_consumption(
            db_session,
            data=changed,
            admin_id=admin_id,
            admin_username="admin",
            idempotency_key="manual-conflict",
        )
    assert exc_info.value.code == 40922


@pytest.mark.asyncio
async def test_rejects_future_time_changed_version_and_unbound_customer(db_session):
    admin_id = await seed_admin(db_session)
    seeded = await seed_bound_customer_with_attribution(db_session)
    customer = seeded["customer"]

    future = _request(customer, minutes_ago=-5)
    with pytest.raises(ValidationException):
        await create_manual_consumption(
            db_session,
            data=future,
            admin_id=admin_id,
            admin_username="admin",
            idempotency_key="future",
        )

    changed_version = _request(customer).model_copy(update={"customer_version": customer.version + 1})
    with pytest.raises(ConflictException) as version_error:
        await create_manual_consumption(
            db_session,
            data=changed_version,
            admin_id=admin_id,
            admin_username="admin",
            idempotency_key="version",
        )
    assert version_error.value.code == 40920

    customer.binding_status = BindingStatus.UNBOUND
    await db_session.flush()
    with pytest.raises(ConflictException) as bound_error:
        await create_manual_consumption(
            db_session,
            data=_request(customer),
            admin_id=admin_id,
            admin_username="admin",
            idempotency_key="unbound",
        )
    assert bound_error.value.code == 40921

    audit_count = (
        await db_session.execute(
            select(func.count(AuditLog.id)).where(AuditLog.action == "manual_consumption_create")
        )
    ).scalar_one()
    assert audit_count == 0


@pytest.mark.asyncio
async def test_audit_detail_is_minimal_and_excludes_sensitive_values(db_session):
    admin_id = await seed_admin(db_session, username="finance")
    seeded = await seed_bound_customer_with_attribution(db_session)
    await create_manual_consumption(
        db_session,
        data=_request(seeded["customer"], note="不要复制到审计日志的备注"),
        admin_id=admin_id,
        admin_username="finance",
        idempotency_key="audit-safe",
        ip_address="10.0.0.8",
    )

    audit = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.action == "manual_consumption_create")
        )
    ).scalar_one()
    assert audit.user_id is None
    assert audit.ip_address == "10.0.0.8"
    assert audit.detail["adminId"] == admin_id
    assert audit.detail["adminUsername"] == "finance"
    serialized = str(audit.detail)
    assert "13800138000" not in serialized
    assert "110101199001011234" not in serialized
    assert "不要复制" not in serialized
