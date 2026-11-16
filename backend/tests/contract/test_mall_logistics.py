from datetime import timedelta

import pytest
from sqlalchemy import func, select

from src.core.config import get_settings
from src.models.mall_base import utc_now
from src.models.mall_operations import MallJob
from tests.conftest import TestAsyncSession, auth_header, make_access_token, seed_user
from tests.contract.test_admin_mall_orders import admin
from tests.contract.test_mall_fulfillment import paid_order
from tests.unit.test_mall_aftersale_service import admin_actor
from tests.unit.test_mall_aftersale_service import paid_order as aftersale_paid_order
from tests.unit.test_mall_order_actions import unattempted


async def approved_return_aftersale(
    client,
    db_session,
    monkeypatch,
    *,
    return_snapshot=None,
    courier_code="yuantong",
    tracking_no="YT202611130001",
    submit_waybill=True,
):
    from src.models.mall_operations import MallSettings

    buyer, order, _, items = await aftersale_paid_order(db_session, monkeypatch)
    settings_row = await db_session.get(MallSettings, 1)
    settings_row.return_address_snapshot = {
        "recipientName": "商城退货收件人",
        "phone": "13900001111",
        "addressLine": "北京虚构退货地址",
        **(return_snapshot or {}),
    }
    await db_session.commit()
    buyer_headers = {
        **auth_header(make_access_token(user_id=buyer.actor_id, user_type="personal")),
        "Idempotency-Key": "contract-return-logistics-create-001",
    }
    created = await client.post(
        "/api/v1/mall/aftersales",
        headers=buyer_headers,
        json={
            "orderId": str(order.id),
            "expectedOrderVersion": order.version,
            "method": "return_refund",
            "items": [{"orderItemId": str(items[1].id), "quantity": 1}],
            "reason": "需要退回商品验收",
        },
    )
    assert created.status_code == 200, created.text
    aftersale_id = created.json()["data"]["id"]

    reviewer = await admin_actor(db_session, ["mall.aftersales.review", "mall.aftersales.read"])
    admin_headers = auth_header(
        make_access_token(user_id=reviewer.actor_id, user_type="admin")
    )
    admin_headers["Idempotency-Key"] = "contract-return-logistics-approve-001"
    approved = await client.post(
        f"/api/v1/admin/mall/aftersales/{aftersale_id}/decision",
        headers=admin_headers,
        json={
            "expectedVersion": created.json()["data"]["version"],
            "decision": "approve",
            "reason": "同意退回验收",
        },
    )
    assert approved.status_code == 200, approved.text

    shipped = None
    if submit_waybill:
        buyer_headers["Idempotency-Key"] = "contract-return-logistics-waybill-001"
        waybill = await client.post(
            f"/api/v1/mall/aftersales/{aftersale_id}/return-shipment",
            headers=buyer_headers,
            json={
                "expectedVersion": approved.json()["data"]["version"],
                "courierCode": courier_code,
                "trackingNo": tracking_no,
            },
        )
        assert waybill.status_code == 200, waybill.text
        shipped = waybill.json()["data"]
    return {
        "buyer": buyer,
        "order": order,
        "aftersaleId": aftersale_id,
        "approvedVersion": approved.json()["data"]["version"],
        "shipped": shipped,
        "buyerHeaders": buyer_headers,
        "adminHeaders": admin_headers,
    }



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
    assert snapshot["mapAvailable"] is True
    assert snapshot["estimatedArrivalText"]
    assert len(snapshot["route"]["points"]) >= 2
    assert snapshot["route"]["points"][0]["latitude"] is not None
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


