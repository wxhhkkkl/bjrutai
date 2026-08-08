"""Integration test: full WeChat login flow.

Tests the complete user journey:
  code -> tokens -> session -> bootstrap -> refresh -> logout

Uses mocked database and WeChat client for reliable integration testing.
"""

import hashlib
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.core.security import create_access_token, create_refresh_token, get_password_hash
from src.main import app
from tests.conftest import (
    assert_response_envelope,
    auth_header,
    make_mock_admin,
    make_mock_role,
    make_mock_token,
    make_mock_user,
    mock_scalar_result,
)


# ──────────────────────────────────────────────
# Fixture: AsyncClient with mocked DB
# ──────────────────────────────────────────────
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


class TestFullWechatLoginFlow:
    """End-to-end WeChat login flow test."""

    async def test_full_flow_code_to_logout(self, mock_client):
        """
        Simulate complete session: code -> tokens -> session -> bootstrap -> refresh -> logout
        """
        mock_user = make_mock_user(user_id=10, openid="flow_openid", user_type="promoter")

        # ── Phase 1: WeChat Login ─────────────────────────────────
        with patch(
            "src.integrations.wechat_client.WechatClient.jscode2session",
            new_callable=AsyncMock,
            return_value={"openid": "flow_openid", "session_key": "sk_flow", "unionid": "flow_unionid"},
        ):
            mock_client._mock_db.execute = AsyncMock(
                return_value=mock_scalar_result(first_value=mock_user)
            )
            login_resp = await mock_client.post(
                "/api/v1/auth/wechat-login",
                json={"code": "flow_code_01"},
            )

        assert login_resp.status_code == 200
        login_body = login_resp.json()
        assert login_body["code"] == 0
        access_token = login_body["data"]["accessToken"]
        refresh_token = login_body["data"]["refreshToken"]
        assert access_token
        assert refresh_token
        assert login_body["data"]["tokenType"] == "Bearer"
        assert login_body["data"]["user"]["isNewUser"] is False

        auth_headers = auth_header(access_token)

        # ── Phase 2: Session Check ────────────────────────────────
        mock_client._mock_db.execute = AsyncMock(
            return_value=mock_scalar_result(first_value=mock_user)
        )
        session_resp = await mock_client.get("/api/v1/auth/session", headers=auth_headers)
        assert session_resp.status_code == 200
        session_body = session_resp.json()
        assert session_body["code"] == 0
        assert session_body["data"]["user"]["role"] == "promoter"
        assert "tokenExpiresAt" in session_body["data"]

        # ── Phase 3: Bootstrap ────────────────────────────────────
        mock_client._mock_db.execute = AsyncMock(
            return_value=mock_scalar_result(first_value=mock_user)
        )
        bootstrap_resp = await mock_client.get("/api/v1/app/bootstrap", headers=auth_headers)
        assert bootstrap_resp.status_code == 200
        bootstrap_body = bootstrap_resp.json()
        assert bootstrap_body["code"] == 0
        assert "session" in bootstrap_body["data"]

        # ── Phase 4: Token Refresh ────────────────────────────────
        family_id = str(uuid.uuid4())
        refresh_jwt = create_refresh_token(
            data={"sub": "10", "user_type": "promoter", "family": family_id, "jti": "100"}
        )
        token_hash = hashlib.sha256(refresh_jwt.encode()).hexdigest()
        existing_token = make_mock_token(
            token_id=100, user_id=10, token_hash=token_hash, family=family_id, is_revoked=False
        )

        mock_client._mock_db.execute = AsyncMock()
        mock_client._mock_db.execute.side_effect = [
            mock_scalar_result(first_value=existing_token),
            mock_scalar_result(all_values=[existing_token]),
        ]

        refresh_resp = await mock_client.post(
            "/api/v1/auth/refresh",
            json={"refreshToken": refresh_jwt},
        )
        assert refresh_resp.status_code == 200
        refresh_body = refresh_resp.json()
        assert refresh_body["code"] == 0
        assert refresh_body["data"]["accessToken"]
        assert refresh_body["data"]["refreshToken"]
        assert refresh_body["data"]["tokenType"] == "Bearer"

        # ── Phase 5: Logout ───────────────────────────────────────
        mock_client._mock_db.execute = AsyncMock(
            return_value=mock_scalar_result(first_value=mock_user)
        )
        logout_resp = await mock_client.post("/api/v1/auth/logout", headers=auth_headers)
        assert logout_resp.status_code == 200
        logout_body = logout_resp.json()
        assert logout_body["code"] == 0
        assert logout_body["data"] is None

        print("Full flow completed: code -> tokens -> session -> bootstrap -> refresh -> logout")


