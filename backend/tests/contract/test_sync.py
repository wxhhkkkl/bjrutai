"""Contract tests for admin sync endpoints.

Tests ensure the 3 sync endpoints conform to the unified response format
{code, message, data, requestId, serverTime} and behave correctly under
all documented scenarios.

Uses mocked database and sync service for isolation.
TDD: These tests are written FIRST and are expected to FAIL until the
implementation is complete.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.core.security import create_access_token
from src.main import app
from tests.conftest import assert_response_envelope, auth_header


# ---------------------------------------------------------------------------
# Fixture: AsyncClient with mocked DB and sync service
# ---------------------------------------------------------------------------
@pytest.fixture
async def mock_client():
    """Return an AsyncClient with get_db overridden to yield a mock session."""
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.refresh = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.delete = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.execute = AsyncMock()

    from src.api.deps import get_db

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        ac._mock_db = mock_session
        yield ac

    app.dependency_overrides.clear()


def make_admin_token(admin_id: int = 1) -> str:
    return create_access_token(data={"sub": str(admin_id), "user_type": "admin"})


# =========================================================================
# POST /api/v1/admin/sync/retry-binduser
# =========================================================================
class TestRetryBindUser:
    """POST /api/v1/admin/sync/retry-binduser"""

    async def test_trigger_success(self, mock_client):
        """Successful manual retry trigger returns accepted status."""
        token = make_admin_token()

        with patch(
            "src.services.sync_service.SyncService.retry_bind_users",
            new_callable=AsyncMock,
            return_value={"status": "accepted", "message": "Bind user sync triggered"},
        ):
            response = await mock_client.post(
                "/api/v1/admin/sync/retry-binduser",
                headers=auth_header(token),
            )

        assert response.status_code == 200
        body = response.json()
        assert_response_envelope(body)
        assert body["code"] == 0
        assert body["data"]["status"] == "accepted"

    async def test_already_running_returns_conflict(self, mock_client):
        """When a sync is already running, return 409 conflict."""
        token = make_admin_token()

        with patch(
            "src.services.sync_service.SyncService.retry_bind_users",
            new_callable=AsyncMock,
            side_effect=Exception("Sync already in progress"),
        ):
            response = await mock_client.post(
                "/api/v1/admin/sync/retry-binduser",
                headers=auth_header(token),
            )

        assert response.status_code == 409
        body = response.json()
        assert body["code"] == 40900

    async def test_requires_admin_auth(self, mock_client):
        """Call without auth returns 401."""
        response = await mock_client.post("/api/v1/admin/sync/retry-binduser")
        assert response.status_code == 401

    async def test_promoter_cannot_access(self, mock_client):
        """Distributor token returns 403 Forbidden."""
        promoter_token = create_access_token(
            data={"sub": "2", "user_type": "promoter"}
        )
        response = await mock_client.post(
            "/api/v1/admin/sync/retry-binduser",
            headers=auth_header(promoter_token),
        )
        assert response.status_code == 403


# =========================================================================
# POST /api/v1/admin/sync/retry-bill/{userId}
# =========================================================================
class TestRetryBill:
    """POST /api/v1/admin/sync/retry-bill/{user_id}"""

    async def test_retry_valid_user_success(self, mock_client):
        """Retry bill fetch for a valid user returns accepted."""
        token = make_admin_token()

        with patch(
            "src.services.sync_service.SyncService.retry_user_bill",
            new_callable=AsyncMock,
            return_value={"status": "accepted", "user_id": "rutai_user_001"},
        ):
            response = await mock_client.post(
                "/api/v1/admin/sync/retry-bill/rutai_user_001",
                headers=auth_header(token),
            )

        assert response.status_code == 200
        body = response.json()
        assert_response_envelope(body)
        assert body["code"] == 0
        assert body["data"]["status"] == "accepted"

    async def test_invalid_user_id_returns_404(self, mock_client):
        """Retry for nonexistent user returns 404."""
        token = make_admin_token()

        with patch(
            "src.services.sync_service.SyncService.retry_user_bill",
            new_callable=AsyncMock,
            side_effect=Exception("User not found"),
        ):
            response = await mock_client.post(
                "/api/v1/admin/sync/retry-bill/nonexistent_user",
                headers=auth_header(token),
            )

        assert response.status_code == 404
        body = response.json()
        assert body["code"] == 40400

    async def test_requires_admin_auth(self, mock_client):
        """Call without auth returns 401."""
        response = await mock_client.post(
            "/api/v1/admin/sync/retry-bill/some_user"
        )
        assert response.status_code == 401


# =========================================================================
# GET /api/v1/admin/sync/status
# =========================================================================
class TestSyncStatus:
    """GET /api/v1/admin/sync/status"""

    async def test_returns_polling_status(self, mock_client):
        """Status endpoint returns current polling state."""
        token = make_admin_token()

        with patch(
            "src.services.sync_service.SyncService.get_sync_status",
            new_callable=AsyncMock,
            return_value={
                "last_success": "2026-07-30T10:00:00Z",
                "failure_count": 0,
                "pending_retries": 0,
                "is_polling": True,
                "circuit_breaker_open": False,
                "last_bind_user_poll": "2026-07-30T10:00:00Z",
                "last_bill_sync": "2026-07-30T09:55:00Z",
            },
        ):
            response = await mock_client.get(
                "/api/v1/admin/sync/status",
                headers=auth_header(token),
            )

        assert response.status_code == 200
        body = response.json()
        assert_response_envelope(body)
        assert body["code"] == 0
        data = body["data"]
        assert "last_success" in data
        assert "failure_count" in data
        assert "pending_retries" in data
        assert "is_polling" in data
        assert "circuit_breaker_open" in data

    async def test_returns_failure_count_when_errors(self, mock_client):
        """Status reflects failure count correctly."""
        token = make_admin_token()

        with patch(
            "src.services.sync_service.SyncService.get_sync_status",
            new_callable=AsyncMock,
            return_value={
                "last_success": "2026-07-30T08:00:00Z",
                "failure_count": 5,
                "pending_retries": 12,
                "is_polling": True,
                "circuit_breaker_open": True,
                "last_bind_user_poll": "2026-07-30T10:00:00Z",
                "last_bill_sync": "2026-07-30T08:30:00Z",
            },
        ):
            response = await mock_client.get(
                "/api/v1/admin/sync/status",
                headers=auth_header(token),
            )

        assert response.status_code == 200
        body = response.json()
        assert body["data"]["failure_count"] == 5
        assert body["data"]["circuit_breaker_open"] is True

    async def test_requires_admin_auth(self, mock_client):
        """Call without auth returns 401."""
        response = await mock_client.get("/api/v1/admin/sync/status")
        assert response.status_code == 401
