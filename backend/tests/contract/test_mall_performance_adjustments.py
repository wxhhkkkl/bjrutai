"""Admin adjustment fields and review permission contract."""

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.mall_operations import MallCommand
from src.models.performance_adjustment import PerformanceAdjustment
from src.models.performance_rule import RuleType
from src.models.role import Role
from src.models.user import admin_account_roles
from tests.conftest import make_access_token, seed_admin
from tests.mall_consumption_fixtures import add_frozen_evidence, performance_context
from src.services.mall_command_service import canonical_payload_hash


async def _admin_identity_and_headers(
    db: AsyncSession, *permissions: str
) -> tuple[int, dict]:
    admin_id = await seed_admin(db, username=f"perf-adjustment-{uuid4().hex[:12]}")
    role = Role(
        name=f"绩效差额测试角色-{admin_id}",
        permissions={"permissions": list(permissions)},
    )
    db.add(role)
    await db.flush()
    await db.execute(
        admin_account_roles.insert().values(admin_account_id=admin_id, role_id=role.id)
    )
    await db.commit()

    token = make_access_token(user_id=admin_id, user_type="admin")
    return admin_id, {"Authorization": f"Bearer {token}"}


async def _headers(db: AsyncSession, *permissions: str) -> dict:
    _admin_id, headers = await _admin_identity_and_headers(db, *permissions)
    return headers


def _data(response):
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["code"] == 0
    return body["data"]


async def _seed_adjustment(db: AsyncSession) -> tuple[int, int]:
    context = await performance_context(db)
    evidence = await add_frozen_evidence(
        db,
        context,
        rule_snapshot={"tiers": [{"minCent": 1000000, "ratio": 0.08}], "version": 4},
        original_base_cent=800000,
        original_commission_cent=0,
        result_presence="not_generated",
        result_absence_reason="below_first_tier",
    )
    adjustment = PerformanceAdjustment(
        adjustment_no=f"ADJ-AC052-{uuid4().hex[:8]}",
        origin_period="2026-07",
        origin_result_id=None,
        evidence_id=evidence.id,
        trigger_source_type="mall",
        trigger_source_id=1001,
        trigger_version=2,
        beneficiary_id=context["distributorId"],
        rule_type=RuleType.INTRA_ORG.value,
        original_commission_cent=0,
        replayed_commission_cent=88000,
        prior_confirmed_adjustment_cent=0,
        delta_cent=88000,
        status="proposed",
        remaining_cent=88000,
    )
    db.add(adjustment)
    await db.flush()
    return adjustment.id, evidence.id


@pytest.mark.asyncio
async def test_detail_keeps_evidence_anchor_when_origin_result_row_was_never_created(
    client: AsyncClient, db_session: AsyncSession
):
    adjustment_id, evidence_id = await _seed_adjustment(db_session)
    headers = await _headers(db_session, "sharing_rules.read")

    data = _data(
        await client.get(
            f"/api/v1/admin/performance/adjustments/{adjustment_id}",
            headers=headers,
        )
    )
    assert data["originEvidenceId"] == str(evidence_id)
    assert data["originResultPresence"] == "not_generated"
    assert data["originResultId"] is None
    assert data["deltaCent"] == 88000


@pytest.mark.asyncio
async def test_review_requires_settlement_permission_and_idempotency_key(
    client: AsyncClient, db_session: AsyncSession
):
    adjustment_id, _ = await _seed_adjustment(db_session)
    url = f"/api/v1/admin/performance/adjustments/{adjustment_id}/review"
    payload = {"expectedVersion": 1}
    read_headers = await _headers(db_session, "sharing_rules.read")

    denied = await client.post(
        url,
        json=payload,
        headers={**read_headers, "Idempotency-Key": "mall-adj-review-001"},
    )
    assert denied.status_code == 403

    settle_headers = await _headers(db_session, "performance.settle")
    accepted = _data(
        await client.post(
            url,
            json=payload,
            headers={
                **settle_headers,
                "Idempotency-Key": "mall-adj-review-002",
            },
        )
    )
    assert accepted["status"] == "reviewed"
    assert accepted["originEvidenceId"] is not None
    assert accepted["originResultId"] is None


@pytest.mark.asyncio
async def test_adjustment_list_uses_cursor_and_keeps_evidence_anchors(
    client: AsyncClient, db_session: AsyncSession
):
    older_id, _ = await _seed_adjustment(db_session)
    newer_id, _ = await _seed_adjustment(db_session)
    headers = await _headers(db_session, "sharing_rules.read")

    first = await client.get(
        "/api/v1/admin/performance/adjustments",
        params={"pageSize": 1},
        headers=headers,
    )
    page = _data(first)
    assert first.headers["cache-control"] == "no-store"
    assert page["total"] == 2
    assert len(page["items"]) == 1
    assert page["items"][0]["id"] == str(newer_id)
    assert page["items"][0]["originEvidenceId"]
    assert page["items"][0]["originResultPresence"] == "not_generated"
    assert page["items"][0]["originResultId"] is None
    assert page["nextCursor"]

    second = _data(
        await client.get(
            "/api/v1/admin/performance/adjustments",
            params={"pageSize": 1, "cursor": page["nextCursor"]},
            headers=headers,
        )
    )
    assert [item["id"] for item in second["items"]] == [str(older_id)]
    assert second["nextCursor"] is None