class TestAdminLoginFlow:
    """End-to-end admin login flow test."""

    async def test_admin_login_and_session(self, mock_client):
        """Admin login -> session -> refresh -> logout."""
        admin = make_mock_admin(admin_id=1, username="admin_flow", password_plain="testpass123")
        role = make_mock_role(name="admin")

        # ── Admin Login ───────────────────────────────────────────
        mock_client._mock_db.execute = AsyncMock()
        mock_client._mock_db.execute.side_effect = [
            mock_scalar_result(first_value=admin),
            mock_scalar_result(all_values=[role]),
        ]

        login_resp = await mock_client.post(
            "/api/v1/auth/admin-login",
            json={"account": "admin_flow", "password": "testpass123"},
        )
        assert login_resp.status_code == 200
        login_body = login_resp.json()
        assert login_body["code"] == 0
        access_token = login_body["data"]["accessToken"]
        assert login_body["data"]["user"]["role"] == "admin"

        auth_headers = auth_header(access_token)

        # ── Session check ─────────────────────────────────────────
        mock_client._mock_db.execute = AsyncMock()
        mock_client._mock_db.execute.side_effect = [
            mock_scalar_result(first_value=admin),
            mock_scalar_result(all_values=[role]),
        ]

        session_resp = await mock_client.get("/api/v1/auth/session", headers=auth_headers)
        assert session_resp.status_code == 200
        session_body = session_resp.json()
        assert session_body["code"] == 0
        assert session_body["data"]["user"]["role"] == "admin"

        # ── Refresh ───────────────────────────────────────────────
        family_id = str(uuid.uuid4())
        refresh_jwt = create_refresh_token(
            data={"sub": "1", "user_type": "admin", "family": family_id, "jti": "200"}
        )
        token_hash = hashlib.sha256(refresh_jwt.encode()).hexdigest()
        existing_token = make_mock_token(
            token_id=200, user_id=1, token_hash=token_hash, family=family_id, is_revoked=False
        )

        mock_client._mock_db.execute = AsyncMock()
        mock_client._mock_db.execute.side_effect = [
            mock_scalar_result(first_value=existing_token),
            mock_scalar_result(all_values=[existing_token]),
        ]

        refresh_resp = await mock_client.post(
            "/api/v1/auth/refresh",
            json={"refreshToken": refresh_jwt},
        )
        assert refresh_resp.status_code == 200

        # ── Logout ────────────────────────────────────────────────
        mock_client._mock_db.execute = AsyncMock(
            return_value=mock_scalar_result(first_value=admin)
        )
        logout_resp = await mock_client.post("/api/v1/auth/logout", headers=auth_headers)
        assert logout_resp.status_code == 200


