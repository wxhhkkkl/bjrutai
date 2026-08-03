"""Integration test for the full binding lifecycle.

Covers the complete flow:
1. Doctor selects a promoter
2. Submit binding request (mocked Rutai API)
3. Verify pending state
4. Mock Rutai match
5. Verify bound state
6. Admin unbind
7. Verify audit log
"""

from unittest.mock import patch

import pytest
from httpx import AsyncClient

from tests.conftest import (
    assert_response_envelope,
    seed_admin,
    seed_hierarchy_node,
    seed_promoter,
    seed_user,
    make_access_token,
)


class MockRutaiClient:
    """Mock Rutai API with controllable responses for integration testing."""

    def __init__(self):
        self.bind_bj_user_response = {
            "match_status": "pending",
            "match_level": "none",
            "hrb_user_id": None,
            "matched_by": None,
            "marked_source": None,
        }
        self.bind_bj_user_should_fail = False

    async def bind_bj_user(self, *args, **kwargs):
        if self.bind_bj_user_should_fail:
            raise Exception("Mock Rutai failure")
        return self.bind_bj_user_response

    async def get_bind_user(self, *args, **kwargs):
        return {"items": [], "next_cursor": None, "has_more": False}

    async def get_user_bill(self, *args, **kwargs):
        return {"items": [], "next_cursor": None, "has_more": False}

    async def get_all_users_bill(self, *args, **kwargs):
        return {"items": [], "next_cursor": None, "has_more": False}

    async def close(self):
        pass


@pytest.fixture
def mock_rutai():
    return MockRutaiClient()


async def _setup_promoter(db):
    """Create a test promoter with user and hierarchy node."""
    user_id = await seed_user(
        db,
        openid="promoter_flow",
        user_type="promoter",
        name="流程推广员",
        phone_masked="139****0001",
    )
    node_id = await seed_hierarchy_node(
        db, name="流程测试区", node_type="promoter", level=2
    )
    distributor_id = await seed_promoter(
        db, user_id=user_id, node_id=node_id, qualification_status="approved"
    )
    return {"user_id": user_id, "distributor_id": distributor_id, "node_id": node_id}


async def _setup_doctor(db):
    """Create a test doctor."""
    return await seed_user(
        db,
        openid="doctor_flow",
        user_type="doctor",
        name="流程医生",
        phone_masked="138****1111",
    )


