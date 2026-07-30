"""Contract tests for sharing rules endpoints.

Tests ensure the sharing rules endpoints conform to the unified
response format {code, message, data, requestId, serverTime} and behave
correctly under all documented scenarios.

Uses real SQLite test database via conftest.py fixtures (same pattern as test_articles.py).
"""

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token
from src.models.sharing import SharingRule, RuleType, RuleBase, RuleStatus
from tests.conftest import assert_response_envelope, seed_admin


def _admin_token(user_id: int = 1) -> str:
    return create_access_token(data={"sub": str(user_id), "user_type": "admin"})


def _auth_headers(user_id: int = 1) -> dict:
    return {"Authorization": f"Bearer {_admin_token(user_id)}"}


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------
async def seed_rule(
    db: AsyncSession,
    *,
    level: int = 2,
    rule_type: str = "fixed_ratio",
    base: str = "paid_amount",
    value: str = "0.70",
    status: str = "active",
    version: int = 1,
    effective_at: datetime | None = None,
    created_by: int | None = None,
) -> int:
    """Insert a sharing rule and return its id."""
    from datetime import timezone as tz

    now = datetime.now(tz.utc)
    rule = SharingRule(
        level=level,
        rule_type=RuleType(rule_type),
        base=RuleBase(base),
        value=value,
        effective_at=effective_at or now,
        status=RuleStatus(status),
        version=version,
        created_by=created_by,
        created_at=now,
        updated_at=now,
    )
    db.add(rule)
    await db.flush()
    await db.refresh(rule)
    return rule.id


