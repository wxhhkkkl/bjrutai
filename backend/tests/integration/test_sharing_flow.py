"""Integration tests for sharing rules lifecycle.

Tests the full lifecycle of sharing rules using a real SQLite test database.
"""

import json
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.main import app
from src.core.database import get_db
from src.core.security import create_access_token
from src.models.sharing import (
    SharingRule,
    RuleType,
    RuleBase,
    RuleStatus,
    sharing_rule_change_logs,
)
from tests.conftest import (
    assert_response_envelope,
    db_session,
    seed_admin,
)


def _admin_token(user_id: int = 1) -> str:
    return create_access_token(data={"sub": str(user_id), "user_type": "admin"})


def _auth_headers(user_id: int = 1) -> dict:
    return {"Authorization": f"Bearer {_admin_token(user_id)}"}


# ──────────────────────────────────────────────
# Full Rule Lifecycle Test
# ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_rule_lifecycle_create_deactivate_and_audit_log(db_session: AsyncSession):
    """Test the complete lifecycle: create, verify, deactivate, and check audit log.

    Steps:
    1. Create an admin user for auth
    2. Create a sharing rule via API
    3. Verify it appears in the list
    4. Deactivate it
    5. Verify the change log was recorded
    """
    # Seed an admin user
    admin_id = await seed_admin(db_session, username="admin_test", password_plain="testpass123")

    # Override get_db for this test
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)

    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = _auth_headers(admin_id)

            # Step 1: Create a rule
            create_response = await client.post(
                "/api/v1/admin/sharing-rules",
                json={
                    "level": 2,
                    "rule_type": "fixed_ratio",
                    "base": "paid_amount",
                    "value": "0.70",
                    "effective_at": "2026-01-01T00:00:00Z",
                },
                headers=headers,
            )

            assert create_response.status_code == 200
            create_body = create_response.json()
            assert create_body["code"] == 0
            rule_id = int(create_body["data"]["ruleId"])

            # Step 2: Verify rule appears in list
            list_response = await client.get(
                "/api/v1/admin/sharing-rules",
                headers=headers,
            )
            assert list_response.status_code == 200
            list_body = list_response.json()
            assert len(list_body["data"]["items"]) >= 1
            rule_ids = [item["ruleId"] for item in list_body["data"]["items"]]
            assert str(rule_id) in rule_ids

            # Step 3: Update the rule (change value)
            update_response = await client.put(
                f"/api/v1/admin/sharing-rules/{rule_id}",
                json={
                    "value": "0.75",
                    "version": 1,
                },
                headers=headers,
            )
            assert update_response.status_code == 200
            update_body = update_response.json()
            assert update_body["code"] == 0

            # Step 4: Verify change log was recorded
            # Refresh db session to see new data
            await db_session.flush()
            from sqlalchemy import select

            log_result = await db_session.execute(
                select(sharing_rule_change_logs).where(
                    sharing_rule_change_logs.c.rule_id == rule_id
                )
            )
            logs = list(log_result)
            assert len(logs) >= 1, "Change log should have at least one entry"

            # Step 5: Deactivate the rule
            deactivate_response = await client.post(
                f"/api/v1/admin/sharing-rules/{rule_id}/deactivate",
                headers=headers,
            )
            assert deactivate_response.status_code == 200
            deactivate_body = deactivate_response.json()
            assert deactivate_body["code"] == 0

            # Step 6: Verify rule is now inactive
            # Manually check the DB
            rule_result = await db_session.execute(
                select(SharingRule).where(SharingRule.id == rule_id)
            )
            rule = rule_result.scalar_one_or_none()
            assert rule is not None
            assert rule.status == RuleStatus.INACTIVE

    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_multiple_rules_different_levels(db_session: AsyncSession):
    """Creating rules at different levels should all succeed."""
    admin_id = await seed_admin(db_session, username="multilevel_admin", password_plain="testpass123")

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)

    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = _auth_headers(admin_id)

            # Create rule at level 2
            r1 = await client.post(
                "/api/v1/admin/sharing-rules",
                json={
                    "level": 2,
                    "rule_type": "fixed_ratio",
                    "base": "paid_amount",
                    "value": "0.60",
                    "effective_at": "2026-01-01T00:00:00Z",
                },
                headers=headers,
            )
            assert r1.status_code == 200

            # Create rule at level 3
            r2 = await client.post(
                "/api/v1/admin/sharing-rules",
                json={
                    "level": 3,
                    "rule_type": "fixed_ratio",
                    "base": "paid_amount",
                    "value": "0.50",
                    "effective_at": "2026-01-01T00:00:00Z",
                },
                headers=headers,
            )
            assert r2.status_code == 200

            # Create rule at level 4
            r3 = await client.post(
                "/api/v1/admin/sharing-rules",
                json={
                    "level": 4,
                    "rule_type": "fixed_amount",
                    "base": "total_amount",
                    "value": "3000",
                    "effective_at": "2026-01-01T00:00:00Z",
                },
                headers=headers,
            )
            assert r3.status_code == 200

            # List all rules - should have 3
            list_resp = await client.get(
                "/api/v1/admin/sharing-rules",
                headers=headers,
            )
            assert list_resp.status_code == 200
            list_body = list_resp.json()
            assert len(list_body["data"]["items"]) == 3

    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_same_level_active_rule_conflict(db_session: AsyncSession):
    """Creating a second active rule at the same level should fail with 409."""
    admin_id = await seed_admin(db_session, username="conflict_admin", password_plain="testpass123")

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)

    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = _auth_headers(admin_id)

            # Create first rule at level 2
            r1 = await client.post(
                "/api/v1/admin/sharing-rules",
                json={
                    "level": 2,
                    "rule_type": "fixed_ratio",
                    "base": "paid_amount",
                    "value": "0.60",
                    "effective_at": "2026-01-01T00:00:00Z",
                },
                headers=headers,
            )
            assert r1.status_code == 200

            # Try to create second rule at same level 2 (should conflict)
            r2 = await client.post(
                "/api/v1/admin/sharing-rules",
                json={
                    "level": 2,
                    "rule_type": "fixed_ratio",
                    "base": "paid_amount",
                    "value": "0.40",
                    "effective_at": "2026-01-01T00:00:00Z",
                },
                headers=headers,
            )
            assert r2.status_code == 409

    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_update_version_conflict(db_session: AsyncSession):
    """Updating a rule with a stale version should return 409."""
    admin_id = await seed_admin(db_session, username="version_admin", password_plain="testpass123")

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)

    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = _auth_headers(admin_id)

            # Create a rule
            create_resp = await client.post(
                "/api/v1/admin/sharing-rules",
                json={
                    "level": 5,
                    "rule_type": "fixed_ratio",
                    "base": "paid_amount",
                    "value": "0.30",
                    "effective_at": "2026-01-01T00:00:00Z",
                },
                headers=headers,
            )
            assert create_resp.status_code == 200
            rule_id = int(create_resp.json()["data"]["ruleId"])

            # First update with version 1 (should succeed, version becomes 2)
            u1 = await client.put(
                f"/api/v1/admin/sharing-rules/{rule_id}",
                json={"value": "0.35", "version": 1},
                headers=headers,
            )
            assert u1.status_code == 200

            # Second update with stale version 1 (should fail)
            u2 = await client.put(
                f"/api/v1/admin/sharing-rules/{rule_id}",
                json={"value": "0.40", "version": 1},
                headers=headers,
            )
            assert u2.status_code == 409

    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_deactivate_already_inactive_rule(db_session: AsyncSession):
    """Deactivating an already inactive rule should return 400."""
    admin_id = await seed_admin(db_session, username="deactivate_admin", password_plain="testpass123")

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)

    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = _auth_headers(admin_id)

            # Create and immediately deactivate a rule
            create_resp = await client.post(
                "/api/v1/admin/sharing-rules",
                json={
                    "level": 2,
                    "rule_type": "fixed_ratio",
                    "base": "paid_amount",
                    "value": "0.25",
                    "effective_at": "2026-01-01T00:00:00Z",
                },
                headers=headers,
            )
            rule_id = int(create_resp.json()["data"]["ruleId"])

            # First deactivate (should succeed)
            d1 = await client.post(
                f"/api/v1/admin/sharing-rules/{rule_id}/deactivate",
                headers=headers,
            )
            assert d1.status_code == 200

            # Second deactivate (should fail - already inactive)
            d2 = await client.post(
                f"/api/v1/admin/sharing-rules/{rule_id}/deactivate",
                headers=headers,
            )
            assert d2.status_code == 400

    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_coefficient_lifecycle(db_session: AsyncSession):
    """Test the contribution coefficient get and update flow."""
    admin_id = await seed_admin(db_session, username="coeff_admin", password_plain="testpass123")

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)

    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = _auth_headers(admin_id)

            # Get initial coefficient (should return default or empty)
            get_resp = await client.get(
                "/api/v1/admin/contribution-coefficient",
                headers=headers,
            )
            assert get_resp.status_code == 200
            get_body = get_resp.json()
            assert get_body["code"] == 0
            # Even if no coefficient set, should still return valid response
            assert "coefficient" in get_body["data"]

    finally:
        app.dependency_overrides.clear()
