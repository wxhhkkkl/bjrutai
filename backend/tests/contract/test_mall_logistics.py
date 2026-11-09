from datetime import timedelta

import pytest
from sqlalchemy import func, select

from src.core.config import get_settings
from src.models.mall_base import utc_now
from src.models.mall_operations import MallJob
from tests.conftest import TestAsyncSession, auth_header, make_access_token, seed_user
from tests.contract.test_admin_mall_orders import admin
from tests.contract.test_mall_fulfillment import paid_order
from tests.unit.test_mall_order_actions import unattempted


@pytest.mark.asyncio
async def test_buyer_and_admin_share_one_pending_query_and_refresh_cooldown(
    client, db_session, monkeypatch
):
    monkeypatch.setattr(get_settings(), "app_environment", "test")
    buyer, order, _ = await paid_order(db_session, monkeypatch)
    _, _, admin_headers = await admin(db_session, ["mall.orders.read", "mall.shipments.write"])
    admin_headers["Idempotency-Key"] = "contract-logistics-ship-0002"
    sent = await client.post(
        f"/api/v1/admin/mall/orders/{order.id}/ship",
        headers=admin_headers,
        json={
            "expectedVersion": order.version,
            "courierCode": "yuantong",
            "trackingNo": "YT202611060001",
        },
    )
    assert sent.status_code == 200, sent.text
    shipment_id = int(sent.json()["data"]["id"])

    buyer_headers = auth_header(make_access_token(user_id=buyer.actor_id, user_type="personal"))
    buyer_url = f"/api/v1/mall/orders/{order.id}/logistics"
    first = await client.get(buyer_url, headers=buyer_headers)
    assert first.status_code == 200, first.text
    snapshot = first.json()["data"]
    assert snapshot["queryStatus"] == "pending" and snapshot["source"] is None
    assert snapshot["shipmentVersion"] == sent.json()["data"]["version"]
    assert snapshot["mapAvailable"] is False
    assert "13800001234" not in first.text and "虚构路" not in first.text
    assert "trailUrl" not in first.text and "courierInfo" not in first.text
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(MallJob)
            .where(MallJob.kind == "mall_logistics_query", MallJob.entity_id == shipment_id)
        )
        == 1
    )

    order_headers = {k: v for k, v in admin_headers.items() if k != "Idempotency-Key"}
    admin_read = await client.get(
        f"/api/v1/admin/mall/orders/{order.id}/logistics", headers=order_headers
    )
    assert admin_read.status_code == 200
    assert admin_read.json()["data"]["queryStatus"] == "pending"
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(MallJob)
            .where(MallJob.kind == "mall_logistics_query", MallJob.entity_id == shipment_id)
        )
        == 1
    )

    admin_headers["Idempotency-Key"] = "contract-logistics-refresh-0001"
    refresh_url = f"/api/v1/admin/mall/shipments/{shipment_id}/logistics-refresh"
    expected_version = sent.json()["data"]["version"]
    body = {"expectedVersion": expected_version}
    limited = await client.post(refresh_url, headers=admin_headers, json=body)
    assert limited.status_code == 202, limited.text
    assert limited.json()["data"]["scheduled"] is False
    assert limited.json()["data"]["commandId"]
    replay = await client.post(refresh_url, headers=admin_headers, json=body)
    assert replay.status_code == 202
    assert replay.json()["data"]["commandId"] == limited.json()["data"]["commandId"]
    assert replay.json()["data"]["scheduled"] is False

    _, _, read_only = await admin(db_session, ["mall.orders.read"])
    read_only["Idempotency-Key"] = "contract-logistics-refresh-denied-001"
    assert (await client.post(refresh_url, headers=read_only, json=body)).status_code == 403


@pytest.mark.asyncio
async def test_fake_worker_returns_sanitized_versioned_events_and_order_scoped_snapshot(
    client, db_session, monkeypatch
):
    from src.services.mall_logistics_service import logistics_handlers
    from src.tasks.mall_tasks import run_mall_worker_once

    monkeypatch.setattr(get_settings(), "app_environment", "test")
    buyer, order, _ = await paid_order(db_session, monkeypatch)
    _, _, headers = await admin(db_session, ["mall.orders.read", "mall.shipments.write"])
    headers["Idempotency-Key"] = "contract-logistics-ship-0003"
    sent = await client.post(
        f"/api/v1/admin/mall/orders/{order.id}/ship",
        headers=headers,
        json={
            "expectedVersion": order.version,
            "courierCode": "yuantong",
            "trackingNo": "YT202611060002",
        },
    )
    assert sent.status_code == 200, sent.text
    shipment_id = int(sent.json()["data"]["id"])
    buyer_headers = auth_header(make_access_token(user_id=buyer.actor_id, user_type="personal"))
    read_url = f"/api/v1/mall/orders/{order.id}/logistics"
    assert (await client.get(read_url, headers=buyer_headers)).status_code == 200
    job = await db_session.scalar(
        select(MallJob).where(
            MallJob.kind == "mall_logistics_query", MallJob.entity_id == shipment_id
        )
    )
    job.next_run_at = utc_now() - timedelta(seconds=1)
    await db_session.commit()

    assert await run_mall_worker_once(
        TestAsyncSession,
        handlers=logistics_handlers(TestAsyncSession),
        enabled=True,
    )
    await db_session.refresh(job)
    assert job.status == "done", (job.status, job.last_error_code, job.attempts)
    result = await client.get(read_url, headers=buyer_headers)
    assert result.status_code == 200, result.text
    snapshot = result.json()["data"]
    assert snapshot["queryStatus"] == "available"
    assert snapshot["source"] == "fake"
    assert snapshot["events"]
    assert snapshot["mapAvailable"] is False
    assert "13800000000" not in result.text
    assert "courierInfo" not in result.text and "trailUrl" not in result.text

    other_id = await seed_user(db_session, user_type="personal", openid="mall-logistics-other")
    await db_session.commit()
    other_headers = auth_header(make_access_token(user_id=other_id, user_type="personal"))
    assert (await client.get(read_url, headers=other_headers)).status_code == 404


