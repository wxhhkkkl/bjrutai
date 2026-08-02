"""Contract tests for reconciliation report endpoints (US8).

Tests ensure report generation and export endpoints conform to the unified
response format {code, message, data, requestId, serverTime} and behave
correctly under all documented scenarios.

TDD: These tests are written FIRST and are expected to FAIL until the
implementation is complete.
"""

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token
from tests.conftest import assert_response_envelope, seed_admin


def _admin_token(user_id: int = 99) -> str:
    return create_access_token(data={"sub": str(user_id), "user_type": "admin"})


def _finance_token(user_id: int = 100) -> str:
    return create_access_token(data={"sub": str(user_id), "user_type": "finance"})


def _promoter_token(user_id: int = 1) -> str:
    return create_access_token(data={"sub": str(user_id), "user_type": "promoter"})


def _admin_headers(user_id: int = 99) -> dict:
    return {"Authorization": f"Bearer {_admin_token(user_id)}"}


def _finance_headers(user_id: int = 100) -> dict:
    return {"Authorization": f"Bearer {_finance_token(user_id)}"}


def _promoter_headers(user_id: int = 1) -> dict:
    return {"Authorization": f"Bearer {_promoter_token(user_id)}"}


# ============================================================================
# POST /api/v1/reports/generate
# ============================================================================
class TestGenerateReport:
    """POST /api/v1/reports/generate"""

    async def test_generate_report_returns_envelope(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Generating a report returns properly enveloped response."""
        await seed_admin(db_session, username="admin_test", password_plain="testpass123")

        resp = await client.post(
            "/api/v1/reports/generate",
            json={
                "startDate": "2026-07-01",
                "endDate": "2026-07-31",
                "dimensions": ["binding", "revenue"],
            },
            headers=_admin_headers(),
        )

        assert resp.status_code == 200
        body = resp.json()
        assert_response_envelope(body)
        assert body["code"] == 0
        data = body["data"]
        assert "reportId" in data
        assert "generatedAt" in data
        assert "dimensions" in data

    async def test_generate_with_all_dimensions(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Generating a report with all four dimensions succeeds."""
        await seed_admin(db_session, username="admin_test", password_plain="testpass123")

        resp = await client.post(
            "/api/v1/reports/generate",
            json={
                "startDate": "2026-06-01",
                "endDate": "2026-07-31",
                "dimensions": ["binding", "revenue", "discount", "allocation"],
            },
            headers=_admin_headers(),
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "reportId" in data
        assert data["reportId"] is not None

    async def test_future_date_rejected(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Generating a report with a future end date returns 400."""
        await seed_admin(db_session, username="admin_test", password_plain="testpass123")

        resp = await client.post(
            "/api/v1/reports/generate",
            json={
                "startDate": "2099-01-01",
                "endDate": "2099-12-31",
                "dimensions": ["revenue"],
            },
            headers=_admin_headers(),
        )

        assert resp.status_code == 400

    async def test_range_too_large_rejected(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Generating a report with date range > 1 year returns 400."""
        await seed_admin(db_session, username="admin_test", password_plain="testpass123")

        resp = await client.post(
            "/api/v1/reports/generate",
            json={
                "startDate": "2025-01-01",
                "endDate": "2026-12-31",
                "dimensions": ["revenue"],
            },
            headers=_admin_headers(),
        )

        assert resp.status_code == 400

    async def test_empty_dimensions_rejected(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Generating a report with no dimensions returns 422."""
        await seed_admin(db_session, username="admin_test", password_plain="testpass123")

        resp = await client.post(
            "/api/v1/reports/generate",
            json={
                "startDate": "2026-07-01",
                "endDate": "2026-07-31",
                "dimensions": [],
            },
            headers=_admin_headers(),
        )

        assert resp.status_code == 422

    async def test_invalid_dimension_rejected(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Generating a report with an invalid dimension returns 422."""
        await seed_admin(db_session, username="admin_test", password_plain="testpass123")

        resp = await client.post(
            "/api/v1/reports/generate",
            json={
                "startDate": "2026-07-01",
                "endDate": "2026-07-31",
                "dimensions": ["invalid_dim"],
            },
            headers=_admin_headers(),
        )

        assert resp.status_code == 422

    async def test_requires_admin_or_finance_role(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Distributor cannot generate reports (returns 403)."""
        resp = await client.post(
            "/api/v1/reports/generate",
            json={
                "startDate": "2026-07-01",
                "endDate": "2026-07-31",
                "dimensions": ["revenue"],
            },
            headers=_promoter_headers(),
        )

        assert resp.status_code == 403

    async def test_finance_role_can_generate(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Finance role can generate reports."""
        await seed_admin(db_session, username="admin_test", password_plain="testpass123")

        resp = await client.post(
            "/api/v1/reports/generate",
            json={
                "startDate": "2026-07-01",
                "endDate": "2026-07-31",
                "dimensions": ["revenue"],
            },
            headers=_finance_headers(),
        )

        assert resp.status_code == 200

    async def test_requires_auth(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Calling without auth returns 401."""
        resp = await client.post(
            "/api/v1/reports/generate",
            json={
                "startDate": "2026-07-01",
                "endDate": "2026-07-31",
                "dimensions": ["revenue"],
            },
        )
        assert resp.status_code == 401


# ============================================================================
# GET /api/v1/reports
# ============================================================================
class TestListReports:
    """GET /api/v1/reports"""

    async def test_list_reports_returns_envelope(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Listing reports returns properly enveloped response."""
        await seed_admin(db_session, username="admin_test", password_plain="testpass123")

        # Generate a report first
        await client.post(
            "/api/v1/reports/generate",
            json={
                "startDate": "2026-07-01",
                "endDate": "2026-07-31",
                "dimensions": ["revenue"],
            },
            headers=_admin_headers(),
        )

        resp = await client.get("/api/v1/reports", headers=_admin_headers())

        assert resp.status_code == 200
        body = resp.json()
        assert_response_envelope(body)
        assert body["code"] == 0
        data = body["data"]
        assert "items" in data
        assert isinstance(data["items"], list)
        assert len(data["items"]) >= 1

    async def test_list_reports_includes_metadata(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Each report in the list includes metadata fields."""
        await seed_admin(db_session, username="admin_test", password_plain="testpass123")

        await client.post(
            "/api/v1/reports/generate",
            json={
                "startDate": "2026-07-01",
                "endDate": "2026-07-31",
                "dimensions": ["revenue"],
            },
            headers=_admin_headers(),
        )

        resp = await client.get("/api/v1/reports", headers=_admin_headers())

        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        for item in items:
            assert "reportId" in item
            assert "generatedAt" in item
            assert "dateRange" in item
            assert "dimensions" in item

    async def test_list_requires_admin_or_finance(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Promoters cannot list reports (returns 403)."""
        resp = await client.get("/api/v1/reports", headers=_promoter_headers())
        assert resp.status_code == 403

    async def test_list_requires_auth(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Calling without auth returns 401."""
        resp = await client.get("/api/v1/reports")
        assert resp.status_code == 401


# ============================================================================
# GET /api/v1/reports/{id}
# ============================================================================
class TestReportDetail:
    """GET /api/v1/reports/{id}"""

    async def test_detail_returns_envelope(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Report detail returns properly enveloped response."""
        await seed_admin(db_session, username="admin_test", password_plain="testpass123")

        gen_resp = await client.post(
            "/api/v1/reports/generate",
            json={
                "startDate": "2026-07-01",
                "endDate": "2026-07-31",
                "dimensions": ["binding", "revenue"],
            },
            headers=_admin_headers(),
        )
        report_id = gen_resp.json()["data"]["reportId"]

        resp = await client.get(f"/api/v1/reports/{report_id}", headers=_admin_headers())

        assert resp.status_code == 200
        body = resp.json()
        assert_response_envelope(body)
        assert body["code"] == 0
        data = body["data"]
        assert "reportId" in data
        assert "dimensions" in data
        assert "sections" in data

    async def test_detail_includes_binding_summary(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Report detail includes binding summary section when requested."""
        await seed_admin(db_session, username="admin_test", password_plain="testpass123")

        gen_resp = await client.post(
            "/api/v1/reports/generate",
            json={
                "startDate": "2026-07-01",
                "endDate": "2026-07-31",
                "dimensions": ["binding"],
            },
            headers=_admin_headers(),
        )
        report_id = gen_resp.json()["data"]["reportId"]

        resp = await client.get(f"/api/v1/reports/{report_id}", headers=_admin_headers())

        assert resp.status_code == 200
        data = resp.json()["data"]
        sections = data["sections"]
        assert "binding" in sections

    async def test_detail_includes_revenue_summary(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Report detail includes revenue summary section when requested."""
        await seed_admin(db_session, username="admin_test", password_plain="testpass123")

        gen_resp = await client.post(
            "/api/v1/reports/generate",
            json={
                "startDate": "2026-07-01",
                "endDate": "2026-07-31",
                "dimensions": ["revenue"],
            },
            headers=_admin_headers(),
        )
        report_id = gen_resp.json()["data"]["reportId"]

        resp = await client.get(f"/api/v1/reports/{report_id}", headers=_admin_headers())

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "revenue" in data["sections"]

    async def test_detail_not_found(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Non-existent report returns 404."""
        await seed_admin(db_session, username="admin_test", password_plain="testpass123")

        resp = await client.get("/api/v1/reports/nonexistent-id", headers=_admin_headers())
        assert resp.status_code == 404

    async def test_detail_requires_admin_or_finance(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Distributor cannot access report detail (returns 403)."""
        resp = await client.get("/api/v1/reports/1", headers=_promoter_headers())
        assert resp.status_code == 403


# ============================================================================
# GET /api/v1/reports/{id}/export
# ============================================================================
class TestExportReport:
    """GET /api/v1/reports/{id}/export"""

    async def test_export_returns_excel_content_type(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Export returns an Excel file with proper Content-Type."""
        await seed_admin(db_session, username="admin_test", password_plain="testpass123")

        gen_resp = await client.post(
            "/api/v1/reports/generate",
            json={
                "startDate": "2026-07-01",
                "endDate": "2026-07-31",
                "dimensions": ["revenue", "discount"],
            },
            headers=_admin_headers(),
        )
        report_id = gen_resp.json()["data"]["reportId"]

        resp = await client.get(
            f"/api/v1/reports/{report_id}/export",
            headers=_admin_headers(),
        )

        assert resp.status_code == 200
        content_type = resp.headers.get("content-type", "")
        assert "spreadsheet" in content_type.lower() or "excel" in content_type.lower() or "xlsx" in content_type.lower(), \
            f"Expected Excel content-type, got: {content_type}"

    async def test_export_returns_binary_data(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Export returns non-empty binary response body."""
        await seed_admin(db_session, username="admin_test", password_plain="testpass123")

        gen_resp = await client.post(
            "/api/v1/reports/generate",
            json={
                "startDate": "2026-07-01",
                "endDate": "2026-07-31",
                "dimensions": ["revenue"],
            },
            headers=_admin_headers(),
        )
        report_id = gen_resp.json()["data"]["reportId"]

        resp = await client.get(
            f"/api/v1/reports/{report_id}/export",
            headers=_admin_headers(),
        )

        assert resp.status_code == 200
        assert len(resp.content) > 0

    async def test_export_nonexistent_report_returns_404(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Exporting a non-existent report returns 404."""
        await seed_admin(db_session, username="admin_test", password_plain="testpass123")

        resp = await client.get(
            "/api/v1/reports/nonexistent-id/export",
            headers=_admin_headers(),
        )
        assert resp.status_code == 404

    async def test_export_requires_admin_or_finance(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Distributor cannot export reports (returns 403)."""
        resp = await client.get("/api/v1/reports/1/export", headers=_promoter_headers())
        assert resp.status_code == 403

    async def test_export_requires_auth(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Calling without auth returns 401."""
        resp = await client.get("/api/v1/reports/1/export")
        assert resp.status_code == 401
