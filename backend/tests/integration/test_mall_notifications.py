"""In-app mall notices and unknown-funds responsibility escalation."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from src.models.mall_operations import MallJob
from src.models.notification import Notification, NotificationCategory
from src.models.user import UserType
from src.services.mall_notification_service import schedule_overdue_funds_responsibilities
from tests.conftest import TestAsyncSession, seed_user
from tests.unit.test_mall_payment_service import payable, success


@pytest.mark.asyncio
async def test_buyer_mall_notice_is_idempotent_and_visible_in_notification_center(
    client, db_session
):
    buyer_id = await seed_user(db_session, openid="mall_notice_buyer", user_type="personal")
    other_id = await seed_user(db_session, openid="mall_notice_other", user_type="personal")
    from src.services.mall_notification_service import notify_mall_buyer

    args = {
        "buyer_user_id": buyer_id,
        "event_key": "mall:payment:501:succeeded",
        "title": "商城支付结果已确认",
        "summary": "订单号 M202611080001 的支付已核实，订单正在等待发货。",
        "target": "/pages/mall-order-detail/index?id=501",
    }
    assert await notify_mall_buyer(db_session, **args)
    assert not await notify_mall_buyer(db_session, **args)
    await db_session.commit()

    response = await client.get(
        "/api/v1/notifications?category=mall", headers=_headers(buyer_id)
    )
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["category"] == "mall"
    assert items[0]["target"] == args["target"]

    other = await client.get(
        "/api/v1/notifications?category=mall", headers=_headers(other_id)
    )
    assert other.json()["data"]["items"] == []
    assert await db_session.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.event_key == args["event_key"])
    ) == 1


def _headers(user_id: int) -> dict:
    from src.core.security import create_access_token

    token = create_access_token(data={"sub": str(user_id), "user_type": "personal"})
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_notice_storage_failure_queues_retry_without_rolling_back_payment(
    db_session, monkeypatch
):
    from src.services import mall_notification_service as notices
    from src.services.mall_payment_service import apply_verified_payment
    from src.tasks.mall_tasks import run_mall_worker_once

    actor, order, _, payment = await payable(db_session, monkeypatch)
    real_persist = notices._persist_notification

    async def fail_insert(*_args, **_kwargs):
        raise RuntimeError("synthetic in-app storage failure")

    monkeypatch.setattr(notices, "_persist_notification", fail_insert)
    await apply_verified_payment(db_session, payment.id, success(payment, order))
    await db_session.commit()

    assert payment.status == "succeeded"
    assert order.status == "pending_shipment"
    retry = await db_session.scalar(
        select(MallJob).where(MallJob.kind == "mall_notification_deliver")
    )
    assert retry is not None and retry.status == "ready"
    assert retry.notification_payload["userId"] == actor.actor_id
    assert await db_session.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.event_key == retry.notification_payload["eventKey"])
    ) == 0

    monkeypatch.setattr(notices, "_persist_notification", real_persist)
    assert await run_mall_worker_once(
        TestAsyncSession,
        handlers=notices.mall_notification_handlers(TestAsyncSession),
        enabled=True,
    )
    await db_session.refresh(retry)
    assert retry.status == "done"
    assert await db_session.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.event_key == retry.notification_payload["eventKey"])
    ) == 1


@pytest.mark.asyncio
async def test_unknown_funds_task_is_strictly_over_ten_minutes_and_closes_on_verified_state(
    db_session, monkeypatch
):
    _, _, _, payment = await payable(db_session, monkeypatch)
    finance_id = await seed_user(
        db_session, openid="mall_notice_finance", user_type=UserType.FINANCE.value
    )
    start = datetime(2026, 11, 8, 3, 0, 0)
    payment.status = "unknown"
    payment.unknown_since = start
    payment.last_query_at = start
    await db_session.commit()

    assert await schedule_overdue_funds_responsibilities(
        db_session, now=start + timedelta(minutes=10)
    ) == 0
    await db_session.commit()

    scan_time = start + timedelta(minutes=10, microseconds=1)
    assert await schedule_overdue_funds_responsibilities(db_session, now=scan_time) == 1
    await db_session.commit()
    assert await schedule_overdue_funds_responsibilities(db_session, now=scan_time) == 0
    await db_session.commit()

    task = await db_session.scalar(
        select(MallJob).where(MallJob.kind == "mall_funds_unknown_responsibility")
    )
    assert task is not None and task.status == "manual"
    assert task.responsibility_role == "finance"
    assert task.responsibility_first_discovered_at == scan_time
    assert task.responsibility_last_verified_at == scan_time
    assert task.responsibility_evidence["status"] == "unknown"
    assert task.responsibility_evidence["recordType"] == "payment"
    assert "不得按失败关闭" in task.responsibility_next_step
    assert await db_session.scalar(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.user_id == finance_id,
            Notification.category == NotificationCategory.MALL,
        )
    ) == 1

    new_interval = start + timedelta(minutes=11)
    payment.unknown_since = new_interval
    payment.last_query_at = new_interval
    await db_session.commit()
    second_scan = new_interval + timedelta(minutes=10, microseconds=1)
    assert await schedule_overdue_funds_responsibilities(db_session, now=second_scan) == 1
    await db_session.commit()
    tasks = (
        await db_session.scalars(
            select(MallJob)
            .where(MallJob.kind == "mall_funds_unknown_responsibility")
            .order_by(MallJob.id)
        )
    ).all()
    assert len(tasks) == 2
    assert all(row.status == "manual" and row.resolution_code is None for row in tasks)
    assert tasks[0].responsibility_evidence["unknownSince"] == start.isoformat(
        timespec="microseconds"
    )
    assert tasks[0].responsibility_evidence["currentUnknownSince"] == new_interval.isoformat(
        timespec="microseconds"
    )
    assert await db_session.scalar(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.user_id == finance_id,
            Notification.category == NotificationCategory.MALL,
        )
    ) == 2

    payment.status = "succeeded"
    payment.unknown_since = None
    payment.last_query_at = second_scan + timedelta(minutes=1)
    await db_session.commit()
    assert await schedule_overdue_funds_responsibilities(
        db_session, now=second_scan + timedelta(minutes=1)
    ) == 0
    await db_session.commit()
    for task in tasks:
        await db_session.refresh(task)
        assert task.status == "done"
        assert task.resolution_code == "payment_succeeded"
        assert task.resolved_by_type == "system"