@pytest.mark.asyncio
async def test_reject_adjustment_is_reasoned_versioned_and_idempotent(
    client: AsyncClient, db_session: AsyncSession
):
    adjustment_id, _ = await _seed_adjustment(db_session)
    url = f"/api/v1/admin/performance/adjustments/{adjustment_id}/reject"
    headers = await _headers(db_session, "performance.settle")
    body = {"expectedVersion": 1, "reason": "原始归属凭证无法核验"}
    command_headers = {**headers, "Idempotency-Key": "mall-adj-reject-command-001"}

    rejected = _data(await client.post(url, json=body, headers=command_headers))
    assert rejected["status"] == "rejected"
    assert rejected["reason"] == body["reason"]
    assert rejected["remainingCent"] == 0
    assert rejected["version"] == 2
    assert _data(await client.post(url, json=body, headers=command_headers)) == rejected
    command = await db_session.scalar(
        select(MallCommand).where(MallCommand.key == "mall-adj-reject-command-001")
    )
    assert command is not None
    assert command.payload_hash == canonical_payload_hash(
        {
            "adjustmentId": str(adjustment_id),
            "expectedVersion": 1,
            "reason": body["reason"],
        }
    )

    mismatch = await client.post(
        url,
        json={**body, "reason": "替换幂等请求原因"},
        headers=command_headers,
    )
    assert mismatch.status_code == 409, mismatch.text


@pytest.mark.asyncio
async def test_reconcile_links_only_verified_scoped_evidence_files(
    client: AsyncClient, db_session: AsyncSession
):
    from src.models.mall_base import utc_now
    from src.models.mall_operations import MallFile

    adjustment_id, _ = await _seed_adjustment(db_session)
    adjustment = await db_session.get(PerformanceAdjustment, adjustment_id)
    adjustment.status = "manual_required"
    adjustment.reason = "原期规则证据需人工核验"
    admin_id, headers = await _admin_identity_and_headers(db_session, "performance.settle")
    proof = MallFile(
        object_key=f"test/performance-adjustment/{uuid4().hex}",
        purpose="performance_adjustment_evidence",
        owner_actor_type="admin",
        owner_actor_id=admin_id,
        mime="image/jpeg",
        size=128,
        sha256="a" * 64,
        status="verified",
        expires_at=utc_now(),
    )
    db_session.add(proof)
    await db_session.flush()

    url = f"/api/v1/admin/performance/adjustments/{adjustment_id}/reconcile"
    body = {
        "expectedVersion": 1,
        "evidenceFileIds": [str(proof.id)],
        "reason": "已核验原期规则与适用资格凭证",
    }
    command_headers = {**headers, "Idempotency-Key": "mall-adj-reconcile-001"}
    reconciled = _data(await client.post(url, json=body, headers=command_headers))
    assert reconciled["status"] == "proposed"
    assert reconciled["evidenceFileIds"] == [str(proof.id)]
    assert reconciled["reason"] == body["reason"]
    assert reconciled["version"] == 2
    await db_session.refresh(proof)
    assert proof.status == "bound"

    replayed = _data(await client.post(url, json=body, headers=command_headers))
    assert replayed == reconciled


@pytest.mark.asyncio
async def test_net_entitlement_separates_normal_commission_and_applied_debt(
    client: AsyncClient, db_session: AsyncSession
):
    from datetime import datetime

    from src.models.commission_result import CommissionResult
    from src.models.performance_adjustment import PerformanceAdjustmentApplication
    from src.models.performance_settlement import PerformanceSettlement, SettlementStatus

    adjustment_id, _ = await _seed_adjustment(db_session)
    adjustment = await db_session.get(PerformanceAdjustment, adjustment_id)
    adjustment.status = "reviewed"
    adjustment.original_commission_cent = 50000
    adjustment.replayed_commission_cent = 0
    adjustment.delta_cent = -50000
    adjustment.remaining_cent = 0
    target_settlement = PerformanceSettlement(
        period="2026-08", status=SettlementStatus.REVIEWED
    )
    db_session.add(target_settlement)
    target = CommissionResult(
        period="2026-08",
        distributor_id=adjustment.beneficiary_id,
        org_id=1,
        rule_type=RuleType.INTRA_ORG,
        base_cent=100000,
        ratio="0.08",
        commission_cent=250000,
        computed_at=datetime(2026, 8, 31),
    )
    db_session.add(target)
    await db_session.flush()
    db_session.add(
        PerformanceAdjustmentApplication(
            adjustment_id=adjustment.id,
            target_period=target.period,
            target_result_id=target.id,
            allocated_cent=-50000,
            settled_cent=-50000,
            status="consumed",
            allocation_key=f"contract-net-entitlement-{uuid4().hex}",
        )
    )
    await db_session.flush()
    headers = await _headers(db_session, "performance.settle")

    response = await client.get(
        f"/api/v1/admin/performance/results/{target.id}/net-entitlement",
        headers=headers,
    )
    data = _data(response)
    assert response.headers["cache-control"] == "no-store"
    assert data["normalCommissionCent"] == 250000
    assert data["confirmedAdjustmentCent"] == -50000
    assert data["appliedDebtCent"] == 50000
    assert data["redeemableCent"] == 200000
    assert data["pendingDebtCent"] == 0
