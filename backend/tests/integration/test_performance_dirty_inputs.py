"""Input writers serialize period revisions before changing unsettled performance inputs."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from src.core.exceptions import ConflictException
from src.models.commission_result import CommissionResult
from src.models.performance_evidence import PerformancePeriodVersion
from src.models.performance_rule import RuleType
from src.models.performance_settlement import PerformanceSettlement, SettlementStatus
from src.schemas.distributor import DistributorRoleUpdate, DistributorUpdate
from src.schemas.organization import OrgCreate, OrgMigrateRequest, OrgUpdate
from src.schemas.performance_rule import (
    PerformanceRuleUpdateRequest,
    PersonalPerformanceRuleUpdateRequest,
    Tier,
)
from src.services import (
    distributor_service,
    organization_service,
    performance_period_service,
    performance_service,
)
from tests.conftest import seed_admin, seed_bound_customer_with_attribution
from tests.mall_consumption_fixtures import add_bill, add_mall_source, performance_context


async def _period_version(db, period):
    return await db.scalar(
        select(PerformancePeriodVersion).where(PerformancePeriodVersion.period == period)
    )


@pytest.mark.asyncio
async def test_bump_periods_locks_sorted_and_skips_frozen_or_reviewed_months(
    db_session, monkeypatch
):
    versions = [
        PerformancePeriodVersion(period="2026-07", revision=2, status="open"),
        PerformancePeriodVersion(period="2026-08", revision=0, status="open"),
        PerformancePeriodVersion(period="2026-09", revision=4, status="frozen"),
    ]
    db_session.add_all(versions)
    db_session.add(PerformanceSettlement(period="2026-10", status=SettlementStatus.REVIEWED))
    await db_session.flush()

    original_lock = performance_period_service.lock_period
    lock_order = []

    async def record_lock(db, period):
        lock_order.append(period)
        return await original_lock(db, period)

    monkeypatch.setattr(performance_period_service, "lock_period", record_lock)
    changed = await performance_period_service.bump_unfrozen_periods(
        db_session, ["2026-10", "2026-09", "2026-08", "2026-07", "2026-08"]
    )

    assert lock_order == ["2026-07", "2026-08", "2026-09", "2026-10"]
    assert changed == {"2026-07", "2026-08"}
    assert (await _period_version(db_session, "2026-07")).revision == 3
    assert (await _period_version(db_session, "2026-08")).revision == 1
    assert (await _period_version(db_session, "2026-09")).revision == 4
    reviewed = await _period_version(db_session, "2026-10")
    assert reviewed.revision == 0
    assert reviewed.status == "frozen"


@pytest.mark.asyncio
async def test_sync_bill_insert_update_and_replay_bump_only_changed_open_period(
    db_session,
):
    from src.models.binding import Customer
    from src.services.sync_service import SyncService

    context = await performance_context(db_session)
    customer = await db_session.get(Customer, context["customerId"])
    customer.rutai_user_id = "rutai-dirty-period-user"
    await db_session.flush()
    service = SyncService()
    item = {
        "transaction_id": "dirty-period-rutai-bill",
        "transaction_time": "2026-07-15T12:00:00Z",
        "transaction_status": "paid",
        "paid_amount_cent": 10000,
        "total_amount_cent": 10000,
    }

    assert await service._process_bill(db_session, customer.rutai_user_id, item) == "created"
    assert (await _period_version(db_session, "2026-07")).revision == 1
    assert await service._process_bill(db_session, customer.rutai_user_id, item) == "skipped"
    assert (await _period_version(db_session, "2026-07")).revision == 1

    refunded = {
        **item,
        "transaction_status": "partially_refunded",
        "refund_amount_cent": 2000,
    }
    assert (
        await service._process_bill(db_session, customer.rutai_user_id, refunded)
        == "refund_processed"
    )
    assert (await _period_version(db_session, "2026-07")).revision == 2
    assert await service._process_bill(db_session, customer.rutai_user_id, refunded) == "skipped"
    assert (await _period_version(db_session, "2026-07")).revision == 2


@pytest.mark.asyncio
async def test_manual_consumption_bumps_period_once_and_rejects_reviewed_month(db_session):
    admin_id = await seed_admin(db_session, username="period-reviewer")
    seeded = await seed_bound_customer_with_attribution(db_session)
    from src.schemas.admin_contribution import ManualConsumptionCreateRequest
    from src.services.manual_consumption_service import create_manual_consumption

    data = ManualConsumptionCreateRequest(
        customerId=str(seeded["customer"].id),
        customerVersion=seeded["customer"].version,
        consumedAt=datetime(2026, 7, 15, 12, tzinfo=timezone.utc),
        amountCent=12000,
        note="核对后的手工消费",
    )
    first = await create_manual_consumption(
        db_session,
        data=data,
        admin_id=admin_id,
        admin_username="period-reviewer",
        idempotency_key="dirty-manual-period-001",
    )
    replay = await create_manual_consumption(
        db_session,
        data=data,
        admin_id=admin_id,
        admin_username="period-reviewer",
        idempotency_key="dirty-manual-period-001",
    )
    assert replay["id"] == first["id"]
    assert (await _period_version(db_session, "2026-07")).revision == 1

    db_session.add(PerformanceSettlement(period="2026-08", status=SettlementStatus.REVIEWED))
    await db_session.flush()
    frozen_input = data.model_copy(
        update={"consumed_at": datetime(2026, 8, 15, 12, tzinfo=timezone.utc)}
    )
    with pytest.raises(ConflictException):
        await create_manual_consumption(
            db_session,
            data=frozen_input,
            admin_id=admin_id,
            admin_username="period-reviewer",
            idempotency_key="dirty-manual-period-frozen",
        )
    assert await _period_version(db_session, "2026-08") is None


@pytest.mark.asyncio
async def test_rule_and_personal_override_changes_mark_source_months_without_recomputing(
    db_session,
):
    context = await performance_context(db_session)
    await add_bill(db_session, context, 800000, datetime(2026, 7, 10))
    await add_mall_source(db_session, context, 300000, datetime(2026, 8, 10))
    old_result = CommissionResult(
        period="2026-07",
        distributor_id=context["distributorId"],
        org_id=context["orgId"],
        rule_type=RuleType.INTRA_ORG,
        base_cent=800000,
        ratio="0.05",
        commission_cent=40000,
    )
    db_session.add(old_result)
    await db_session.flush()
    rule = PerformanceRuleUpdateRequest(tiers=[Tier(minCent=0, maxCent=None, ratio=0.08)])

    await performance_service.save_rule(
        db_session, context["orgId"], "intra_org", rule, operator_id=1
    )
    assert (await _period_version(db_session, "2026-07")).revision == 1
    assert (await _period_version(db_session, "2026-08")).revision == 1
    assert old_result.base_cent == 800000 and old_result.commission_cent == 40000

    personal = PersonalPerformanceRuleUpdateRequest(
        tiers=[Tier(minCent=0, maxCent=None, ratio=0.12)]
    )
    await performance_service.save_personal_rule(
        db_session, context["distributorId"], personal, operator_id=1
    )
    assert (await _period_version(db_session, "2026-07")).revision == 2
    assert (await _period_version(db_session, "2026-08")).revision == 2

    await performance_service.clear_personal_rule(db_session, context["distributorId"])
    assert (await _period_version(db_session, "2026-07")).revision == 3
    assert (await _period_version(db_session, "2026-08")).revision == 3
    assert old_result.base_cent == 800000 and old_result.commission_cent == 40000


@pytest.mark.asyncio
async def test_distributor_move_marks_its_source_month_before_changing_org(db_session):
    from src.models.organization import Organization
    from src.schemas.distributor import DistributorUpdate

    context = await performance_context(db_session)
    await add_bill(db_session, context, 100000, datetime(2026, 7, 10))
    new_org = Organization(name="绩效迁移目标", org_type="region", level=1, sort_order=0)
    db_session.add(new_org)
    await db_session.flush()

    result = await distributor_service.update_distributor(
        db_session,
        context["distributorId"],
        DistributorUpdate(orgId=new_org.id),
        operator_id=1,
    )
    assert result["orgId"] == str(new_org.id)
    assert (await _period_version(db_session, "2026-07")).revision == 1


@pytest.mark.asyncio
async def test_org_branch_move_marks_open_affected_months(db_session):
    context = await performance_context(db_session)
    await add_bill(db_session, context, 100000, datetime(2026, 7, 10))
    new_parent = await organization_service.create_org(
        db_session, OrgCreate(name="绩效迁移父组织", orgType="region")
    )

    await organization_service.migrate_branch(
        db_session,
        context["orgId"],
        OrgMigrateRequest(newParentId=new_parent.id),
        operator_id=1,
    )
    assert (await _period_version(db_session, "2026-07")).revision == 1


@pytest.mark.asyncio
async def test_personnel_and_org_status_changes_mark_only_open_sources(db_session):
    context = await performance_context(db_session)
    await add_bill(db_session, context, 100000, datetime(2026, 7, 10))
    await add_bill(db_session, context, 50000, datetime(2026, 8, 10))
    db_session.add(PerformanceSettlement(period="2026-08", status=SettlementStatus.REVIEWED))
    await db_session.flush()

    await distributor_service.update_distributor(
        db_session,
        context["distributorId"],
        DistributorUpdate(status="disabled"),
        operator_id=1,
    )
    assert (await _period_version(db_session, "2026-07")).revision == 1
    assert (await _period_version(db_session, "2026-08")).status == "frozen"

    await distributor_service.set_role(
        db_session,
        context["distributorId"],
        DistributorRoleUpdate(orgRole="admin"),
        operator_id=1,
    )
    await organization_service.update_org(
        db_session,
        context["orgId"],
        OrgUpdate(status="disabled"),
        operator_id=1,
    )
    assert (await _period_version(db_session, "2026-07")).revision == 3
    assert (await _period_version(db_session, "2026-08")).revision == 0