# ──────────────────────────────────────────────────────────────────────
# 012-register-default-dept: auto-mount integration tests
# ──────────────────────────────────────────────────────────────────────
class TestWechatRegisterAutoMount:
    """T009: WeChat login auto-creates Distributor under default org."""

    async def test_wechat_register_creates_distributor(self, mock_client):
        """New WeChat user → Distributor record created with source_channel=wechat_register."""
        new_user = make_mock_user(user_id=101, openid="o_auto_mount", user_type="promoter")
        default_org = MagicMock()
        default_org.id = 1
        default_org.name = "北京鲁泰服务有限公司"
        default_org.parent_id = None
        default_org.sort_order = 0

        with patch(
            "src.integrations.wechat_client.WechatClient.jscode2session",
            new_callable=AsyncMock,
            return_value={"openid": "o_auto_mount", "session_key": "sk", "unionid": None},
        ):
            mock_client._mock_db.execute = AsyncMock()
            mock_client._mock_db.execute.side_effect = [
                mock_scalar_result(first_value=None),       # User lookup → new user
                mock_scalar_result(first_value=default_org),  # Default org lookup
            ]

            login_resp = await mock_client.post(
                "/api/v1/auth/wechat-login",
                json={"code": "auto_mount_code"},
            )

        assert login_resp.status_code == 200
        body = login_resp.json()
        assert body["code"] == 0
        assert body["data"]["user"]["isNewUser"] is True
        assert body["data"]["distributor"] is not None
        assert body["data"]["distributor"]["orgId"] == "1"
        assert body["data"]["distributor"]["orgRole"] == "member"
        assert body["data"]["distributor"]["sourceChannel"] == "wechat_register"


class TestPhoneRegisterAutoMount:
    """T010: Phone+password registration auto-creates Distributor."""

    async def test_phone_register_creates_distributor(self, mock_client):
        """New phone registration → Distributor created with source_channel=phone_register."""
        default_org = MagicMock()
        default_org.id = 1
        default_org.name = "北京鲁泰服务有限公司"

        mock_client._mock_db.execute = AsyncMock()
        mock_client._mock_db.execute.side_effect = [
            mock_scalar_result(first_value=None),       # Phone duplicate check
            mock_scalar_result(first_value=default_org),  # Default org lookup
        ]

        register_resp = await mock_client.post(
            "/api/v1/auth/distributor-register",
            json={"phone": "13800001234", "password": "password123", "name": "新用户"},
        )

        assert register_resp.status_code == 201
        body = register_resp.json()
        assert body["code"] == 0
        assert body["data"]["distributor"] is not None
        assert body["data"]["distributor"]["sourceChannel"] == "phone_register"
        assert body["data"]["distributor"]["orgRole"] == "member"


class TestExistingDistributorWechatBind:
    """T025: Existing distributor binds WeChat — no duplicate, org unchanged."""

    async def test_existing_phone_match_wechat_bind_preserves_org(self, mock_client):
        """Phone matches existing Distributor → only bind WeChat, org unchanged."""
        from tests.conftest import make_mock_user

        existing_user = make_mock_user(
            user_id=200, openid=None, user_type="distributor", phone="138****8888"
        )
        existing_dist = MagicMock()
        existing_dist.id = 200
        existing_dist.org_id = 5
        existing_dist.org_role = MagicMock()
        existing_dist.org_role.value = "member"
        existing_dist.source_channel = "admin_create"

        with patch(
            "src.integrations.wechat_client.WechatClient.jscode2session",
            new_callable=AsyncMock,
            return_value={"openid": "o_bind_existing", "session_key": "sk", "unionid": None},
        ), patch(
            "src.integrations.wechat_client.WechatClient.get_phone_number",
            new_callable=AsyncMock,
            return_value="138****8888",
        ):
            mock_client._mock_db.execute = AsyncMock()
            mock_client._mock_db.execute.side_effect = [
                mock_scalar_result(first_value=existing_user),   # Phone lookup
                mock_scalar_result(first_value=None),             # OpenID lookup → new
            ]

            login_resp = await mock_client.post(
                "/api/v1/auth/wechat-login",
                json={"code": "bind_code", "phoneCode": "phone_auth_code"},
            )

        assert login_resp.status_code == 200
        body = login_resp.json()
        assert body["code"] == 0
        assert body["data"]["user"]["isNewUser"] is False
        assert body["data"]["distributor"] is not None
        assert body["data"]["distributor"]["sourceChannel"] == "admin_create"
        assert body["data"]["distributor"]["orgId"] == "5"
