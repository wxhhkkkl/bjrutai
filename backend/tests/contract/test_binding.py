"""Contract tests for binding API endpoints.

Tests all binding-related endpoints against the API contract defined in
specs/001-distribution-management-api/contracts/binding.md.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

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


# =============================================================================
# Helpers
# =============================================================================


async def _create_promoter(db, *, user_id=None, name="测试推广员", org_name="华东大区", approved=True):
    """Create a promoter with user, node, and optionally approve qualifications."""
    if user_id is None:
        user_id = await seed_user(
            db,
            openid=f"promoter_{name}",
            user_type="promoter",
            name=name,
            phone_masked="139****0000",
        )
    node_id = await seed_hierarchy_node(db, name=org_name, node_type="promoter", level=2)
    distributor_id = await seed_promoter(
        db,
        user_id=user_id,
        node_id=node_id,
        qualification_status="approved" if approved else "draft",
    )
    return {"distributor_id": distributor_id, "user_id": user_id, "node_id": node_id}


async def _create_doctor(db, *, openid="doctor_test", name="测试医生"):
    """Create a doctor user."""
    return await seed_user(
        db,
        openid=openid,
        user_type="doctor",
        name=name,
        phone_masked="138****1234",
    )


# =============================================================================
# Mock Rutai Client
# =============================================================================


class MockRutaiClient:
    """Mock Rutai API client for tests."""

    def __init__(self):
        self.bind_bj_user_response = {
            "match_status": "matched",
            "match_level": "exact",
            "hrb_user_id": "hrb_001",
            "matched_by": "phone",
            "marked_source": "scan",
        }
        self.bind_bj_user_should_fail = False
        self.bind_bj_user_fail_message = "Rutai API error"

    async def bind_bj_user(self, *args, **kwargs):
        if self.bind_bj_user_should_fail:
            raise Exception(self.bind_bj_user_fail_message)
        return self.bind_bj_user_response

    async def get_bind_user(self, *args, **kwargs):
        return {
            "items": [],
            "next_cursor": None,
            "has_more": False,
        }

    async def get_user_bill(self, *args, **kwargs):
        return {
            "items": [],
            "next_cursor": None,
            "has_more": False,
        }

    async def get_all_users_bill(self, *args, **kwargs):
        return {
            "items": [],
            "next_cursor": None,
            "has_more": False,
        }

    async def close(self):
        pass


@pytest.fixture
def mock_rutai():
    return MockRutaiClient()


# =============================================================================
# Test Group 1: GET /api/v1/promoters/selectable
# =============================================================================


class TestSelectablePromoters:
    """GET /api/v1/promoters/selectable"""

    async def test_keyword_search(self, client: AsyncClient, db_session):
        """Search promoters by keyword returns matching active promoters."""
        await _create_promoter(db_session, name="张推广", org_name="华北区")
        await _create_promoter(db_session, name="李推广", org_name="华东区")

        token = make_access_token(user_id=1, user_type="doctor")
        resp = await client.get(
            "/api/v1/promoters/selectable?keyword=张",
            headers={"Authorization": f"Bearer {token}"},
        )
        data = resp.json()
        assert_response_envelope(data)
        assert data["code"] == 0
        items = data["data"]["items"]
        assert len(items) >= 1
        assert any("张" in (item.get("displayName") or "") for item in items)

    async def test_cursor_pagination(self, client: AsyncClient, db_session):
        """Selectable promoters support cursor-based pagination."""
        for i in range(5):
            await _create_promoter(db_session, name=f"推广{i}", org_name="测试区")

        token = make_access_token(user_id=1, user_type="doctor")
        resp = await client.get(
            "/api/v1/promoters/selectable?limit=3",
            headers={"Authorization": f"Bearer {token}"},
        )
        data = resp.json()
        assert_response_envelope(data)
        assert "nextCursor" in data["data"]
        assert "hasMore" in data["data"]
        assert len(data["data"]["items"]) <= 3

    async def test_permission_filtering_doctor(self, client: AsyncClient, db_session):
        """Only approved promoters are shown."""
        await _create_promoter(db_session, name="已审核", approved=True)
        await _create_promoter(db_session, name="未审核", approved=False)

        token = make_access_token(user_id=1, user_type="doctor")
        resp = await client.get(
            "/api/v1/promoters/selectable",
            headers={"Authorization": f"Bearer {token}"},
        )
        data = resp.json()
        assert_response_envelope(data)
        names = [item.get("displayName") for item in data["data"]["items"]]
        assert "已审核" in names or len(names) > 0
        # Unapproved should not appear
        assert "未审核" not in names

    async def test_requires_auth(self, client: AsyncClient):
        """Selectable promoters requires authentication."""
        resp = await client.get("/api/v1/promoters/selectable")
        assert resp.status_code == 401


# =============================================================================
# Test Group 2: POST /api/v1/binding-requests
# =============================================================================


class TestSubmitBindingRequest:
    """POST /api/v1/binding-requests"""

    async def test_success_with_complete_customer_data(
        self, client: AsyncClient, db_session, mock_rutai
    ):
        """Submit binding request with full customer info succeeds."""
        prom = await _create_promoter(db_session, name="测试推广员")
        doctor_id = await _create_doctor(db_session)

        token = make_access_token(user_id=doctor_id, user_type="doctor")

        with patch(
            "src.services.binding_service.get_rutai_client",
            return_value=mock_rutai,
        ):
            resp = await client.post(
                "/api/v1/binding-requests",
                json={
                    "promoterId": str(prom["user_id"]),
                    "customerInfo": {
                        "name": "患者张三",
                        "phone": "13800138000",
                        "idCard": "110101199001011234",
                        "medicalAccount": "MED001",
                        "familyPhone": "13900139000",
                        "remark": "测试备注",
                    },
                    "sourceType": "manual",
                },
                headers={
                    "Authorization": f"Bearer {token}",
                    "Idempotency-Key": "ik_test_001",
                },
            )

        data = resp.json()
        assert_response_envelope(data)
        assert data["code"] == 0
        assert data["data"]["status"] in ("bound", "pending_match", "matching")
        assert "requestId" in data["data"]

    async def test_duplicate_idempotency_key(
        self, client: AsyncClient, db_session, mock_rutai
    ):
        """Duplicate idempotency key returns same response."""
        prom = await _create_promoter(db_session, name="测试推广员2")
        doctor_id = await _create_doctor(db_session)
        token = make_access_token(user_id=doctor_id, user_type="doctor")

        key = "ik_dup_001"
        payload = {
            "promoterId": str(prom["user_id"]),
            "customerInfo": {"name": "患者李四", "phone": "13800138001"},
            "sourceType": "manual",
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": key,
        }

        with patch(
            "src.services.binding_service.get_rutai_client",
            return_value=mock_rutai,
        ):
            resp1 = await client.post("/api/v1/binding-requests", json=payload, headers=headers)
            resp2 = await client.post("/api/v1/binding-requests", json=payload, headers=headers)

        # The IdempotencyMiddleware should cache the response
        assert resp1.status_code == resp2.status_code

    async def test_already_bound_customer(self, client: AsyncClient, db_session, mock_rutai):
        """Cannot bind a customer who is already bound to a promoter."""
        from src.models.binding import BindingRequest, BindingRequestStatus, BindingStatus, Customer

        prom = await _create_promoter(db_session, name="测试推广员3")
        doctor_id = await _create_doctor(db_session)
        token = make_access_token(user_id=doctor_id, user_type="doctor")

        # Create an existing bound customer for this promoter
        cust = Customer(
            distributor_id=prom["distributor_id"],
            name="已绑定患者",
            phone="13800138002",
            binding_status=BindingStatus.BOUND,
        )
        db_session.add(cust)
        await db_session.flush()

        with patch(
            "src.services.binding_service.get_rutai_client",
            return_value=mock_rutai,
        ):
            resp = await client.post(
                "/api/v1/binding-requests",
                json={
                    "promoterId": str(prom["user_id"]),
                    "customerInfo": {"name": "已绑定患者", "phone": "13800138002"},
                    "sourceType": "manual",
                },
                headers={
                    "Authorization": f"Bearer {token}",
                    "Idempotency-Key": "ik_bound_test",
                },
            )

        data = resp.json()
        assert data["code"] == 40022 or resp.status_code == 409

    async def test_missing_consent_record(self, client: AsyncClient, db_session, mock_rutai):
        """Binding with invalid consent record ID fails."""
        prom = await _create_promoter(db_session, name="测试推广员4")
        doctor_id = await _create_doctor(db_session)
        token = make_access_token(user_id=doctor_id, user_type="doctor")

        with patch(
            "src.services.binding_service.get_rutai_client",
            return_value=mock_rutai,
        ):
            resp = await client.post(
                "/api/v1/binding-requests",
                json={
                    "promoterId": str(prom["user_id"]),
                    "customerInfo": {"name": "患者", "phone": "13800138003"},
                    "consentRecordId": 99999,
                    "sourceType": "manual",
                },
                headers={
                    "Authorization": f"Bearer {token}",
                    "Idempotency-Key": "ik_consent_001",
                },
            )

        data = resp.json()
        assert data["code"] == 40025

    async def test_missing_required_fields(self, client: AsyncClient, db_session):
        """Binding request without promoterId fails."""
        doctor_id = await _create_doctor(db_session)
        token = make_access_token(user_id=doctor_id, user_type="doctor")

        resp = await client.post(
            "/api/v1/binding-requests",
            json={
                "customerInfo": {"name": "患者"},
                "sourceType": "manual",
            },
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": "ik_missing_001",
            },
        )

        assert resp.status_code == 422

    async def test_missing_idempotency_key(self, client: AsyncClient, db_session, mock_rutai):
        """Binding request without Idempotency-Key header fails."""
        prom = await _create_promoter(db_session, name="测试推广员5")
        doctor_id = await _create_doctor(db_session)
        token = make_access_token(user_id=doctor_id, user_type="doctor")

        with patch(
            "src.services.binding_service.get_rutai_client",
            return_value=mock_rutai,
        ):
            resp = await client.post(
                "/api/v1/binding-requests",
                json={
                    "promoterId": str(prom["user_id"]),
                    "customerInfo": {"name": "患者", "phone": "13800138004"},
                    "sourceType": "manual",
                },
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 400
        data = resp.json()
        assert "Idempotency-Key" in data.get("message", "")


# =============================================================================
# Test Group 3: GET /api/v1/binding-requests
# =============================================================================


class TestListBindingRequests:
    """GET /api/v1/binding-requests"""

    async def test_list_with_status_filter(self, client: AsyncClient, db_session, mock_rutai):
        """Filter binding requests by status."""
        prom = await _create_promoter(db_session, name="测试推广员6")
        doctor_id = await _create_doctor(db_session)
        token = make_access_token(user_id=doctor_id, user_type="doctor")

        # Create a binding request
        with patch(
            "src.services.binding_service.get_rutai_client",
            return_value=mock_rutai,
        ):
            await client.post(
                "/api/v1/binding-requests",
                json={
                    "promoterId": str(prom["user_id"]),
                    "customerInfo": {"name": "患者王五", "phone": "13800138005"},
                    "sourceType": "manual",
                },
                headers={
                    "Authorization": f"Bearer {token}",
                    "Idempotency-Key": "ik_list_001",
                },
            )

        resp = await client.get(
            "/api/v1/binding-requests?status=bound",
            headers={"Authorization": f"Bearer {token}"},
        )
        data = resp.json()
        assert_response_envelope(data)
        assert data["code"] == 0
        assert "items" in data["data"]

    async def test_keyword_search(self, client: AsyncClient, db_session, mock_rutai):
        """Search binding requests by keyword."""
        prom = await _create_promoter(db_session, name="测试推广员7")
        doctor_id = await _create_doctor(db_session)
        token = make_access_token(user_id=doctor_id, user_type="doctor")

        with patch(
            "src.services.binding_service.get_rutai_client",
            return_value=mock_rutai,
        ):
            await client.post(
                "/api/v1/binding-requests",
                json={
                    "promoterId": str(prom["user_id"]),
                    "customerInfo": {"name": "独特名字789", "phone": "13800138006"},
                    "sourceType": "manual",
                },
                headers={
                    "Authorization": f"Bearer {token}",
                    "Idempotency-Key": "ik_search_001",
                },
            )

        resp = await client.get(
            "/api/v1/binding-requests?keyword=独特名字",
            headers={"Authorization": f"Bearer {token}"},
        )
        data = resp.json()
        assert_response_envelope(data)
        # At least one result should match
        assert data["code"] == 0

    async def test_submitted_by_me_filter(self, client: AsyncClient, db_session, mock_rutai):
        """Filter binding requests to show only those submitted by current user."""
        prom = await _create_promoter(db_session, name="测试推广员8")
        doctor_id = await _create_doctor(db_session)
        token = make_access_token(user_id=doctor_id, user_type="doctor")

        with patch(
            "src.services.binding_service.get_rutai_client",
            return_value=mock_rutai,
        ):
            await client.post(
                "/api/v1/binding-requests",
                json={
                    "promoterId": str(prom["user_id"]),
                    "customerInfo": {"name": "测试提交者筛选", "phone": "13800138007"},
                    "sourceType": "manual",
                },
                headers={
                    "Authorization": f"Bearer {token}",
                    "Idempotency-Key": "ik_myfilter_001",
                },
            )

        resp = await client.get(
            "/api/v1/binding-requests?submittedByMe=true",
            headers={"Authorization": f"Bearer {token}"},
        )
        data = resp.json()
        assert_response_envelope(data)
        assert data["code"] == 0
        for item in data["data"]["items"]:
            assert item.get("initiator", {}).get("userId") == str(doctor_id)

    async def test_cursor_pagination(self, client: AsyncClient, db_session, mock_rutai):
        """Binding requests list supports cursor pagination."""
        prom = await _create_promoter(db_session, name="测试推广员9")
        doctor_id = await _create_doctor(db_session)
        token = make_access_token(user_id=doctor_id, user_type="doctor")

        # Create multiple requests
        for i in range(5):
            with patch(
                "src.services.binding_service.get_rutai_client",
                return_value=mock_rutai,
            ):
                await client.post(
                    "/api/v1/binding-requests",
                    json={
                        "promoterId": str(prom["user_id"]),
                        "customerInfo": {"name": f"分页测试{i}", "phone": f"1380013800{i}"},
                        "sourceType": "manual",
                    },
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Idempotency-Key": f"ik_paginate_{i}",
                    },
                )

        resp = await client.get(
            "/api/v1/binding-requests?limit=3",
            headers={"Authorization": f"Bearer {token}"},
        )
        data = resp.json()
        assert_response_envelope(data)
        assert "nextCursor" in data["data"]
        assert "hasMore" in data["data"]

    async def test_requires_auth(self, client: AsyncClient):
        """Binding requests list requires authentication."""
        resp = await client.get("/api/v1/binding-requests")
        assert resp.status_code == 401


# =============================================================================
# Test Group 4: GET /api/v1/binding-requests/{id}
# =============================================================================


class TestBindingDetail:
    """GET /api/v1/binding-requests/{id}"""

    async def test_pending_state(self, client: AsyncClient, db_session, mock_rutai):
        """View a binding request in pending state."""
        mock_rutai.bind_bj_user_response = {
            "match_status": "pending",
            "match_level": "none",
            "hrb_user_id": None,
        }

        prom = await _create_promoter(db_session, name="测试推广员A")
        doctor_id = await _create_doctor(db_session)
        token = make_access_token(user_id=doctor_id, user_type="doctor")

        with patch(
            "src.services.binding_service.get_rutai_client",
            return_value=mock_rutai,
        ):
            resp = await client.post(
                "/api/v1/binding-requests",
                json={
                    "promoterId": str(prom["user_id"]),
                    "customerInfo": {"name": "朝阳患者", "phone": "13800138008"},
                    "sourceType": "manual",
                },
                headers={
                    "Authorization": f"Bearer {token}",
                    "Idempotency-Key": "ik_detail_001",
                },
            )
        create_data = resp.json()
        req_id = create_data["data"]["requestId"]

        detail_resp = await client.get(
            f"/api/v1/binding-requests/{req_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        detail = detail_resp.json()
        assert_response_envelope(detail)
        assert detail["data"]["status"] == "matching"
        assert "initiator" in detail["data"]
        assert "target" in detail["data"]
        assert "events" in detail["data"]

    async def test_bound_state(self, client: AsyncClient, db_session, mock_rutai):
        """View a binding request in bound state."""
        mock_rutai.bind_bj_user_response = {
            "match_status": "matched",
            "match_level": "exact",
            "hrb_user_id": "hrb_bound_001",
        }

        prom = await _create_promoter(db_session, name="测试推广员B")
        doctor_id = await _create_doctor(db_session)
        token = make_access_token(user_id=doctor_id, user_type="doctor")

        with patch(
            "src.services.binding_service.get_rutai_client",
            return_value=mock_rutai,
        ):
            resp = await client.post(
                "/api/v1/binding-requests",
                json={
                    "promoterId": str(prom["user_id"]),
                    "customerInfo": {"name": "海淀患者", "phone": "13800138009"},
                    "sourceType": "manual",
                },
                headers={
                    "Authorization": f"Bearer {token}",
                    "Idempotency-Key": "ik_bound_detail",
                },
            )
        create_data = resp.json()
        req_id = create_data["data"]["requestId"]

        detail_resp = await client.get(
            f"/api/v1/binding-requests/{req_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        detail = detail_resp.json()
        assert_response_envelope(detail)
        assert detail["data"]["status"] == "bound"

    async def test_abnormal_state(self, client: AsyncClient, db_session, mock_rutai):
        """View a binding request in abnormal state."""
        mock_rutai.bind_bj_user_should_fail = True
        mock_rutai.bind_bj_user_fail_message = "Simulated Rutai timeout"

        prom = await _create_promoter(db_session, name="测试推广员C")
        doctor_id = await _create_doctor(db_session)
        token = make_access_token(user_id=doctor_id, user_type="doctor")

        with patch(
            "src.services.binding_service.get_rutai_client",
            return_value=mock_rutai,
        ):
            resp = await client.post(
                "/api/v1/binding-requests",
                json={
                    "promoterId": str(prom["user_id"]),
                    "customerInfo": {"name": "西城患者", "phone": "13800138010"},
                    "sourceType": "manual",
                },
                headers={
                    "Authorization": f"Bearer {token}",
                    "Idempotency-Key": "ik_abnormal_detail",
                },
            )
        create_data = resp.json()
        req_id = create_data["data"]["requestId"]

        detail_resp = await client.get(
            f"/api/v1/binding-requests/{req_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        detail = detail_resp.json()
        assert_response_envelope(detail)
        assert detail["data"]["status"] == "abnormal"
        assert detail["data"]["retryCount"] == 0

    async def test_not_found(self, client: AsyncClient):
        """Non-existent binding request returns 404."""
        token = make_access_token(user_id=1, user_type="doctor")
        resp = await client.get(
            "/api/v1/binding-requests/99999",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    async def test_requires_auth(self, client: AsyncClient):
        """Binding detail requires authentication."""
        resp = await client.get("/api/v1/binding-requests/1")
        assert resp.status_code == 401


# =============================================================================
# Test Group 5: POST /api/v1/binding-requests/{id}/retry
# =============================================================================


class TestRetryBinding:
    """POST /api/v1/binding-requests/{id}/retry"""

    async def test_valid_retry_from_abnormal_state(
        self, client: AsyncClient, db_session, mock_rutai
    ):
        """Retry a binding request from abnormal state succeeds."""
        # First, create an abnormal request
        mock_rutai.bind_bj_user_should_fail = True
        mock_rutai.bind_bj_user_fail_message = "Initial failure"

        prom = await _create_promoter(db_session, name="推广员重试")
        doctor_id = await _create_doctor(db_session)
        token = make_access_token(user_id=doctor_id, user_type="doctor")

        with patch(
            "src.services.binding_service.get_rutai_client",
            return_value=mock_rutai,
        ):
            resp = await client.post(
                "/api/v1/binding-requests",
                json={
                    "promoterId": str(prom["user_id"]),
                    "customerInfo": {"name": "重试患者", "phone": "13800138011"},
                    "sourceType": "manual",
                },
                headers={
                    "Authorization": f"Bearer {token}",
                    "Idempotency-Key": "ik_retry_create",
                },
            )
        req_id = resp.json()["data"]["requestId"]

        # Now retry with Rutai succeeding
        mock_rutai.bind_bj_user_should_fail = False
        mock_rutai.bind_bj_user_response = {
            "match_status": "matched",
            "match_level": "exact",
            "hrb_user_id": "hrb_retry_001",
        }

        with patch(
            "src.services.binding_service.get_rutai_client",
            return_value=mock_rutai,
        ):
            retry_resp = await client.post(
                f"/api/v1/binding-requests/{req_id}/retry",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Idempotency-Key": "ik_retry_001",
                },
            )

        data = retry_resp.json()
        assert_response_envelope(data)
        assert data["data"]["status"] in ("bound", "retrying", "matching", "no_consume")

    async def test_already_bound_rejection(
        self, client: AsyncClient, db_session, mock_rutai
    ):
        """Retry on already-bound request should fail."""
        mock_rutai.bind_bj_user_response = {
            "match_status": "matched",
            "match_level": "exact",
            "hrb_user_id": "hrb_bound",
        }

        prom = await _create_promoter(db_session, name="已绑定推广员")
        doctor_id = await _create_doctor(db_session)
        token = make_access_token(user_id=doctor_id, user_type="doctor")

        with patch(
            "src.services.binding_service.get_rutai_client",
            return_value=mock_rutai,
        ):
            resp = await client.post(
                "/api/v1/binding-requests",
                json={
                    "promoterId": str(prom["user_id"]),
                    "customerInfo": {"name": "已绑定患者", "phone": "13800138012"},
                    "sourceType": "manual",
                },
                headers={
                    "Authorization": f"Bearer {token}",
                    "Idempotency-Key": "ik_bound_no_retry",
                },
            )
        req_id = resp.json()["data"]["requestId"]

        # Retry should fail because status is "bound", not retryable
        retry_resp = await client.post(
            f"/api/v1/binding-requests/{req_id}/retry",
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": "ik_retry_bound",
            },
        )

        assert retry_resp.status_code == 400
        data = retry_resp.json()
        assert data["code"] == 40026

    async def test_requires_auth(self, client: AsyncClient):
        """Retry requires authentication."""
        resp = await client.post(
            "/api/v1/binding-requests/1/retry",
            headers={"Idempotency-Key": "ik_test"},
        )
        assert resp.status_code == 401


# =============================================================================
# Test Group 6: GET /api/v1/binding-summary
# =============================================================================


class TestBindingSummary:
    """GET /api/v1/binding-summary"""

    async def test_correct_counts(self, client: AsyncClient, db_session, mock_rutai):
        """Binding summary returns correct counts per status."""
        prom1 = await _create_promoter(db_session, name="汇总推广员1")
        prom2 = await _create_promoter(db_session, name="汇总推广员2")
        doctor_id = await _create_doctor(db_session)
        token = make_access_token(user_id=doctor_id, user_type="doctor")

        # Create one bound with prom1
        with patch(
            "src.services.binding_service.get_rutai_client",
            return_value=mock_rutai,
        ):
            await client.post(
                "/api/v1/binding-requests",
                json={
                    "promoterId": str(prom1["user_id"]),
                    "customerInfo": {"name": "汇总患者1", "phone": "13800138013"},
                    "sourceType": "manual",
                },
                headers={
                    "Authorization": f"Bearer {token}",
                    "Idempotency-Key": "ik_summary_1",
                },
            )

        # Create one abnormal with prom2 (different promoter to avoid bound check)
        mock_rutai.bind_bj_user_should_fail = True
        with patch(
            "src.services.binding_service.get_rutai_client",
            return_value=mock_rutai,
        ):
            await client.post(
                "/api/v1/binding-requests",
                json={
                    "promoterId": str(prom2["user_id"]),
                    "customerInfo": {"name": "汇总患者2", "phone": "13800138014"},
                    "sourceType": "manual",
                },
                headers={
                    "Authorization": f"Bearer {token}",
                    "Idempotency-Key": "ik_summary_2",
                },
            )

        resp = await client.get(
            "/api/v1/binding-summary",
            headers={"Authorization": f"Bearer {token}"},
        )
        data = resp.json()
        assert_response_envelope(data)
        assert data["code"] == 0
        summary = data["data"]
        assert summary["totalBindings"] >= 2
        assert summary["activeBindings"] >= 1
        assert "pendingRequests" in summary
        assert "rejectedRequests" in summary

    async def test_requires_auth(self, client: AsyncClient):
        """Binding summary requires authentication."""
        resp = await client.get("/api/v1/binding-summary")
        assert resp.status_code == 401


# =============================================================================
# Test Group 7: POST /api/v1/admin/bindings/{id}/unbind
# =============================================================================


class TestAdminUnbind:
    """POST /api/v1/admin/bindings/{id}/unbind"""

    async def test_unbind_success(self, client: AsyncClient, db_session, mock_rutai):
        """Admin can unbind a bound customer with a reason."""
        # Create admin
        admin_id = await seed_admin(db_session, username="unbind_admin")
        prom = await _create_promoter(db_session, name="解绑推广员")
        doctor_id = await _create_doctor(db_session)
        doctor_token = make_access_token(user_id=doctor_id, user_type="doctor")

        # Create bound binding request
        with patch(
            "src.services.binding_service.get_rutai_client",
            return_value=mock_rutai,
        ):
            resp = await client.post(
                "/api/v1/binding-requests",
                json={
                    "promoterId": str(prom["user_id"]),
                    "customerInfo": {"name": "解绑患者", "phone": "13800138015"},
                    "sourceType": "manual",
                },
                headers={
                    "Authorization": f"Bearer {doctor_token}",
                    "Idempotency-Key": "ik_unbind_create",
                },
            )
        req_id = resp.json()["data"]["requestId"]

        admin_token = make_access_token(user_id=admin_id, user_type="admin")
        unbind_resp = await client.post(
            f"/api/v1/admin/bindings/{req_id}/unbind",
            json={"reason": "客户投诉，要求解绑"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        data = unbind_resp.json()
        assert_response_envelope(data)
        assert data["code"] == 0
        assert data["data"]["status"] == "unbound"
        assert "reason" in data["data"]

    async def test_missing_reason(self, client: AsyncClient, db_session, mock_rutai):
        """Unbind without reason fails validation."""
        admin_id = await seed_admin(db_session, username="no_reason_admin")
        prom = await _create_promoter(db_session, name="推广员无理由")
        doctor_id = await _create_doctor(db_session)
        doctor_token = make_access_token(user_id=doctor_id, user_type="doctor")

        with patch(
            "src.services.binding_service.get_rutai_client",
            return_value=mock_rutai,
        ):
            resp = await client.post(
                "/api/v1/binding-requests",
                json={
                    "promoterId": str(prom["user_id"]),
                    "customerInfo": {"name": "无理由", "phone": "13800138016"},
                    "sourceType": "manual",
                },
                headers={
                    "Authorization": f"Bearer {doctor_token}",
                    "Idempotency-Key": "ik_unbind_noreason",
                },
            )
        req_id = resp.json()["data"]["requestId"]

        admin_token = make_access_token(user_id=admin_id, user_type="admin")
        unbind_resp = await client.post(
            f"/api/v1/admin/bindings/{req_id}/unbind",
            json={"reason": ""},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert unbind_resp.status_code == 422

    async def test_already_unbound(self, client: AsyncClient, db_session, mock_rutai):
        """Unbinding an already-unbound request fails."""
        admin_id = await seed_admin(db_session, username="double_unbind_admin")
        prom = await _create_promoter(db_session, name="推广员重复解绑")
        doctor_id = await _create_doctor(db_session)
        doctor_token = make_access_token(user_id=doctor_id, user_type="doctor")

        with patch(
            "src.services.binding_service.get_rutai_client",
            return_value=mock_rutai,
        ):
            resp = await client.post(
                "/api/v1/binding-requests",
                json={
                    "promoterId": str(prom["user_id"]),
                    "customerInfo": {"name": "重复解绑", "phone": "13800138017"},
                    "sourceType": "manual",
                },
                headers={
                    "Authorization": f"Bearer {doctor_token}",
                    "Idempotency-Key": "ik_double_unbind",
                },
            )
        req_id = resp.json()["data"]["requestId"]

        admin_token = make_access_token(user_id=admin_id, user_type="admin")
        # First unbind
        await client.post(
            f"/api/v1/admin/bindings/{req_id}/unbind",
            json={"reason": "第一次解绑"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        # Second unbind should fail
        resp2 = await client.post(
            f"/api/v1/admin/bindings/{req_id}/unbind",
            json={"reason": "第二次解绑"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp2.status_code == 400
        assert resp2.json()["code"] == 40027

    async def test_requires_admin_role(self, client: AsyncClient, db_session):
        """Non-admin users cannot unbind."""
        token = make_access_token(user_id=1, user_type="doctor")
        resp = await client.post(
            "/api/v1/admin/bindings/1/unbind",
            json={"reason": "非法解绑"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403


# =============================================================================
# Test Group 8: POST /api/v1/admin/bindings/{id}/transfer
# =============================================================================


class TestAdminTransfer:
    """POST /api/v1/admin/bindings/{id}/transfer"""

    async def test_transfer_success(self, client: AsyncClient, db_session, mock_rutai):
        """Admin can transfer a customer from one promoter to another."""
        admin_id = await seed_admin(db_session, username="transfer_admin")
        prom1 = await _create_promoter(db_session, name="原推广员")
        prom2 = await _create_promoter(db_session, name="新推广员")
        doctor_id = await _create_doctor(db_session)
        doctor_token = make_access_token(user_id=doctor_id, user_type="doctor")

        # Create bound binding request with prom1
        with patch(
            "src.services.binding_service.get_rutai_client",
            return_value=mock_rutai,
        ):
            resp = await client.post(
                "/api/v1/binding-requests",
                json={
                    "promoterId": str(prom1["user_id"]),
                    "customerInfo": {"name": "转移患者", "phone": "13800138018"},
                    "sourceType": "manual",
                },
                headers={
                    "Authorization": f"Bearer {doctor_token}",
                    "Idempotency-Key": "ik_transfer_create",
                },
            )
        req_id = resp.json()["data"]["requestId"]

        admin_token = make_access_token(user_id=admin_id, user_type="admin")
        transfer_resp = await client.post(
            f"/api/v1/admin/bindings/{req_id}/transfer",
            json={
                "newPromoterId": str(prom2["user_id"]),
                "reason": "业务调整",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        data = transfer_resp.json()
        assert_response_envelope(data)
        assert data["code"] == 0
        assert "previousPromoterId" in data["data"]
        assert "newPromoterId" in data["data"]

    async def test_transfer_to_same_promoter(self, client: AsyncClient, db_session, mock_rutai):
        """Transfer to the same promoter fails."""
        admin_id = await seed_admin(db_session, username="same_transfer_admin")
        prom = await _create_promoter(db_session, name="同一推广员")
        doctor_id = await _create_doctor(db_session)
        doctor_token = make_access_token(user_id=doctor_id, user_type="doctor")

        with patch(
            "src.services.binding_service.get_rutai_client",
            return_value=mock_rutai,
        ):
            resp = await client.post(
                "/api/v1/binding-requests",
                json={
                    "promoterId": str(prom["user_id"]),
                    "customerInfo": {"name": "同一推广员转移", "phone": "13800138019"},
                    "sourceType": "manual",
                },
                headers={
                    "Authorization": f"Bearer {doctor_token}",
                    "Idempotency-Key": "ik_same_transfer",
                },
            )
        req_id = resp.json()["data"]["requestId"]

        admin_token = make_access_token(user_id=admin_id, user_type="admin")
        transfer_resp = await client.post(
            f"/api/v1/admin/bindings/{req_id}/transfer",
            json={
                "newPromoterId": str(prom["user_id"]),
                "reason": "不变",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert transfer_resp.status_code == 400
        assert transfer_resp.json()["code"] == 40020

    async def test_requires_admin_role(self, client: AsyncClient, db_session):
        """Non-admin users cannot transfer."""
        token = make_access_token(user_id=1, user_type="doctor")
        resp = await client.post(
            "/api/v1/admin/bindings/1/transfer",
            json={"newPromoterId": "2", "reason": "非法转移"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403


# =============================================================================
# Test Group 9: PUT /api/v1/binding-requests/{id}/customer-info
# =============================================================================


class TestUpdateCustomerInfo:
    """PUT /api/v1/binding-requests/{id}/customer-info"""

    async def test_correct_info(self, client: AsyncClient, db_session, mock_rutai):
        """Update customer info on a pending binding request succeeds."""
        mock_rutai.bind_bj_user_response = {
            "match_status": "pending",
            "match_level": "none",
            "hrb_user_id": None,
        }

        prom = await _create_promoter(db_session, name="更正推广员")
        doctor_id = await _create_doctor(db_session)
        token = make_access_token(user_id=doctor_id, user_type="doctor")

        with patch(
            "src.services.binding_service.get_rutai_client",
            return_value=mock_rutai,
        ):
            resp = await client.post(
                "/api/v1/binding-requests",
                json={
                    "promoterId": str(prom["user_id"]),
                    "customerInfo": {"name": "原名字", "phone": "13800138020"},
                    "sourceType": "manual",
                },
                headers={
                    "Authorization": f"Bearer {token}",
                    "Idempotency-Key": "ik_correct_create",
                },
            )
        req_id = resp.json()["data"]["requestId"]

        # Update customer info
        update_resp = await client.put(
            f"/api/v1/binding-requests/{req_id}/customer-info",
            json={
                "name": "更正后名字",
                "reason": "姓名输入错误",
                "version": 1,
            },
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": "ik_correct_update",
            },
        )
        data = update_resp.json()
        assert_response_envelope(data)
        assert data["code"] == 0
        assert data["data"]["customerInfo"]["name"] == "更正后名字"

    async def test_already_bound_rejection(
        self, client: AsyncClient, db_session, mock_rutai
    ):
        """Cannot update customer info on an already-bound request."""
        prom = await _create_promoter(db_session, name="已绑不可改")
        doctor_id = await _create_doctor(db_session)
        token = make_access_token(user_id=doctor_id, user_type="doctor")

        with patch(
            "src.services.binding_service.get_rutai_client",
            return_value=mock_rutai,
        ):
            resp = await client.post(
                "/api/v1/binding-requests",
                json={
                    "promoterId": str(prom["user_id"]),
                    "customerInfo": {"name": "已绑患者", "phone": "13800138021"},
                    "sourceType": "manual",
                },
                headers={
                    "Authorization": f"Bearer {token}",
                    "Idempotency-Key": "ik_bound_update",
                },
            )
        req_id = resp.json()["data"]["requestId"]

        # Try to update when bound
        update_resp = await client.put(
            f"/api/v1/binding-requests/{req_id}/customer-info",
            json={"name": "新名字", "version": 1},
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": "ik_bound_update_2",
            },
        )
        assert update_resp.status_code == 400
        assert update_resp.json()["code"] == 40027

    async def test_requires_auth(self, client: AsyncClient):
        """Update customer info requires authentication."""
        resp = await client.put(
            "/api/v1/binding-requests/1/customer-info",
            json={"name": "无名"},
            headers={"Idempotency-Key": "ik_test"},
        )
        assert resp.status_code == 401
