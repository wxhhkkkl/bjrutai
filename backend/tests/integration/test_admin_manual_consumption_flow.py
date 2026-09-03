"""End-to-end business flow for manual consumption and dashboard attribution."""

from datetime import datetime, timezone

import pytest

from src.models.distributor import Distributor, OrgRole
from src.schemas.admin_contribution import ManualConsumptionCreateRequest
from src.services.contribution_dashboard_service import get_dashboard, org_ranking, persons_ranking
from src.services.manual_consumption_service import create_manual_consumption
from tests.conftest import seed_admin, seed_bound_customer_with_attribution, seed_user


@pytest.mark.asyncio
async def test_manual_entry_updates_dashboard_and_retains_original_attribution(db_session):
    admin_id = await seed_admin(db_session)
    seeded = await seed_bound_customer_with_attribution(
        db_session,
        person_name="原归属人",
        customer_name="消费客户",
    )
    consumed_at = datetime(2026, 9, 2, 8, 30, tzinfo=timezone.utc)
    await create_manual_consumption(
        db_session,
        data=ManualConsumptionCreateRequest(
            customerId=str(seeded["customer"].id),
            customerVersion=seeded["customer"].version,
            consumedAt=consumed_at,
            amountCent=12880,
            note="集成测试",
        ),
        admin_id=admin_id,
        admin_username="admin",
        idempotency_key="integration-flow",
    )

    dashboard = await get_dashboard(db_session, "2026-09")
    assert dashboard["stats"]["monthlyAmountCent"] == 12880
    assert dashboard["trend"][-1]["amountCent"] == 12880
    assert dashboard["latest"][0]["customerName"] == "消费客户"
    assert dashboard["latest"][0]["source"] == "manual"

    people = await persons_ranking(db_session, "2026-09")
    orgs = await org_ranking(db_session, "2026-09")
    assert people["items"][0]["name"] == "原归属人"
    assert people["items"][0]["amountCent"] == 12880
    assert orgs["items"][0]["orgId"] == str(seeded["org"].id)
    assert orgs["items"][0]["amountCent"] == 12880

    other_user_id = await seed_user(
        db_session,
        openid="openid-new-owner",
        user_type="distributor",
        name="新归属人",
    )
    other = Distributor(user_id=other_user_id, org_id=seeded["org"].id, org_role=OrgRole.MEMBER)
    db_session.add(other)
    await db_session.flush()
    seeded["customer"].distributor_id = other.id
    seeded["customer"].version += 1
    await db_session.flush()

    people_after_transfer = await persons_ranking(db_session, "2026-09")
    assert people_after_transfer["items"][0]["distributorId"] == str(seeded["distributor"].id)
    assert people_after_transfer["items"][0]["name"] == "原归属人"
    assert people_after_transfer["items"][0]["amountCent"] == 12880
