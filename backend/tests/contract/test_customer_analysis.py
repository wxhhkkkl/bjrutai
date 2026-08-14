"""Contract tests for the customer overview metrics."""

from datetime import datetime, timezone

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token
from src.models.binding import BindingStatus, Customer
from src.models.followup import (
    FollowupMethod,
    FollowupRecord,
    FollowupResult,
    ReminderStatus,
)
from tests.conftest import assert_response_envelope, seed_hierarchy_node, seed_promoter, seed_user


def _auth_headers(user_id: int) -> dict:
    token = create_access_token(data={"sub": str(user_id), "user_type": "promoter"})
    return {"Authorization": f"Bearer {token}"}


async def _seed_promoter(db: AsyncSession, *, openid: str) -> tuple[int, int]:
    node_id = await seed_hierarchy_node(
        db, name=f"节点-{openid}", node_type="promoter", level=5, parent_id=None
    )
    user_id = await seed_user(db, openid=openid, user_type="promoter", name=openid)
    distributor_id = await seed_promoter(db, user_id=user_id, node_id=node_id)
    return user_id, distributor_id


async def _seed_customer(
    db: AsyncSession, *, distributor_id: int, status: BindingStatus
) -> Customer:
    customer = Customer(distributor_id=distributor_id, binding_status=status, version=1)
    db.add(customer)
    await db.flush()
    return customer


async def test_customer_analysis_returns_real_status_and_followup_counts(
    client: AsyncClient, db_session: AsyncSession
):
    user_id, distributor_id = await _seed_promoter(db_session, openid="wx_analysis_owner")
    _other_user_id, other_distributor_id = await _seed_promoter(db_session, openid="wx_analysis_other")

    await _seed_customer(db_session, distributor_id=distributor_id, status=BindingStatus.BOUND)
    await _seed_customer(db_session, distributor_id=distributor_id, status=BindingStatus.PENDING)
    followup_customer = await _seed_customer(
        db_session, distributor_id=distributor_id, status=BindingStatus.BOUND
    )
    await _seed_customer(db_session, distributor_id=distributor_id, status=BindingStatus.UNBOUND)
    await _seed_customer(db_session, distributor_id=other_distributor_id, status=BindingStatus.BOUND)

    # Two active reminders for one customer must be counted as one customer.
    for _ in range(2):
        db_session.add(FollowupRecord(
            customer_id=followup_customer.id,
            doctor_id=user_id,
            method=FollowupMethod.PHONE,
            result=FollowupResult.PENDING,
            reminder_enabled=True,
            reminder_at=datetime.now(timezone.utc),
            reminder_status=ReminderStatus.PENDING,
        ))
    await db_session.flush()

    response = await client.get("/api/v1/customer-analysis?period=30d", headers=_auth_headers(user_id))
    assert response.status_code == 200
    body = response.json()
    assert_response_envelope(body)
    assert body["data"]["overview"] == {
        "totalCustomers": 4,
        "boundCustomers": 2,
        "pendingCustomers": 1,
        "unboundCustomers": 1,
        "followupCustomers": 1,
        "newCustomers": 4,
    }

    followup_response = await client.get(
        "/api/v1/customers",
        params={"status": "followup"},
        headers=_auth_headers(user_id),
    )
    assert followup_response.status_code == 200
    followup_body = followup_response.json()
    assert_response_envelope(followup_body)
    assert [item["id"] for item in followup_body["data"]["items"]] == [str(followup_customer.id)]
    assert followup_body["data"]["items"][0]["bindingStatus"] == "bound"
    assert followup_body["data"]["items"][0]["hasPendingFollowup"] is True


async def test_bound_customer_can_only_update_name(
    client: AsyncClient, db_session: AsyncSession
):
    user_id, distributor_id = await _seed_promoter(db_session, openid="wx_bound_edit_owner")
    customer = await _seed_customer(
        db_session, distributor_id=distributor_id, status=BindingStatus.BOUND
    )

    blocked = await client.patch(
        f"/api/v1/customers/{customer.id}",
        json={"name": "新姓名", "note": "不允许修改"},
        headers=_auth_headers(user_id),
    )
    assert blocked.status_code == 400
    assert blocked.json()["code"] == 40000
    assert blocked.json()["message"] == "客户绑定后仅允许修改姓名"

    allowed = await client.patch(
        f"/api/v1/customers/{customer.id}",
        json={"name": "新姓名"},
        headers=_auth_headers(user_id),
    )
    assert allowed.status_code == 200
    assert allowed.json()["data"]["name"] == "新姓名"
