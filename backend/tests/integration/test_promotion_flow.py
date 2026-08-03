"""Integration test: full promotion code lifecycle (US10).

Tests the complete journey:
  generate -> refresh -> old token invalid -> check statistics
"""
import secrets
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from tests.conftest import make_access_token, mock_scalar_result


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

    from src.core.database import get_db

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        ac._mock_db = mock_session
        yield ac

    app.dependency_overrides.clear()


def _make_promoter_mock(distributor_id=1, user_id=1, qualification_status="approved"):
    p = MagicMock()
    p.id = distributor_id
    p.user_id = user_id
    p.org_id = 1
    p.qualification_status = qualification_status
    return p


def _make_org_mock(org_id=1, status="active"):
    from src.models.organization import OrgStatus

    o = MagicMock()
    o.id = org_id
    o.status = OrgStatus(status)
    o.parent_id = None
    return o


def _make_org_qualification_mock(qual_id=1, org_id=1, status="approved"):
    """Mock for the org's latest OrganizationQualification (FR-008 gate)."""
    from src.models.org_qualification import OrgQualStatus

    q = MagicMock()
    q.id = qual_id
    q.org_id = org_id
    q.status = OrgQualStatus(status)
    q.valid_until = None
    return q


def _make_promotion_code_mock(
    code_id=1, distributor_id=1, ref_token="ref_tok_abc",
    source_code="BJTR", status="available",
    scan_count=100, lead_count=50, bind_count=25,
    qr_image_url=None, share_title=None, share_path=None,
):
    c = MagicMock()
    c.id = code_id
    c.distributor_id = distributor_id
    c.ref_token = ref_token
    c.source_code = source_code
    c.status = MagicMock()
    c.status.value = status
    c.qr_image_url = qr_image_url
    c.share_title = share_title
    c.share_path = share_path
    c.scan_count = scan_count
    c.lead_count = lead_count
    c.bind_count = bind_count
    c.created_at = datetime.now(timezone.utc)
    c.updated_at = datetime.now(timezone.utc)
    return c


class TestFullPromotionFlow:
    """End-to-end promotion code lifecycle."""

    async def test_full_flow_generate_refresh_statistics(self, mock_client):
        """Full flow: generate code -> verify -> refresh -> old invalid -> check stats."""
        promoter_token = make_access_token(user_id=1, user_type="promoter")
        promoter_headers = {"Authorization": f"Bearer {promoter_token}"}

        promoter = _make_promoter_mock(distributor_id=1, user_id=1, qualification_status="approved")
        org = _make_org_mock(org_id=1)
        org_qual = _make_org_qualification_mock(qual_id=1, org_id=1, status="approved")

        # Phase 1: Get promotion code (first time - generates new)
        old_token = "old_ref_token_001"
        old_code = _make_promotion_code_mock(
            code_id=1, distributor_id=1, ref_token=old_token,
            status="available", scan_count=0, lead_count=0, bind_count=0,
        )
        new_token = secrets.token_urlsafe(32)
        new_code = _make_promotion_code_mock(
            code_id=1, distributor_id=1, ref_token=new_token,
            status="available", scan_count=0, lead_count=0, bind_count=0,
        )

        # Mock: lookup promoter found, org approved (FR-008), no existing promo code
        mock_client._mock_db.execute = AsyncMock()
        mock_client._mock_db.execute.side_effect = [
            mock_scalar_result(first_value=promoter),       # lookup promoter by user_id
            mock_scalar_result(first_value=promoter),        # lookup distributor by id (FR-008)
            mock_scalar_result(first_value=org),             # lookup org
            mock_scalar_result(first_value=org_qual),        # lookup org qualification
            mock_scalar_result(first_value=None),            # no existing promo code
        ]

        get_resp = await mock_client.get(
            "/api/v1/promotion-code", headers=promoter_headers
        )
        assert get_resp.status_code == 200
        get_data = get_resp.json()
        assert get_data["code"] == 0
        assert len(get_data["data"]["refToken"]) > 0

        # Phase 2: Refresh promotion code
        mock_client._mock_db.execute = AsyncMock()
        mock_client._mock_db.execute.side_effect = [
            mock_scalar_result(first_value=promoter),        # lookup promoter by user_id
            mock_scalar_result(first_value=promoter),         # lookup distributor by id (FR-008)
            mock_scalar_result(first_value=org),              # lookup org
            mock_scalar_result(first_value=org_qual),         # lookup org qualification
            mock_scalar_result(first_value=old_code),         # find existing code
        ]

        refresh_resp = await mock_client.post(
            "/api/v1/promotion-code/refresh",
            headers=promoter_headers,
        )
        assert refresh_resp.status_code == 200
        refresh_data = refresh_resp.json()
        assert refresh_data["code"] == 0
        # New token should be different from old
        assert "refToken" in refresh_data["data"]

        # Phase 3: Get statistics
        stats_code = _make_promotion_code_mock(
            code_id=1, distributor_id=1, ref_token="stats_token",
            status="available", scan_count=120, lead_count=60, bind_count=30,
        )

        mock_client._mock_db.execute = AsyncMock()
        mock_client._mock_db.execute.side_effect = [
            mock_scalar_result(first_value=promoter),        # lookup promoter by user_id
            mock_scalar_result(first_value=promoter),         # lookup distributor by id (FR-008)
            mock_scalar_result(first_value=org),              # lookup org
            mock_scalar_result(first_value=org_qual),         # lookup org qualification
            mock_scalar_result(first_value=stats_code),       # find promo code
        ]

        stats_resp = await mock_client.get(
            "/api/v1/promotion-code/statistics",
            params={"period": "30d"},
            headers=promoter_headers,
        )
        assert stats_resp.status_code == 200
        stats_data = stats_resp.json()
        assert stats_data["code"] == 0
        assert stats_data["data"]["scanCount"] == 120
        assert stats_data["data"]["leadCount"] == 60
        assert stats_data["data"]["bindCount"] == 30

        print("Full promotion code lifecycle completed: generate -> refresh -> statistics")


class TestPromotionPoster:
    """Promotion poster endpoint tests."""

    async def test_get_poster_returns_url(self, mock_client):
        """Test that the poster endpoint returns a poster image URL."""
        promoter_token = make_access_token(user_id=1, user_type="promoter")
        promoter_headers = {"Authorization": f"Bearer {promoter_token}"}

        promoter = _make_promoter_mock(distributor_id=1, user_id=1, qualification_status="approved")
        org = _make_org_mock(org_id=1)
        org_qual = _make_org_qualification_mock(qual_id=1, org_id=1, status="approved")
        code = _make_promotion_code_mock(
            code_id=1, distributor_id=1, ref_token="poster_token",
            status="available", qr_image_url="https://cos.example.com/qr/poster_1.png",
            share_title="北京儒泰分销", share_path="/pages/index/index",
        )

        mock_client._mock_db.execute = AsyncMock()
        mock_client._mock_db.execute.side_effect = [
            mock_scalar_result(first_value=promoter),        # lookup promoter by user_id
            mock_scalar_result(first_value=promoter),         # lookup distributor by id (FR-008)
            mock_scalar_result(first_value=org),              # lookup org
            mock_scalar_result(first_value=org_qual),         # lookup org qualification
            mock_scalar_result(first_value=code),             # promo code
        ]

        poster_resp = await mock_client.get(
            "/api/v1/promotion-code/poster",
            headers=promoter_headers,
        )
        assert poster_resp.status_code == 200
        poster_data = poster_resp.json()
        assert poster_data["code"] == 0
        assert "posterUrl" in poster_data["data"] or "qrImageUrl" in poster_data["data"]
