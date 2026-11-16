"""Synthetic Kuaidi100 delivery remains separate from shipment and receipt facts."""

import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import select

from src.core.config import get_settings
from src.models.mall_base import utc_now
from src.models.mall_operations import MallJob
from src.models.mall_trade import MallShipment
from src.tasks.mall_tasks import run_mall_worker_once
from tests.conftest import TestAsyncSession, auth_header, make_access_token
from tests.contract.test_admin_mall_orders import admin
from tests.contract.test_mall_fulfillment import paid_order


class DelayedSignedEvent:
    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def query(self, *, tracking_no, **_unused):
        self.started.set()
        await self.release.wait()
        return {
            "state": "3",
            "data": [
                {
                    "leaveTime": "2026-11-06 12:00:00",
                    "name": f"旧运单{tracking_no[-4:]}显示签收",
                    "stateCode": "3",
                    "status": "签收轨迹",
                }
            ],
        }


@pytest.mark.asyncio
async def test_late_old_waybill_result_cannot_replace_corrected_tracking_or_confirm_receipt(
    client, db_session, monkeypatch
):
    from src.services.mall_logistics_service import logistics_handlers

    monkeypatch.setattr(get_settings(), "app_environment", "test")
    buyer, order, _ = await paid_order(db_session, monkeypatch)
    _, _, admin_headers = await admin(db_session, ["mall.orders.read", "mall.shipments.write"])
    admin_headers["Idempotency-Key"] = "integration-logistics-ship-0001"
    dispatched = await client.post(
        f"/api/v1/admin/mall/orders/{order.id}/ship",
        headers=admin_headers,
        json={
            "expectedVersion": order.version,
            "courierCode": "yuantong",
            "trackingNo": "YT202611060091",
        },
    )
    assert dispatched.status_code == 200, dispatched.text
    package = dispatched.json()["data"]
    await db_session.refresh(order)
    buyer_headers = auth_header(make_access_token(user_id=buyer.actor_id, user_type="personal"))
    logistics_url = f"/api/v1/mall/orders/{order.id}/logistics"
    assert (await client.get(logistics_url, headers=buyer_headers)).status_code == 200
    old_job = await db_session.scalar(
        select(MallJob).where(
            MallJob.kind == "mall_logistics_query", MallJob.entity_id == package["id"]
        )
    )
    old_job.next_run_at = utc_now() - timedelta(seconds=1)
    await db_session.commit()

    provider = DelayedSignedEvent()
    handlers = logistics_handlers(TestAsyncSession, client=provider)
    worker = asyncio.create_task(
        run_mall_worker_once(TestAsyncSession, handlers=handlers, enabled=True)
    )
    await asyncio.wait_for(provider.started.wait(), timeout=5)
    corrected = await client.patch(
        f"/api/v1/admin/mall/shipments/{package['id']}",
        headers=admin_headers,
        json={
            "expectedVersion": order.version,
            "shipmentVersion": package["version"],
            "courierCode": "shunfeng",
            "trackingNo": "SF202611060092",
            "reason": "供应商录单错运单",
        },
    )
    assert corrected.status_code == 200, corrected.text
    corrected_package = corrected.json()["data"]
    provider.release.set()
    assert await asyncio.wait_for(worker, timeout=5)

    snapshot = (await client.get(logistics_url, headers=buyer_headers)).json()["data"]
    assert snapshot["trackingNo"] == "SF202611060092"
    assert snapshot["shipmentVersion"] == corrected_package["version"]
    assert snapshot["queryStatus"] == "pending"
    assert snapshot["events"] == []
    assert "YT202611060091" not in str(snapshot)
    await db_session.refresh(order)
    assert order.status == "pending_receipt"
    current_auto_receive = await db_session.scalar(
        select(MallJob).where(
            MallJob.kind == "mall_order_auto_receive",
            MallJob.entity_type == "mall_shipment",
            MallJob.entity_id == package["id"],
            MallJob.entity_version == corrected_package["version"],
        )
    )
    assert current_auto_receive is not None and current_auto_receive.status == "ready"

    new_job = await db_session.scalar(
        select(MallJob).where(
            MallJob.kind == "mall_logistics_query",
            MallJob.entity_id == package["id"],
            MallJob.entity_version == corrected_package["version"],
        )
    )
    assert new_job is not None
    new_job.next_run_at = utc_now() - timedelta(seconds=1)
    await db_session.commit()

    class SignedEvent:
        async def query(self, **_unused):
            return {
                "state": "3",
                "data": [
                    {
                        "leaveTime": "2026-11-06 12:01:00",
                        "name": "新运单已签收联系电话13800000000",
                        "stateCode": "3",
                        "status": "签收轨迹",
                    }
                ],
            }

    assert await run_mall_worker_once(
        TestAsyncSession,
        handlers=logistics_handlers(TestAsyncSession, client=SignedEvent()),
        enabled=True,
    )
    result = await client.get(logistics_url, headers=buyer_headers)
    assert result.status_code == 200
    fresh = result.json()["data"]
    assert fresh["queryStatus"] == "available" and fresh["stateCode"] == "3"
    assert "13800000000" not in result.text
    assert "13800000000" not in str(fresh["events"])
    await db_session.refresh(order)
    shipment = await db_session.get(MallShipment, int(package["id"]))
    assert order.status == "pending_receipt"
    assert shipment.platform_confirmation_status == "unknown"
    assert shipment.logistics_status == "available"

    from src.services.mall_job_service import enqueue_mall_job

    async with TestAsyncSession() as worker_db:
        current_shipment = await worker_db.get(MallShipment, int(package["id"]))
        await enqueue_mall_job(
            worker_db,
            kind="mall_logistics_query",
            entity_type="mall_shipment",
            entity_id=current_shipment.id,
            entity_version=current_shipment.version,
            dedupe_key="integration-logistics-no-record-retry",
            next_run_at=utc_now() - timedelta(seconds=1),
        )
        await worker_db.commit()

    from src.integrations.kuaidi100_client import Kuaidi100Error

    class NoRecord:
        async def query(self, **_unused):
            raise Kuaidi100Error("no_record")

    assert await run_mall_worker_once(
        TestAsyncSession,
        handlers=logistics_handlers(TestAsyncSession, client=NoRecord()),
        enabled=True,
    )
    stale_result = await client.get(logistics_url, headers=buyer_headers)
    assert stale_result.status_code == 200
    stale = stale_result.json()["data"]
    assert stale["queryStatus"] == "stale" and stale["errorCode"] == "no_record"
    assert stale["events"] == fresh["events"]
    await db_session.refresh(order)
    assert order.status == "pending_receipt"