@pytest.mark.asyncio
async def test_logistics_reads_without_shipment_do_not_reveal_order_existence(
    client, db_session, monkeypatch
):
    actor, _, _, _, order = await unattempted(db_session, monkeypatch)
    headers = auth_header(make_access_token(user_id=actor.actor_id, user_type="personal"))
    response = await client.get(f"/api/v1/mall/orders/{order.id}/logistics", headers=headers)
    assert response.status_code == 409
    assert "13800001234" not in response.text and "虚构路" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_code", "status"),
    [
        ("no_record", "no_record"),
        ("verification_failed", "verification_failed"),
        ("permission_denied", "permission_denied"),
        ("service_error", "service_error"),
    ],
)
async def test_provider_failures_have_safe_states_and_do_not_expose_diagnostics(
    client, db_session, monkeypatch, error_code, status
):
    from src.integrations.kuaidi100_client import Kuaidi100Error
    from src.services.mall_logistics_service import logistics_handlers
    from src.tasks.mall_tasks import run_mall_worker_once

    monkeypatch.setattr(get_settings(), "app_environment", "test")
    buyer, order, _ = await paid_order(db_session, monkeypatch)
    _, _, headers = await admin(db_session, ["mall.orders.read", "mall.shipments.write"])
    headers["Idempotency-Key"] = "contract-logistics-error-ship-" + error_code
    shipped = await client.post(
        f"/api/v1/admin/mall/orders/{order.id}/ship",
        headers=headers,
        json={
            "expectedVersion": order.version,
            "courierCode": "yuantong",
            "trackingNo": "YT202611060003",
        },
    )
    assert shipped.status_code == 200, shipped.text
    shipment_id = int(shipped.json()["data"]["id"])
    buyer_headers = auth_header(make_access_token(user_id=buyer.actor_id, user_type="personal"))
    url = f"/api/v1/mall/orders/{order.id}/logistics"
    assert (await client.get(url, headers=buyer_headers)).status_code == 200
    job = await db_session.scalar(
        select(MallJob).where(
            MallJob.kind == "mall_logistics_query", MallJob.entity_id == shipment_id
        )
    )
    job.next_run_at = utc_now() - timedelta(seconds=1)
    await db_session.commit()

    class FailingProvider:
        async def query(self, **_unused):
            raise Kuaidi100Error(error_code)

    assert await run_mall_worker_once(
        TestAsyncSession,
        handlers=logistics_handlers(TestAsyncSession, client=FailingProvider()),
        enabled=True,
    )
    result = await client.get(url, headers=buyer_headers)
    assert result.status_code == 200
    data = result.json()["data"]
    assert data["queryStatus"] == status and data["errorCode"] == error_code
    assert error_code in result.text


@pytest.mark.asyncio
async def test_production_logistics_worker_stays_closed_even_with_live_flags(
    client, db_session, monkeypatch
):
    from src.services.mall_logistics_service import logistics_handlers
    from src.tasks.mall_tasks import run_mall_worker_once

    settings = get_settings()
    monkeypatch.setattr(settings, "app_environment", "production")
    monkeypatch.setattr(settings, "mall_kuaidi100_mode", "live")
    monkeypatch.setattr(settings, "mall_kuaidi100_outbound_enabled", True)
    buyer, order, _ = await paid_order(db_session, monkeypatch)
    _, _, headers = await admin(db_session, ["mall.orders.read", "mall.shipments.write"])
    headers["Idempotency-Key"] = "contract-logistics-live-gate-0001"
    shipped = await client.post(
        f"/api/v1/admin/mall/orders/{order.id}/ship",
        headers=headers,
        json={
            "expectedVersion": order.version,
            "courierCode": "yuantong",
            "trackingNo": "YT202611060004",
        },
    )
    assert shipped.status_code == 200, shipped.text
    url = f"/api/v1/mall/orders/{order.id}/logistics"
    buyer_headers = auth_header(make_access_token(user_id=buyer.actor_id, user_type="personal"))
    await client.get(url, headers=buyer_headers)
    job = await db_session.scalar(
        select(MallJob).where(
            MallJob.kind == "mall_logistics_query",
            MallJob.entity_id == int(shipped.json()["data"]["id"]),
        )
    )
    job.next_run_at = utc_now() - timedelta(seconds=1)
    await db_session.commit()

    class MustNotCallLiveProvider:
        async def query(self, **_unused):
            pytest.fail("production network access is not enabled by this task")

    assert await run_mall_worker_once(
        TestAsyncSession,
        handlers=logistics_handlers(TestAsyncSession, client=MustNotCallLiveProvider()),
        enabled=True,
    )
    result = await client.get(url, headers=buyer_headers)
    assert result.status_code == 200
    assert result.json()["data"]["queryStatus"] == "config_required"
    assert result.json()["data"]["errorCode"] == "data_release_gate_inactive"
