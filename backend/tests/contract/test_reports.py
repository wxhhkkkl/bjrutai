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


# ============================================================================
# Settlement report records (010, FR-005/FR-006/FR-011)
# ============================================================================
async def _seed_settlement_report(
    db: AsyncSession,
    *,
    period: str = "2026-07",
    status: str = "pending",
    generated_by: str = "User 7",
) -> str:
    """Insert a performance_settlement report record and return its id."""
    from src.models.commission_result import CommissionResult
    from src.models.distributor import Distributor, OrgRole
    from src.models.organization import Organization
    from src.models.performance_rule import RuleType
    from src.models.report import Report

    org = Organization(name="总部", org_type="headquarters", level=1, sort_order=0)
    db.add(org)
    await db.flush()
    await db.refresh(org)

    dist = Distributor(user_id=77, org_id=org.id, org_role=OrgRole.MEMBER)
    db.add(dist)
    await db.flush()
    await db.refresh(dist)

    db.add(CommissionResult(
        period=period, distributor_id=dist.id, org_id=org.id,
        rule_type=RuleType.INTRA_ORG, base_cent=800000, ratio="0.050000",
        commission_cent=40000, rule_snapshot={"ruleType": "intra_org", "tiers": [], "version": 1},
    ))
    await db.flush()

    report = Report(
        id="settlement-report-1",
        start_date=f"{period}-01",
        end_date=f"{period}-31",
        dimensions=["performance"],
        sections={"performance": {
            "title": "绩效核算",
            "summary": {"周期": period, "状态": "待审核", "核算人数": 1, "提成总额(元)": "400.00", "组织数": 1},
            "details": [{"组织": "总部", "姓名": "推广员", "提成类型": "组织内提成", "计算基数(元)": "8000.00", "比例": "5.00%", "提成金额(元)": "400.00"}],
        }},
        generated_by=generated_by,
        source="performance_settlement",
        period=period,
        status=status,
    )
    db.add(report)
    await db.flush()
    return report.id


def _settle_token(user_id: int = 99) -> str:
    return create_access_token(
        data={"sub": str(user_id), "user_type": "admin", "permissions": ["sharing_rules.read", "performance.settle"]}
    )


def _read_only_token(user_id: int = 99) -> str:
    return create_access_token(
        data={"sub": str(user_id), "user_type": "admin", "permissions": ["reports.read"]}
    )