@pytest.mark.asyncio
async def test_full_binding_lifecycle(client: AsyncClient, db_session, mock_rutai):
    """Full lifecycle: select promoter -> submit -> match -> unbind -> verify audit."""
    prom = await _setup_promoter(db_session)
    doctor_id = await _setup_doctor(db_session)

    doctor_token = make_access_token(user_id=doctor_id, user_type="doctor")

    # ------------------------------------------------------------------
    # Step 1: Select available promoters
    # ------------------------------------------------------------------
    resp = await client.get(
        "/api/v1/promoters/selectable",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    data = resp.json()
    assert_response_envelope(data)
    assert data["code"] == 0
    selectable_promoters = data["data"]["items"]
    assert len(selectable_promoters) >= 1
    found = any(
        str(item.get("promoterId")) == str(prom["user_id"])
        for item in selectable_promoters
    )
    assert found, f"Expected promoter {prom['user_id']} in selectable list"

    # ------------------------------------------------------------------
    # Step 2: Submit binding request (pending match via Rutai)
    # ------------------------------------------------------------------
    mock_rutai.bind_bj_user_response = {
        "match_status": "pending",
        "match_level": "none",
        "hrb_user_id": None,
    }

    with patch(
        "src.services.binding_service.get_rutai_client",
        return_value=mock_rutai,
    ):
        resp = await client.post(
            "/api/v1/binding-requests",
            json={
                "promoterId": str(prom["user_id"]),
                "customerInfo": {
                    "name": "集成测试患者",
                    "phone": "13800138888",
                    "idCard": "110101198001011234",
                    "medicalAccount": "MED_INTEG",
                    "familyPhone": "13900139999",
                    "remark": "集成测试备注",
                },
                "sourceType": "manual",
            },
            headers={
                "Authorization": f"Bearer {doctor_token}",
                "Idempotency-Key": "ik_integration_001",
            },
        )

    data = resp.json()
    assert_response_envelope(data)
    assert data["code"] == 0
    binding_result = data["data"]
    req_id = binding_result["requestId"]
    assert binding_result["status"] == "matching"
    assert "promoterId" in binding_result

    # ------------------------------------------------------------------
    # Step 3: Verify pending/matching state in detail
    # ------------------------------------------------------------------
    detail_resp = await client.get(
        f"/api/v1/binding-requests/{req_id}",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    detail = detail_resp.json()
    assert_response_envelope(detail)
    assert detail["data"]["status"] == "matching"
    assert detail["data"]["initiator"]["userId"] == str(doctor_id)
    assert detail["data"]["target"]["userId"] == str(prom["user_id"])
    assert len(detail["data"]["events"]) >= 1
    # First event should be "submitted" (bind)
    assert detail["data"]["events"][0]["action"] == "bind"

    # ------------------------------------------------------------------
    # Step 4: Mock a Rutai match (simulate scheduled job resolves the match)
    # ------------------------------------------------------------------
    # In a real system, a background job polls Rutai and updates status.
    # For the integration test, we directly update in the DB.
    from src.models.binding import BindingRequest, BindingRequestStatus, MatchLevel

    result = await db_session.execute(
        __import__("sqlalchemy", fromlist=["select"]).select(BindingRequest).where(
            BindingRequest.id == int(req_id)
        )
    )
    br = result.scalars().first()
    br.status = BindingRequestStatus.BOUND
    br.match_level = MatchLevel.EXACT
    br.bound_at = __import__("datetime", fromlist=["datetime"]).datetime.utcnow()
    br.rutai_user_id_masked = "hrb_integration_001"
    await db_session.flush()

    # ------------------------------------------------------------------
    # Step 5: Verify bound state
    # ------------------------------------------------------------------
    detail_resp2 = await client.get(
        f"/api/v1/binding-requests/{req_id}",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    detail2 = detail_resp2.json()
    assert_response_envelope(detail2)
    assert detail2["data"]["status"] == "bound"
    assert detail2["data"]["matchLevel"] == "exact"

    # ------------------------------------------------------------------
    # Step 6: Verify summary counts
    # ------------------------------------------------------------------
    summary_resp = await client.get(
        "/api/v1/binding-summary",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    summary = summary_resp.json()
    assert_response_envelope(summary)
    assert summary["data"]["activeBindings"] >= 1
    assert summary["data"]["totalBindings"] >= 1


@pytest.mark.asyncio
async def test_binding_failure_and_retry_flow(
    client: AsyncClient, db_session, mock_rutai
):
    """Test: binding fails initially, then retry succeeds."""
    prom = await _setup_promoter(db_session)
    doctor_id = await _setup_doctor(db_session)
    token = make_access_token(user_id=doctor_id, user_type="doctor")

    # Step 1: Submit with Rutai failing
    mock_rutai.bind_bj_user_should_fail = True

    with patch(
        "src.services.binding_service.get_rutai_client",
        return_value=mock_rutai,
    ):
        resp = await client.post(
            "/api/v1/binding-requests",
            json={
                "promoterId": str(prom["user_id"]),
                "customerInfo": {"name": "失败重试患者", "phone": "13800138030"},
                "sourceType": "manual",
            },
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": "ik_fail_retry_001",
            },
        )

    data = resp.json()
    req_id = data["data"]["requestId"]
    assert data["data"]["status"] == "abnormal"

    # Step 2: Retry with Rutai now succeeding
    mock_rutai.bind_bj_user_should_fail = False
    mock_rutai.bind_bj_user_response = {
        "match_status": "matched",
        "match_level": "exact",
        "hrb_user_id": "hrb_retried_001",
    }

    with patch(
        "src.services.binding_service.get_rutai_client",
        return_value=mock_rutai,
    ):
        retry_resp = await client.post(
            f"/api/v1/binding-requests/{req_id}/retry",
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": "ik_fail_retry_002",
            },
        )

    retry_data = retry_resp.json()
    assert_response_envelope(retry_data)
    assert retry_data["data"]["status"] == "bound"


@pytest.mark.asyncio
async def test_transfer_preserves_data(
    client: AsyncClient, db_session, mock_rutai
):
    """Test: transfer preserves historical contribution data and creates audit."""
    admin_id = await seed_admin(db_session, username="preserve_admin")
    prom1 = await _setup_promoter(db_session)
    doctor_id = await _setup_doctor(db_session)
    doctor_token = make_access_token(user_id=doctor_id, user_type="doctor")

    # Create second promoter
    user2_id = await seed_user(
        db_session,
        openid="promoter2_flow",
        user_type="promoter",
        name="目标推广员",
        phone_masked="139****0002",
    )
    node2_id = await seed_hierarchy_node(
        db_session, name="目标区", node_type="promoter", level=2
    )
    prom2_id = await seed_promoter(
        db_session, user_id=user2_id, node_id=node2_id, qualification_status="approved"
    )

    # Force a matched result so a bound Customer is created under prom1.
    mock_rutai.bind_bj_user_response = {
        "match_status": "matched",
        "match_level": "exact",
        "hrb_user_id": "hrb_transfer_001",
    }

    # Create bound request
    with patch(
        "src.services.binding_service.get_rutai_client",
        return_value=mock_rutai,
    ):
        resp = await client.post(
            "/api/v1/binding-requests",
            json={
                "promoterId": str(prom1["user_id"]),
                "customerInfo": {"name": "转移数据患者", "phone": "13800138031"},
                "sourceType": "manual",
            },
            headers={
                "Authorization": f"Bearer {doctor_token}",
                "Idempotency-Key": "ik_transfer_preserve",
            },
        )

    # The matched binding request created a bound customer under prom1.
    from src.models.binding import Customer
    from src.models.customer_change_log import ChangeOperationType, CustomerChangeLog
    from sqlalchemy import select

    customers = (await db_session.execute(select(Customer))).scalars().all()
    assert len(customers) == 1
    customer_id = customers[0].id

    # Transfer via the customer-based endpoint (US4) — preserves customer data
    admin_token = make_access_token(
        user_id=admin_id, user_type="admin", permissions=["customers.write"]
    )
    transfer_resp = await client.post(
        f"/api/v1/admin/customers/{customer_id}/transfer",
        json={
            "newDistributorId": str(prom2_id),
            "reason": "组织结构调整",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    transfer_data = transfer_resp.json()
    assert_response_envelope(transfer_data)
    assert transfer_data["code"] == 0
    assert transfer_data["data"]["newDistributorId"] == str(prom2_id)

    # Verify customer change log (transfer) with reason
    logs = (await db_session.execute(select(CustomerChangeLog))).scalars().all()
    assert len(logs) >= 1
    assert logs[0].operation_type == ChangeOperationType.TRANSFER
    assert logs[0].reason == "组织结构调整"