@pytest.mark.asyncio
async def test_live_worker_sends_configured_regions_to_provider(client, db_session, monkeypatch):
    from src.models.mall_operations import MallSettings
    from src.services.mall_logistics_service import logistics_handlers
    from src.services.mall_settings_service import get_mall_settings
    from src.tasks.mall_tasks import run_mall_worker_once

    settings = get_settings()
    monkeypatch.setattr(settings, "app_environment", "development")
    monkeypatch.setattr(settings, "mall_kuaidi100_mode", "live")
    monkeypatch.setattr(settings, "mall_kuaidi100_outbound_enabled", True)
    buyer, order, _ = await paid_order(db_session, monkeypatch)
    mall_settings = await get_mall_settings(db_session)
    mall_settings.dispatch_address_snapshot = {
        "regionCodes": ["110000", "110100", "110114"],
        "regionNames": ["北京市", "北京市", "昌平区"],
    }
    order.address_snapshot = {
        **(order.address_snapshot or {}),
        "regionNames": ["河北省", "廊坊市", "固安县"],
    }
    await db_session.commit()
    assert isinstance(mall_settings, MallSettings)

    _, _, headers = await admin(db_session, ["mall.orders.read", "mall.shipments.write"])
    headers["Idempotency-Key"] = "contract-logistics-live-ship-0001"
    shipped = await client.post(
        f"/api/v1/admin/mall/orders/{order.id}/ship",
        headers=headers,
        json={
            "expectedVersion": order.version,
            "courierCode": "yuantong",
            "trackingNo": "YT202611060005",
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

    class RecordingLiveProvider:
        def __init__(self):
            self.calls = []

        async def query(self, **kwargs):
            self.calls.append(kwargs)
            return {
                "state": "3",
                "data": [
                    {
                        "context": "已签收，联系电话13800000000",
                        "time": "2026-11-11 10:00:00",
                        "province": "河北省",
                        "city": "廊坊市",
                    }
                ],
            }

    provider = RecordingLiveProvider()
    assert await run_mall_worker_once(
        TestAsyncSession,
        handlers=logistics_handlers(TestAsyncSession, live_client=provider),
        enabled=True,
    )
    assert provider.calls == [
        {
            "courier_code": "yuantong",
            "tracking_no": "YT202611060005",
            "from_city": "北京市,北京市,昌平区",
            "to_city": "河北省,廊坊市,固安县",
        }
    ]
    result = await client.get(url, headers=buyer_headers)
    assert result.status_code == 200
    data = result.json()["data"]
    assert data["source"] == "live"
    assert data["queryStatus"] == "available"
    assert data["stateName"] == "已签收"
    assert "13800000000" not in result.text
    assert data["mapAvailable"] is False


@pytest.mark.asyncio
async def test_live_map_query_returns_route_and_sends_phone_for_verification_carrier(
    client, db_session, monkeypatch
):
    from src.services.mall_logistics_service import logistics_handlers
    from src.services.mall_settings_service import get_mall_settings
    from src.tasks.mall_tasks import run_mall_worker_once

    settings = get_settings()
    monkeypatch.setattr(settings, "app_environment", "development")
    monkeypatch.setattr(settings, "mall_kuaidi100_mode", "live")
    monkeypatch.setattr(settings, "mall_kuaidi100_outbound_enabled", True)
    buyer, order, _ = await paid_order(db_session, monkeypatch)
    mall_settings = await get_mall_settings(db_session)
    mall_settings.dispatch_address_snapshot = {
        "regionCodes": ["340000", "340100", "340104"],
        "regionNames": ["安徽省", "合肥市", "蜀山区"],
    }
    order.address_snapshot = {
        **(order.address_snapshot or {}),
        "regionNames": ["北京市", "北京市", "东城区"],
    }
    await db_session.commit()

    _, _, headers = await admin(db_session, ["mall.orders.read", "mall.shipments.write"])
    headers["Idempotency-Key"] = "contract-logistics-map-phone-0001"
    shipped = await client.post(
        f"/api/v1/admin/mall/orders/{order.id}/ship",
        headers=headers,
        json={
            "expectedVersion": order.version,
            "courierCode": "zhongtong",
            "trackingNo": "ZT202611110001",
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

    class RecordingLiveProvider:
        def __init__(self):
            self.calls = []

        async def query(self, **kwargs):
            self.calls.append(kwargs)
            return {
                "state": "0",
                "data": [{"context": "快件已发出", "time": "2026-11-11 10:00:00"}],
                "routeInfo": {"cur": {"name": "合肥市"}},
                "predictedRoute": [
                    {
                        "name": "合肥转运中心",
                        "state": "当前停留节点",
                        "location": "117.2272,31.8206",
                    },
                    {
                        "name": "北京转运中心",
                        "state": "预估途径节点",
                        "location": "116.4074,39.9042",
                    },
                ],
                "arrivalTime": "2026-11-13 10",
                "trailUrl": (
                    "https://api.kuaidi100.com/tools/map/V2/"
                    "contract-token_117.242911,31.835115_6"
                ),
            }

    provider = RecordingLiveProvider()
    assert await run_mall_worker_once(
        TestAsyncSession,
        handlers=logistics_handlers(TestAsyncSession, live_client=provider),
        enabled=True,
    )
    assert provider.calls[0]["phone"] == "13800001234"
    assert provider.calls[0]["from_city"] == "安徽省,合肥市,蜀山区"
    assert provider.calls[0]["to_city"] == "北京市,北京市,东城区"

    result = await client.get(url, headers=buyer_headers)
    data = result.json()["data"]
    assert data["mapAvailable"] is True
    assert data["estimatedArrivalText"]
    assert data["route"]["currentName"] == "合肥市"
    assert [point["latitude"] for point in data["route"]["points"]] == [31.8206, 39.9042]
    assert "13800001234" not in result.text
    assert "trailUrl" not in result.text and "courierInfo" not in result.text
    assert data["mapUrl"] == (
        "https://api.kuaidi100.com/tools/map/V2/contract-token_117.242911,31.835115_6"
    )

    admin_read = await client.get(
        f"/api/v1/admin/mall/orders/{order.id}/logistics",
        params={"scheduleRefresh": "false"},
        headers=headers,
    )
    assert admin_read.status_code == 200, admin_read.text
    assert admin_read.json()["data"]["mapUrl"] == (
        "https://api.kuaidi100.com/tools/map/V2/contract-token_117.242911,31.835115_6"
    )


@pytest.mark.asyncio
async def test_live_map_query_without_active_recipient_contact_consent_omits_phone(
    client, db_session, monkeypatch
):
    from src.models.consent import ConsentRecord
    from src.services.mall_logistics_service import logistics_handlers
    from src.services.mall_settings_service import get_mall_settings
    from src.tasks.mall_tasks import run_mall_worker_once

    settings = get_settings()
    monkeypatch.setattr(settings, "app_environment", "development")
    monkeypatch.setattr(settings, "mall_kuaidi100_mode", "live")
    monkeypatch.setattr(settings, "mall_kuaidi100_outbound_enabled", True)
    buyer, order, _ = await paid_order(db_session, monkeypatch)
    mall_settings = await get_mall_settings(db_session)
    mall_settings.dispatch_address_snapshot = {
        "regionCodes": ["340000", "340100", "340104"],
        "regionNames": ["安徽省", "合肥市", "蜀山区"],
    }
    order.address_snapshot = {
        **(order.address_snapshot or {}),
        "regionNames": ["北京市", "北京市", "东城区"],
    }
    consent = await db_session.get(ConsentRecord, order.consent_record_id)
    consent.status = "revoked"
    await db_session.commit()

    _, _, headers = await admin(db_session, ["mall.orders.read", "mall.shipments.write"])
    headers["Idempotency-Key"] = "contract-logistics-map-noconsent-0001"
    shipped = await client.post(
        f"/api/v1/admin/mall/orders/{order.id}/ship",
        headers=headers,
        json={
            "expectedVersion": order.version,
            "courierCode": "zhongtong",
            "trackingNo": "ZT202611110002",
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

    class RecordingLiveProvider:
        def __init__(self):
            self.calls = []

        async def query(self, **kwargs):
            self.calls.append(kwargs)
            return {"state": "0", "data": []}

    provider = RecordingLiveProvider()
    assert await run_mall_worker_once(
        TestAsyncSession,
        handlers=logistics_handlers(TestAsyncSession, live_client=provider),
        enabled=True,
    )
    assert "phone" not in provider.calls[0]


@pytest.mark.asyncio
async def test_admin_return_logistics_needs_waybill_and_reports_company_name(
    client, db_session, monkeypatch
):
    monkeypatch.setattr(get_settings(), "app_environment", "test")
    fixture = await approved_return_aftersale(
        client, db_session, monkeypatch, submit_waybill=False
    )
    url = f"/api/v1/admin/mall/aftersales/{fixture['aftersaleId']}/return-logistics"
    missing = await client.get(url, headers=fixture["adminHeaders"])
    assert missing.status_code == 409
    assert "退货运单" in missing.json()["message"]

    fixture["buyerHeaders"]["Idempotency-Key"] = "contract-return-logistics-waybill-002"
    waybill = await client.post(
        f"/api/v1/mall/aftersales/{fixture['aftersaleId']}/return-shipment",
        headers=fixture["buyerHeaders"],
        json={
            "expectedVersion": fixture["approvedVersion"],
            "courierCode": "zhongtong",
            "trackingNo": "ZT202611130009",
        },
    )
    assert waybill.status_code == 200, waybill.text

    first = await client.get(url, headers=fixture["adminHeaders"])
    assert first.status_code == 200, first.text
    snapshot = first.json()["data"]
    assert snapshot["courierCode"] == "zhongtong"
    assert snapshot["trackingNo"] == "ZT202611130009"
    assert snapshot["aftersaleVersion"] == waybill.json()["data"]["version"]
    assert snapshot["queryStatus"] == "pending" and snapshot["source"] is None
    assert "13900001111" not in first.text
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(MallJob)
            .where(
                MallJob.kind == "mall_logistics_query",
                MallJob.entity_type == "mall_aftersale",
                MallJob.entity_id == int(fixture["aftersaleId"]),
            )
        )
        == 1
    )
    detail = await client.get(
        f"/api/v1/admin/mall/aftersales/{fixture['aftersaleId']}",
        headers=fixture["adminHeaders"],
    )
    assert detail.json()["data"]["returnCompany"] == "zhongtong"

    _, _, orders_only = await admin(db_session, ["mall.orders.read"])
    denied = await client.get(url, headers=orders_only)
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_fake_worker_caches_return_snapshot_and_respects_cooldown(
    client, db_session, monkeypatch
):
    from src.services.mall_logistics_service import logistics_handlers
    from src.tasks.mall_tasks import run_mall_worker_once

    monkeypatch.setattr(get_settings(), "app_environment", "test")
    fixture = await approved_return_aftersale(client, db_session, monkeypatch)
    url = f"/api/v1/admin/mall/aftersales/{fixture['aftersaleId']}/return-logistics"
    first = await client.get(url, headers=fixture["adminHeaders"])
    assert first.status_code == 200, first.text
    assert first.json()["data"]["queryStatus"] == "pending"

    job = await db_session.scalar(
        select(MallJob).where(
            MallJob.kind == "mall_logistics_query",
            MallJob.entity_type == "mall_aftersale",
            MallJob.entity_id == int(fixture["aftersaleId"]),
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

    second = await client.get(url, headers=fixture["adminHeaders"])
    assert second.status_code == 200, second.text
    snapshot = second.json()["data"]
    assert snapshot["queryStatus"] == "available" and snapshot["source"] == "fake"
    assert snapshot["courierCode"] == "yuantong"
    assert snapshot["events"] and snapshot["mapAvailable"] is True
    assert "13900001111" not in second.text
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(MallJob)
            .where(
                MallJob.kind == "mall_logistics_query",
                MallJob.entity_type == "mall_aftersale",
                MallJob.entity_id == int(fixture["aftersaleId"]),
            )
        )
        == 1
    )


@pytest.mark.asyncio
async def test_live_return_query_uses_matching_return_regions_and_merchant_phone(
    client, db_session, monkeypatch
):
    from src.models.mall_operations import MallSettings
    from src.services.mall_logistics_service import logistics_handlers
    from src.tasks.mall_tasks import run_mall_worker_once

    settings = get_settings()
    monkeypatch.setattr(settings, "app_environment", "development")
    monkeypatch.setattr(settings, "mall_kuaidi100_mode", "live")
    monkeypatch.setattr(settings, "mall_kuaidi100_outbound_enabled", True)
    fixture = await approved_return_aftersale(
        client,
        db_session,
        monkeypatch,
        return_snapshot={"regionCodes": ["110000", "110100", "110114"]},
        courier_code="zhongtong",
        tracking_no="ZT202611130010",
    )
    fixture["order"].address_snapshot = {
        **(fixture["order"].address_snapshot or {}),
        "regionNames": ["河北省", "廊坊市", "固安县"],
    }
    settings_row = await db_session.get(MallSettings, 1)
    settings_row.return_address_snapshot = {
        "recipientName": "商城退货收件人",
        "phone": "13900001111",
        "addressLine": "北京虚构退货地址",
        "regionCodes": ["110000", "110100", "110114"],
        "regionNames": ["北京市", "北京市", "昌平区"],
    }
    await db_session.commit()

    url = f"/api/v1/admin/mall/aftersales/{fixture['aftersaleId']}/return-logistics"
    assert (await client.get(url, headers=fixture["adminHeaders"])).status_code == 200
    job = await db_session.scalar(
        select(MallJob).where(
            MallJob.kind == "mall_logistics_query",
            MallJob.entity_type == "mall_aftersale",
            MallJob.entity_id == int(fixture["aftersaleId"]),
        )
    )
    job.next_run_at = utc_now() - timedelta(seconds=1)
    await db_session.commit()

    class RecordingLiveProvider:
        def __init__(self):
            self.calls = []

        async def query(self, **kwargs):
            self.calls.append(kwargs)
            return {
                "state": "0",
                "data": [{"context": "退货快件已揽收", "time": "2026-11-13 10:00:00"}],
            }

    provider = RecordingLiveProvider()
    assert await run_mall_worker_once(
        TestAsyncSession,
        handlers=logistics_handlers(TestAsyncSession, live_client=provider),
        enabled=True,
    )
    assert provider.calls == [
        {
            "courier_code": "zhongtong",
            "tracking_no": "ZT202611130010",
            "from_city": "河北省,廊坊市,固安县",
            "to_city": "北京市,北京市,昌平区",
            "phone": "13900001111",
        }
    ]

    result = await client.get(url, headers=fixture["adminHeaders"])
    data = result.json()["data"]
    assert data["source"] == "live" and data["queryStatus"] == "available"
    assert data["courierCode"] == "zhongtong"
    assert "13900001111" not in result.text