class TestSettlementReportList:
    """GET /api/v1/reports with settlement source records (FR-005/FR-011)."""

    async def test_list_includes_settlement_source_fields(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Settlement report list item carries source/period/status."""
        await seed_admin(db_session, username="admin_test", password_plain="testpass123")
        await _seed_settlement_report(db_session)

        resp = await client.get(
            "/api/v1/reports", headers={"Authorization": f"Bearer {_settle_token()}"}
        )
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        settlement_items = [i for i in items if i.get("source") == "performance_settlement"]
        assert len(settlement_items) == 1
        item = settlement_items[0]
        assert item["period"] == "2026-07"
        assert item["status"] == "pending"

    async def test_list_filters_settlement_without_read_permission(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Caller without sharing_rules.read does not see settlement reports (FR-011)."""
        await seed_admin(db_session, username="admin_test", password_plain="testpass123")
        await _seed_settlement_report(db_session)

        resp = await client.get(
            "/api/v1/reports", headers={"Authorization": f"Bearer {_read_only_token()}"}
        )
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        settlement_items = [i for i in items if i.get("source") == "performance_settlement"]
        assert len(settlement_items) == 0


class TestSettlementReportDetail:
    """GET /api/v1/reports/{id} for settlement reports (FR-006)."""

    async def test_detail_includes_performance_section(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Settlement report detail carries performance section + status."""
        await seed_admin(db_session, username="admin_test", password_plain="testpass123")
        report_id = await _seed_settlement_report(db_session)

        resp = await client.get(
            f"/api/v1/reports/{report_id}", headers={"Authorization": f"Bearer {_settle_token()}"}
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["source"] == "performance_settlement"
        assert data["status"] == "pending"
        assert "performance" in data["sections"]
        assert data["sections"]["performance"]["summary"]["核算人数"] == 1

    async def test_detail_denied_without_read_permission(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Settlement report detail returns 403 without sharing_rules.read (FR-011)."""
        await seed_admin(db_session, username="admin_test", password_plain="testpass123")
        report_id = await _seed_settlement_report(db_session)

        resp = await client.get(
            f"/api/v1/reports/{report_id}", headers={"Authorization": f"Bearer {_read_only_token()}"}
        )
        assert resp.status_code == 403


class TestSettlementReportExport:
    """GET /api/v1/reports/{id}/export for settlement reports (FR-012)."""

    async def test_export_returns_excel(self, client: AsyncClient, db_session: AsyncSession):
        """Settlement report exports an Excel file."""
        await seed_admin(db_session, username="admin_test", password_plain="testpass123")
        report_id = await _seed_settlement_report(db_session)

        resp = await client.get(
            f"/api/v1/reports/{report_id}/export", headers={"Authorization": f"Bearer {_settle_token()}"}
        )
        assert resp.status_code == 200
        content_type = resp.headers.get("content-type", "")
        assert "spreadsheet" in content_type.lower() or "excel" in content_type.lower() or "xlsx" in content_type.lower()

    async def test_export_denied_without_read_permission(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Settlement report export returns 403 without sharing_rules.read (FR-011)."""
        await seed_admin(db_session, username="admin_test", password_plain="testpass123")
        report_id = await _seed_settlement_report(db_session)

        resp = await client.get(
            f"/api/v1/reports/{report_id}/export", headers={"Authorization": f"Bearer {_read_only_token()}"}
        )
        assert resp.status_code == 403


# ============================================================================
# Settlement report status sync on review/reject/recompute (010, FR-005/FR-007/FR-009)
# ============================================================================
def _settle_only_token(user_id: int = 99) -> str:
    return create_access_token(
        data={"sub": str(user_id), "user_type": "admin", "permissions": ["performance.settle"]}
    )


class TestSettlementReportStatusSync:
    """Review/reject/recompute update the settlement report record's status."""

    async def test_review_updates_report_status(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """review → settlement report status becomes reviewed (FR-005)."""
        from src.models.performance_settlement import PerformanceSettlement, SettlementStatus
        from src.models.report import Report
        from sqlalchemy import select

        await seed_admin(db_session, username="admin_test", password_plain="testpass123")
        report_id = await _seed_settlement_report(db_session, period="2026-07", status="pending")
        db_session.add(PerformanceSettlement(period="2026-07", status=SettlementStatus.PENDING))
        await db_session.flush()

        resp = await client.post(
            "/api/v1/admin/performance/settlements/2026-07/review",
            headers={"Authorization": f"Bearer {_settle_only_token()}"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "reviewed"

        report = (await db_session.execute(select(Report).where(Report.id == report_id))).scalars().first()
        assert report.status == "reviewed"

    async def test_reject_updates_report_status(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """reject with reason → settlement report status becomes rejected (FR-007)."""
        from src.models.performance_settlement import PerformanceSettlement, SettlementStatus
        from src.models.report import Report
        from sqlalchemy import select

        await seed_admin(db_session, username="admin_test", password_plain="testpass123")
        report_id = await _seed_settlement_report(db_session, period="2026-07", status="pending")
        db_session.add(PerformanceSettlement(period="2026-07", status=SettlementStatus.PENDING))
        await db_session.flush()

        resp = await client.post(
            "/api/v1/admin/performance/settlements/2026-07/reject",
            json={"reason": "核对有误"},
            headers={"Authorization": f"Bearer {_settle_only_token()}"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "rejected"

        report = (await db_session.execute(select(Report).where(Report.id == report_id))).scalars().first()
        assert report.status == "rejected"

    async def test_recompute_updates_report_status(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """recompute rejected → settlement report status becomes pending (FR-009)."""
        from src.models.performance_settlement import PerformanceSettlement, SettlementStatus
        from src.models.report import Report
        from sqlalchemy import select

        await seed_admin(db_session, username="admin_test", password_plain="testpass123")
        report_id = await _seed_settlement_report(db_session, period="2026-07", status="rejected")
        db_session.add(PerformanceSettlement(period="2026-07", status=SettlementStatus.REJECTED, reject_reason="核对有误"))
        await db_session.flush()

        resp = await client.post(
            "/api/v1/admin/performance/settlements/2026-07/recompute",
            headers={"Authorization": f"Bearer {_settle_only_token()}"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "pending"

        report = (await db_session.execute(select(Report).where(Report.id == report_id))).scalars().first()
        assert report.status == "pending"
