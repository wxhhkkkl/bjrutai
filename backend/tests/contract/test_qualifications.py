"""Contract tests for Qualification upload and review endpoints (US2)."""
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import (
    admin_auth_headers,
    make_access_token,
    seed_hierarchy_node,
    seed_promoter,
    seed_qualification,
    seed_user,
)


_setup_counter = 0


async def _setup_promoter(db_session: AsyncSession, user_type: str = "promoter") -> tuple[int, int, str]:
    """Create user + hierarchy_node + promoter and return (user_id, distributor_id, token)."""
    global _setup_counter
    _setup_counter += 1
    suffix = str(_setup_counter)
    user_id = await seed_user(
        db_session, openid=f"qual_test_{suffix}", user_type=user_type, name=f"测试用户{suffix}"
    )
    node_id = await seed_hierarchy_node(db_session, name=f"节点_{suffix}", node_type="promoter", level=2)
    distributor_id = await seed_promoter(db_session, user_id=user_id, node_id=node_id)
    token = make_access_token(user_id=user_id, user_type=user_type)
    return user_id, distributor_id, token


# ============================================================================
# POST /api/v1/qualification-files/upload-token
# ============================================================================
class TestUploadToken:
    async def test_valid_request_returns_upload_token(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        _, _, token = await _setup_promoter(db_session)
        payload = {"fileName": "license.jpg", "fileType": "image/jpeg", "fileSize": 1024000}
        resp = await client.post(
            "/api/v1/qualification-files/upload-token",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert "fileId" in data["data"]
        assert "uploadUrl" in data["data"]
        assert "expiresAt" in data["data"]

    async def test_invalid_file_type_returns_error(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        _, _, token = await _setup_promoter(db_session)
        payload = {"fileName": "doc.docx", "fileType": "application/msword", "fileSize": 1024000}
        resp = await client.post(
            "/api/v1/qualification-files/upload-token",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] != 0

    async def test_oversized_file_returns_error(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        _, _, token = await _setup_promoter(db_session)
        # > 10MB
        payload = {"fileName": "large.jpg", "fileType": "image/jpeg", "fileSize": 11 * 1024 * 1024}
        resp = await client.post(
            "/api/v1/qualification-files/upload-token",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] != 0

    async def test_missing_auth_returns_401(self, client: AsyncClient):
        payload = {"fileName": "license.jpg", "fileType": "image/jpeg", "fileSize": 1024000}
        resp = await client.post("/api/v1/qualification-files/upload-token", json=payload)
        assert resp.status_code in (401, 403)

    async def test_invalid_filename_extension_returns_error(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        _, _, token = await _setup_promoter(db_session)
        payload = {"fileName": "noext", "fileType": "image/jpeg", "fileSize": 1024000}
        resp = await client.post(
            "/api/v1/qualification-files/upload-token",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code in (400, 422)


# ============================================================================
# POST /api/v1/qualifications (submit)
# ============================================================================
class TestSubmitQualification:
    async def test_submit_with_file_id_success(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        _, distributor_id, token = await _setup_promoter(db_session)
        payload = {
            "qualificationType": "enterprise",
            "fileId": "cos_file_key_001",
            "fileName": "business_license.jpg",
            "fileType": "image/jpeg",
            "fileSize": 2048000,
        }
        resp = await client.post(
            "/api/v1/qualifications",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert data["data"]["status"] == "reviewing"
        assert "qualificationId" in data["data"]

    async def test_missing_file_id_returns_error(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        _, _, token = await _setup_promoter(db_session)
        payload = {"qualificationType": "enterprise"}
        resp = await client.post(
            "/api/v1/qualifications",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422

    async def test_duplicate_submit_while_reviewing_returns_conflict(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        _, distributor_id, token = await _setup_promoter(db_session)
        payload = {
            "qualificationType": "enterprise",
            "fileId": "cos_file_key_002",
            "fileName": "license.pdf",
            "fileType": "application/pdf",
            "fileSize": 512000,
        }
        # First submission
        resp1 = await client.post(
            "/api/v1/qualifications",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp1.status_code == 200

        # Second submission with same type while first is reviewing
        resp2 = await client.post(
            "/api/v1/qualifications",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp2.status_code == 409

    async def test_submit_requires_auth(self, client: AsyncClient):
        payload = {"qualificationType": "enterprise", "fileId": "cos_key"}
        resp = await client.post("/api/v1/qualifications", json=payload)
        assert resp.status_code in (401, 403)


# ============================================================================
# GET /api/v1/qualifications/current
# ============================================================================
class TestGetCurrentQualification:
    async def test_no_qualification_returns_empty(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        _, _, token = await _setup_promoter(db_session)
        resp = await client.get(
            "/api/v1/qualifications/current",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert data["data"]["items"] == []

    async def test_reviewing_qualification_returned(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user_id, distributor_id, token = await _setup_promoter(db_session)
        qual_id = await seed_qualification(
            db_session,
            distributor_id=distributor_id,
            qualification_type="enterprise",
            status="reviewing",
            file_id="cos_key_reviewing",
            file_name="license.jpg",
            file_type="image/jpeg",
            file_size=1024000,
            submitted_at=datetime.now(timezone.utc),
        )
        resp = await client.get(
            "/api/v1/qualifications/current",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        items = data["data"]["items"]
        assert len(items) == 1
        assert items[0]["status"] == "reviewing"

    async def test_approved_qualification_returned(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user_id, distributor_id, token = await _setup_promoter(db_session)
        qual_id = await seed_qualification(
            db_session,
            distributor_id=distributor_id,
            qualification_type="enterprise",
            status="approved",
            file_id="cos_key_approved",
            file_name="license.pdf",
            file_type="application/pdf",
            file_size=512000,
            submitted_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            approved_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
        )
        resp = await client.get(
            "/api/v1/qualifications/current",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["status"] == "approved"

    async def test_rejected_qualification_returned(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user_id, distributor_id, token = await _setup_promoter(db_session)
        qual_id = await seed_qualification(
            db_session,
            distributor_id=distributor_id,
            qualification_type="enterprise",
            status="rejected",
            file_id="cos_key_rejected",
            file_name="license.jpg",
            file_type="image/jpeg",
            file_size=1024000,
            submitted_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            rejected_reason="图片不清晰",
        )
        resp = await client.get(
            "/api/v1/qualifications/current",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["status"] == "rejected"

    async def test_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/qualifications/current")
        assert resp.status_code in (401, 403)


# ============================================================================
# PUT /api/v1/qualifications/{id} (resubmit after reject)
# ============================================================================
class TestUpdateQualification:
    async def test_resubmit_after_reject_success(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user_id, distributor_id, token = await _setup_promoter(db_session)
        qual_id = await seed_qualification(
            db_session,
            distributor_id=distributor_id,
            qualification_type="enterprise",
            status="rejected",
            file_id="old_key",
            file_name="old.jpg",
            file_type="image/jpeg",
            file_size=1024000,
            version=1,
            submitted_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            rejected_reason="图片模糊",
        )
        payload = {
            "fileId": "new_cos_key",
            "fileName": "new_clear.jpg",
            "fileType": "image/jpeg",
            "fileSize": 2048000,
            "version": 1,
        }
        resp = await client.put(
            f"/api/v1/qualifications/{qual_id}",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert data["data"]["status"] == "reviewing"

    async def test_version_conflict_returns_409(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user_id, distributor_id, token = await _setup_promoter(db_session)
        qual_id = await seed_qualification(
            db_session,
            distributor_id=distributor_id,
            qualification_type="enterprise",
            status="rejected",
            file_id="old_key",
            file_name="old.jpg",
            file_type="image/jpeg",
            file_size=1024000,
            version=3,
            submitted_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            rejected_reason="图片模糊",
        )
        payload = {
            "fileId": "new_cos_key",
            "fileName": "new.jpg",
            "fileType": "image/jpeg",
            "fileSize": 2048000,
            "version": 1,
        }
        resp = await client.put(
            f"/api/v1/qualifications/{qual_id}",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 409

    async def test_cannot_update_approved_qualification(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user_id, distributor_id, token = await _setup_promoter(db_session)
        qual_id = await seed_qualification(
            db_session,
            distributor_id=distributor_id,
            qualification_type="enterprise",
            status="approved",
            file_id="approved_key",
            file_name="approved.jpg",
            file_type="image/jpeg",
            file_size=1024000,
            version=1,
            submitted_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            approved_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
        )
        payload = {"fileId": "new_key", "fileName": "new.jpg", "fileType": "image/jpeg",
                    "fileSize": 2048000, "version": 1}
        resp = await client.put(
            f"/api/v1/qualifications/{qual_id}",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400

    async def test_requires_auth(self, client: AsyncClient, db_session: AsyncSession):
        _, distributor_id, _ = await _setup_promoter(db_session)
        qual_id = await seed_qualification(
            db_session, distributor_id=distributor_id, status="rejected",
            file_id="k", file_name="f.jpg", file_type="image/jpeg", file_size=1000,
            version=1, submitted_at=datetime.now(timezone.utc),
        )
        resp = await client.put(
            f"/api/v1/qualifications/{qual_id}",
            json={"fileId": "k2", "fileName": "f2.jpg", "fileType": "image/jpeg",
                  "fileSize": 2000, "version": 1},
        )
        assert resp.status_code in (401, 403)

    async def test_nonexistent_qualification_returns_404(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        _, _, token = await _setup_promoter(db_session)
        resp = await client.put(
            "/api/v1/qualifications/99999",
            json={"fileId": "k", "fileName": "f.jpg", "fileType": "image/jpeg",
                  "fileSize": 1000, "version": 1},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404


# ============================================================================
# GET /api/v1/qualifications/{id}/reviews
# ============================================================================
class TestQualificationReviews:
    async def test_returns_empty_for_unreviewed(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user_id, distributor_id, token = await _setup_promoter(db_session)
        qual_id = await seed_qualification(
            db_session, distributor_id=distributor_id, status="reviewing",
            file_id="k", file_name="f.jpg", file_type="image/jpeg", file_size=1000,
            submitted_at=datetime.now(timezone.utc),
        )
        resp = await client.get(
            f"/api/v1/qualifications/{qual_id}/reviews",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["items"] == []

    async def test_requires_auth(self, client: AsyncClient, db_session: AsyncSession):
        _, distributor_id, _ = await _setup_promoter(db_session)
        qual_id = await seed_qualification(
            db_session, distributor_id=distributor_id, status="reviewing",
            file_id="k", file_name="f.jpg", file_type="image/jpeg", file_size=1000,
            submitted_at=datetime.now(timezone.utc),
        )
        resp = await client.get(f"/api/v1/qualifications/{qual_id}/reviews")
        assert resp.status_code in (401, 403)


# ============================================================================
# POST /api/v1/admin/qualifications/{id}/review
# ============================================================================
class TestAdminReview:
    async def test_approve_qualification_success(
        self, client: AsyncClient, db_session: AsyncSession, admin_auth_headers: dict
    ):
        user_id, distributor_id, _ = await _setup_promoter(db_session)
        qual_id = await seed_qualification(
            db_session, distributor_id=distributor_id, status="reviewing",
            file_id="k", file_name="f.jpg", file_type="image/jpeg", file_size=1000,
            submitted_at=datetime.now(timezone.utc),
        )
        resp = await client.post(
            f"/api/v1/admin/qualifications/{qual_id}/review",
            json={"action": "approve", "comment": "审核通过"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert data["data"]["status"] == "approved"

    async def test_reject_with_reason(
        self, client: AsyncClient, db_session: AsyncSession, admin_auth_headers: dict
    ):
        user_id, distributor_id, _ = await _setup_promoter(db_session)
        qual_id = await seed_qualification(
            db_session, distributor_id=distributor_id, status="reviewing",
            file_id="k", file_name="f.jpg", file_type="image/jpeg", file_size=1000,
            submitted_at=datetime.now(timezone.utc),
        )
        resp = await client.post(
            f"/api/v1/admin/qualifications/{qual_id}/review",
            json={"action": "reject", "comment": "图片不清晰，请重新上传"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert data["data"]["status"] == "rejected"

    async def test_already_reviewed_returns_error(
        self, client: AsyncClient, db_session: AsyncSession, admin_auth_headers: dict
    ):
        user_id, distributor_id, _ = await _setup_promoter(db_session)
        qual_id = await seed_qualification(
            db_session, distributor_id=distributor_id, status="approved",
            file_id="k", file_name="f.jpg", file_type="image/jpeg", file_size=1000,
            submitted_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            approved_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
        )
        resp = await client.post(
            f"/api/v1/admin/qualifications/{qual_id}/review",
            json={"action": "approve", "comment": "already done"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 400

    async def test_missing_action_returns_error(
        self, client: AsyncClient, db_session: AsyncSession, admin_auth_headers: dict
    ):
        user_id, distributor_id, _ = await _setup_promoter(db_session)
        qual_id = await seed_qualification(
            db_session, distributor_id=distributor_id, status="reviewing",
            file_id="k", file_name="f.jpg", file_type="image/jpeg", file_size=1000,
            submitted_at=datetime.now(timezone.utc),
        )
        resp = await client.post(
            f"/api/v1/admin/qualifications/{qual_id}/review",
            json={"comment": "no action"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 422

    async def test_requires_admin_auth(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user_id, distributor_id, token = await _setup_promoter(db_session)
        qual_id = await seed_qualification(
            db_session, distributor_id=distributor_id, status="reviewing",
            file_id="k", file_name="f.jpg", file_type="image/jpeg", file_size=1000,
            submitted_at=datetime.now(timezone.utc),
        )
        resp = await client.post(
            f"/api/v1/admin/qualifications/{qual_id}/review",
            json={"action": "approve", "comment": "通过"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code in (401, 403)

    async def test_nonexistent_qualification_returns_404(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        resp = await client.post(
            "/api/v1/admin/qualifications/99999/review",
            json={"action": "approve", "comment": "通过"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 404


# ============================================================================
# POST /api/v1/qualifications/draft
# ============================================================================
class TestSaveDraft:
    async def test_save_draft_success(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        _, distributor_id, token = await _setup_promoter(db_session)
        payload = {
            "qualificationType": "enterprise",
            "fileId": "draft_file_key",
            "fileName": "draft_license.jpg",
            "fileType": "image/jpeg",
            "fileSize": 1024000,
        }
        resp = await client.post(
            "/api/v1/qualifications/draft",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert data["data"]["status"] == "draft"

    async def test_cannot_draft_while_reviewing(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user_id, distributor_id, token = await _setup_promoter(db_session)
        await seed_qualification(
            db_session, distributor_id=distributor_id, status="reviewing",
            qualification_type="enterprise",
            file_id="existing_key", file_name="existing.jpg",
            file_type="image/jpeg", file_size=1024000,
            submitted_at=datetime.now(timezone.utc),
        )
        payload = {
            "qualificationType": "enterprise",
            "fileId": "draft_key_2",
            "fileName": "draft2.jpg",
            "fileType": "image/jpeg",
            "fileSize": 512000,
        }
        resp = await client.post(
            "/api/v1/qualifications/draft",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 409

    async def test_requires_auth(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/qualifications/draft",
            json={"qualificationType": "enterprise", "fileId": "k", "fileName": "f.jpg",
                  "fileType": "image/jpeg", "fileSize": 1000},
        )
        assert resp.status_code in (401, 403)


# ============================================================================
# GET /api/v1/admin/qualifications (list pending for admin)
# ============================================================================
class TestAdminListQualifications:
    async def test_list_pending_qualifications(
        self, client: AsyncClient, db_session: AsyncSession, admin_auth_headers: dict
    ):
        # Create two promoters with reviewing qualifications
        u1, p1, _ = await _setup_promoter(db_session)
        u2, p2, _ = await _setup_promoter(db_session)

        await seed_qualification(
            db_session, distributor_id=p1, status="reviewing", qualification_type="enterprise",
            file_id="k1", file_name="f1.jpg", file_type="image/jpeg", file_size=1000,
            submitted_at=datetime.now(timezone.utc),
        )
        await seed_qualification(
            db_session, distributor_id=p2, status="reviewing", qualification_type="individual",
            file_id="k2", file_name="f2.jpg", file_type="image/jpeg", file_size=1000,
            submitted_at=datetime.now(timezone.utc),
        )
        # Also create an approved one that should not appear in pending list
        await seed_qualification(
            db_session, distributor_id=p1, status="approved", qualification_type="enterprise",
            file_id="k3", file_name="f3.pdf", file_type="application/pdf", file_size=2000,
            submitted_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            approved_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
        )

        resp = await client.get(
            "/api/v1/admin/qualifications",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        # Should only return reviewing qualifications
        statuses = [item["status"] for item in items]
        assert all(s == "reviewing" for s in statuses)
        assert len(items) >= 2

    async def test_requires_admin_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/admin/qualifications")
        assert resp.status_code in (401, 403)