# ============================================================================
# GET /api/v1/admin/sharing-rules
# ============================================================================
class TestListSharingRules:
    """GET /api/v1/admin/sharing-rules"""

    async def test_list_all_rules_returns_envelope(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Listing all rules returns properly enveloped response."""
        await seed_admin(db_session, username="admin_test", password_plain="testpass123")
        await seed_rule(db_session, level=2)

        resp = await client.get(
            "/api/v1/admin/sharing-rules",
            headers=_auth_headers(),
        )

        assert resp.status_code == 200
        body = resp.json()
        assert_response_envelope(body)
        assert body["code"] == 0
        assert "items" in body["data"]
        assert isinstance(body["data"]["items"], list)
        assert "nextCursor" in body["data"]
        assert "hasMore" in body["data"]

    async def test_filter_by_level(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Filtering by level returns only matching rules."""
        await seed_admin(db_session, username="admin_test", password_plain="testpass123")
        await seed_rule(db_session, level=3)
        await seed_rule(db_session, level=4)

        resp = await client.get(
            "/api/v1/admin/sharing-rules?level=3",
            headers=_auth_headers(),
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        items = body["data"]["items"]
        assert len(items) == 1
        assert items[0]["level"] == 3

    async def test_filter_by_active_status(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Filtering by active status returns only active rules."""
        await seed_admin(db_session, username="admin_test", password_plain="testpass123")
        await seed_rule(db_session, level=2, status="active")
        await seed_rule(db_session, level=3, status="inactive")

        resp = await client.get(
            "/api/v1/admin/sharing-rules?status=active",
            headers=_auth_headers(),
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        items = body["data"]["items"]
        for item in items:
            assert item["status"] == "active"

    async def test_filter_by_inactive_status(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Filtering by inactive status returns only inactive rules."""
        await seed_admin(db_session, username="admin_test", password_plain="testpass123")
        await seed_rule(db_session, level=2, status="active")
        await seed_rule(db_session, level=3, status="inactive")

        resp = await client.get(
            "/api/v1/admin/sharing-rules?status=inactive",
            headers=_auth_headers(),
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        items = body["data"]["items"]
        for item in items:
            assert item["status"] == "inactive"

    async def test_empty_list(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """No rules returns empty items list."""
        await seed_admin(db_session, username="admin_test", password_plain="testpass123")

        resp = await client.get(
            "/api/v1/admin/sharing-rules",
            headers=_auth_headers(),
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["items"] == []

    async def test_requires_admin_auth(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Calling without admin auth returns 401 or 403."""
        resp = await client.get("/api/v1/admin/sharing-rules")
        assert resp.status_code in (401, 403)


# ============================================================================
# POST /api/v1/admin/sharing-rules
# ============================================================================
class TestCreateSharingRule:
    """POST /api/v1/admin/sharing-rules"""

    async def test_create_fixed_ratio_rule(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Creating a fixed_ratio rule succeeds."""
        await seed_admin(db_session, username="admin_test", password_plain="testpass123")

        resp = await client.post(
            "/api/v1/admin/sharing-rules",
            json={
                "level": 2,
                "rule_type": "fixed_ratio",
                "base": "paid_amount",
                "value": "0.70",
                "effective_at": "2026-08-01T00:00:00Z",
            },
            headers=_auth_headers(),
        )

        assert resp.status_code == 200
        body = resp.json()
        assert_response_envelope(body)
        assert body["code"] == 0
        assert body["data"]["ruleId"] is not None

    async def test_create_fixed_amount_rule(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Creating a fixed_amount rule succeeds."""
        await seed_admin(db_session, username="admin_test", password_plain="testpass123")

        resp = await client.post(
            "/api/v1/admin/sharing-rules",
            json={
                "level": 2,
                "rule_type": "fixed_amount",
                "base": "paid_amount",
                "value": "5000",
                "effective_at": "2026-08-01T00:00:00Z",
            },
            headers=_auth_headers(),
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0

    async def test_create_tiered_rule(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Creating a tiered rule with valid JSON tiers succeeds."""
        await seed_admin(db_session, username="admin_test", password_plain="testpass123")

        resp = await client.post(
            "/api/v1/admin/sharing-rules",
            json={
                "level": 3,
                "rule_type": "tiered",
                "base": "total_amount",
                "value": '[{"threshold": 10000, "ratio": 0.10}, {"threshold": 50000, "ratio": 0.15}]',
                "effective_at": "2026-08-01T00:00:00Z",
            },
            headers=_auth_headers(),
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0

    async def test_same_level_active_conflict_rejected(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Creating a rule at a level that already has an active rule returns 409."""
        await seed_admin(db_session, username="admin_test", password_plain="testpass123")
        await seed_rule(db_session, level=3, status="active")

        resp = await client.post(
            "/api/v1/admin/sharing-rules",
            json={
                "level": 3,
                "rule_type": "fixed_ratio",
                "base": "paid_amount",
                "value": "0.50",
                "effective_at": "2026-08-01T00:00:00Z",
            },
            headers=_auth_headers(),
        )

        assert resp.status_code == 409

    async def test_ratio_exceeds_100_percent_rejected(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """A ratio > 1.0 is rejected with validation error."""
        await seed_admin(db_session, username="admin_test", password_plain="testpass123")

        resp = await client.post(
            "/api/v1/admin/sharing-rules",
            json={
                "level": 2,
                "rule_type": "fixed_ratio",
                "base": "paid_amount",
                "value": "1.50",
                "effective_at": "2026-08-01T00:00:00Z",
            },
            headers=_auth_headers(),
        )

        assert resp.status_code == 422

    async def test_negative_ratio_rejected(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """A negative ratio is rejected with validation error."""
        await seed_admin(db_session, username="admin_test", password_plain="testpass123")

        resp = await client.post(
            "/api/v1/admin/sharing-rules",
            json={
                "level": 2,
                "rule_type": "fixed_ratio",
                "base": "paid_amount",
                "value": "-0.10",
                "effective_at": "2026-08-01T00:00:00Z",
            },
            headers=_auth_headers(),
        )

        assert resp.status_code == 422

    async def test_requires_admin_auth(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Creating without admin auth returns 401 or 403."""
        resp = await client.post(
            "/api/v1/admin/sharing-rules",
            json={
                "level": 2,
                "rule_type": "fixed_ratio",
                "base": "paid_amount",
                "value": "0.70",
                "effective_at": "2026-08-01T00:00:00Z",
            },
        )
        assert resp.status_code in (401, 403)


# ============================================================================
# PUT /api/v1/admin/sharing-rules/{id}
# ============================================================================
class TestUpdateSharingRule:
    """PUT /api/v1/admin/sharing-rules/{id}"""

    async def test_update_rule_succeeds(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Updating an existing rule with correct version succeeds."""
        await seed_admin(db_session, username="admin_test", password_plain="testpass123")
        rule_id = await seed_rule(db_session, level=2, version=1)

        resp = await client.put(
            f"/api/v1/admin/sharing-rules/{rule_id}",
            json={
                "value": "0.80",
                "version": 1,
            },
            headers=_auth_headers(),
        )

        assert resp.status_code == 200
        body = resp.json()
        assert_response_envelope(body)
        assert body["code"] == 0

    async def test_update_version_conflict_returns_409(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Updating with stale version returns 409 conflict."""
        await seed_admin(db_session, username="admin_test", password_plain="testpass123")
        rule_id = await seed_rule(db_session, level=2, version=2)

        resp = await client.put(
            f"/api/v1/admin/sharing-rules/{rule_id}",
            json={
                "value": "0.80",
                "version": 1,  # stale version
            },
            headers=_auth_headers(),
        )

        assert resp.status_code == 409

    async def test_update_nonexistent_rule_returns_404(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Updating a non-existent rule returns 404."""
        await seed_admin(db_session, username="admin_test", password_plain="testpass123")

        resp = await client.put(
            "/api/v1/admin/sharing-rules/999",
            json={
                "value": "0.80",
                "version": 1,
            },
            headers=_auth_headers(),
        )

        assert resp.status_code == 404

    async def test_requires_admin_auth(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Updating without admin auth returns 401 or 403."""
        resp = await client.put(
            "/api/v1/admin/sharing-rules/1",
            json={
                "value": "0.80",
                "version": 1,
            },
        )
        assert resp.status_code in (401, 403)


# ============================================================================
# POST /api/v1/admin/sharing-rules/{id}/deactivate
# ============================================================================
class TestDeactivateSharingRule:
    """POST /api/v1/admin/sharing-rules/{id}/deactivate"""

    async def test_deactivate_active_rule_succeeds(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Deactivating an active rule succeeds."""
        await seed_admin(db_session, username="admin_test", password_plain="testpass123")
        rule_id = await seed_rule(db_session, level=2, status="active")

        resp = await client.post(
            f"/api/v1/admin/sharing-rules/{rule_id}/deactivate",
            headers=_auth_headers(),
        )

        assert resp.status_code == 200
        body = resp.json()
        assert_response_envelope(body)
        assert body["code"] == 0

    async def test_deactivate_already_inactive_returns_400(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Deactivating an already inactive rule returns 400."""
        await seed_admin(db_session, username="admin_test", password_plain="testpass123")
        rule_id = await seed_rule(db_session, level=2, status="inactive")

        resp = await client.post(
            f"/api/v1/admin/sharing-rules/{rule_id}/deactivate",
            headers=_auth_headers(),
        )

        assert resp.status_code == 400

    async def test_deactivate_nonexistent_rule_returns_404(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Deactivating a non-existent rule returns 404."""
        await seed_admin(db_session, username="admin_test", password_plain="testpass123")

        resp = await client.post(
            "/api/v1/admin/sharing-rules/999/deactivate",
            headers=_auth_headers(),
        )

        assert resp.status_code == 404

    async def test_requires_admin_auth(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Deactivating without admin auth returns 401 or 403."""
        resp = await client.post("/api/v1/admin/sharing-rules/1/deactivate")
        assert resp.status_code in (401, 403)


# ============================================================================
# GET /api/v1/admin/contribution-coefficient
# ============================================================================
class TestGetContributionCoefficient:
    """GET /api/v1/admin/contribution-coefficient"""

    async def test_get_current_coefficient(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Getting the current coefficient returns a valid response."""
        await seed_admin(db_session, username="admin_test", password_plain="testpass123")

        resp = await client.get(
            "/api/v1/admin/contribution-coefficient",
            headers=_auth_headers(),
        )

        assert resp.status_code == 200
        body = resp.json()
        assert_response_envelope(body)
        assert body["code"] == 0
        assert "coefficient" in body["data"]

    async def test_requires_admin_auth(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Calling without admin auth returns 401 or 403."""
        resp = await client.get("/api/v1/admin/contribution-coefficient")
        assert resp.status_code in (401, 403)
