"""Administrator orders obey live RBAC and never share their private projection with buyers."""

from uuid import uuid4

import pytest
from sqlalchemy import select

from src.models.audit import AuditLog
from src.models.role import Role
from src.models.user import admin_account_roles
from tests.conftest import auth_header, make_access_token, seed_admin
from tests.unit.test_mall_aftersale_service import paid_order
from tests.unit.test_mall_order_actions import unattempted
from tests.unit.test_mall_payment_service import payable


async def admin(db, permissions):
    identity = await seed_admin(db, username="order-admin-" + uuid4().hex)
    role = Role(name="商城订单测试-" + uuid4().hex, permissions={"permissions": permissions})
    db.add(role)
    await db.flush()
    await db.execute(
        admin_account_roles.insert().values(admin_account_id=identity, role_id=role.id)
    )
    await db.commit()
    return (
        identity,
        role,
        auth_header(
            make_access_token(user_id=identity, user_type="admin", permissions=permissions)
        ),
    )


@pytest.mark.asyncio
async def test_admin_order_detail_has_safe_identity_and_private_events_do_not_reach_buyer(
    client, db_session, monkeypatch
):
    actor, _, _, _, order = await unattempted(db_session, monkeypatch)
    identity, _, headers = await admin(db_session, ["mall.orders.read", "mall.orders.write"])
    url = f"/api/v1/admin/mall/orders/{order.id}"
    result = await client.get(url, headers=headers)
    assert result.status_code == 200, result.text
    detail = result.json()["data"]
    assert detail["buyer"]["id"] == str(actor.actor_id)
    assert detail["internalNote"] is None and detail["shipment"] is None
    assert not detail["fulfillmentCheck"]["businessReady"]
    assert (
        "noteMallOrder" in detail["availableActions"]
        and "shipMallOrder" not in detail["availableActions"]
    )
    assert result.headers["cache-control"] == "no-store"
    headers["Idempotency-Key"] = "admin-order-note-intent-001"
    data = {"expectedVersion": order.version, "internalNote": "仓库核实，联系13800001234"}
    note = await client.patch(url + "/note", headers=headers, json=data)
    assert note.status_code == 200, note.text
    assert (await client.patch(url + "/note", headers=headers, json=data)).json()["data"][
        "version"
    ] == note.json()["data"]["version"]
    detail_response = await client.get(url, headers=headers)
    assert "13800001234" not in detail_response.text
    assert "138****1234" in detail_response.json()["data"]["internalNote"]
    buyer = await client.get(
        f"/api/v1/mall/orders/{order.id}",
        headers=auth_header(make_access_token(user_id=actor.actor_id, user_type="personal")),
    )
    assert "internalNote" not in buyer.text and "仓库核实" not in buyer.text
    assert all(
        event["action"] != "internal_note_updated" for event in buyer.json()["data"]["timeline"]
    )
    audit = await db_session.scalar(
        select(AuditLog).where(AuditLog.action == "mall_admin_order_note")
    )
    assert audit.user_id is None and audit.detail["adminAccountId"] == str(identity)
    assert "13800001234" not in str(audit.detail)


@pytest.mark.asyncio
async def test_admin_list_filters_cursor_and_live_revocation(client, db_session, monkeypatch):
    _, _, _, _, first = await unattempted(db_session, monkeypatch)
    _, _, headers = await admin(db_session, ["mall.orders.read"])
    root = "/api/v1/admin/mall/orders"
    page = await client.get(root, headers=headers, params={"orderNo": first.order_no})
    assert page.status_code == 200 and page.json()["data"]["total"] == 1
    assert (await client.get(root, headers=headers, params={"status": "closed"})).json()["data"][
        "total"
    ] == 0
    assert (
        await client.get(root, headers=headers, params={"from": "2026-11-06"})
    ).status_code == 422
    assert (
        await client.get(
            root,
            headers=headers,
            params={"from": "2026-12-01T00:00:00Z", "to": "2026-11-01T00:00:00Z"},
        )
    ).status_code == 422
    _, role, permitted = await admin(db_session, ["mall.orders.read", "mall.orders.write"])
    role.permissions = {"permissions": []}
    await db_session.commit()
    permitted["Idempotency-Key"] = "revoked-admin-note-001"
    assert (await client.get(root, headers=permitted)).status_code == 403
    assert (
        await client.patch(
            f"{root}/{first.id}/note",
            headers=permitted,
            json={"expectedVersion": first.version, "internalNote": "无权"},
        )
    ).status_code == 403
    headers["Idempotency-Key"] = "read-only-note-denied-001"
    assert (
        await client.patch(
            f"{root}/{first.id}/note",
            headers=headers,
            json={"expectedVersion": first.version, "internalNote": "只读"},
        )
    ).status_code == 403


@pytest.mark.asyncio
async def test_admin_order_list_exposes_payment_identifiers_but_not_to_buyers(
    client, db_session, monkeypatch
):
    actor, order, _, _ = await paid_order(db_session, monkeypatch)
    _, _, headers = await admin(db_session, ["mall.orders.read"])
    root = "/api/v1/admin/mall/orders"
    page = await client.get(root, headers=headers, params={"orderNo": order.order_no})
    assert page.status_code == 200, page.text
    item = page.json()["data"]["items"][0]
    assert item["outTradeNo"].startswith("P")
    assert item["channelTransactionId"] == "synthetic-channel-id"

    buyer = await client.get(
        f"/api/v1/mall/orders/{order.id}",
        headers=auth_header(make_access_token(user_id=actor.actor_id, user_type="personal")),
    )
    assert buyer.status_code == 200, buyer.text
    assert "outTradeNo" not in buyer.json()["data"]
    assert "channelTransactionId" not in buyer.json()["data"]


@pytest.mark.asyncio
async def test_admin_cancel_preserves_channel_reservation_and_raw_release_stays_closed(
    client, db_session, monkeypatch
):
    _, order, skus, _ = await payable(db_session, monkeypatch)
    _, _, headers = await admin(
        db_session, ["mall.orders.read", "mall.orders.write", "mall.fulfillment.release"]
    )
    headers["Idempotency-Key"] = "admin-cancel-intent-001"
    root = f"/api/v1/admin/mall/orders/{order.id}"
    cancel = await client.post(
        root + "/cancel",
        headers=headers,
        json={"expectedVersion": order.version, "reason": "买家申请取消"},
    )
    assert cancel.status_code == 202, cancel.text
    result = cancel.json()["data"]
    assert result["status"] == "pending"
    progress = await client.get(
        f'/api/v1/admin/mall/commands/{result["commandId"]}', headers=headers
    )
    assert progress.json()["data"]["status"] == "pending"
    await db_session.refresh(order)
    assert order.status == "pending_payment" and skus[0].reserved_qty == 1
    response = await client.post(
        root + "/fulfillment-release",
        headers=headers,
        json={"expectedVersion": order.version, "purpose": "shipping_label", "reason": "发货"},
    )
    assert response.status_code == 403 and "13800001234" not in response.text


@pytest.mark.asyncio
async def test_admin_immediate_close_uses_admin_audit_identity_and_buyer_safe_event(
    client, db_session, monkeypatch
):
    from src.models.mall_catalog import MallStockMovement

    actor, _, _, _, order = await unattempted(db_session, monkeypatch)
    identity, _, headers = await admin(db_session, ["mall.orders.read", "mall.orders.write"])
    headers["Idempotency-Key"] = "admin-local-cancel-intent-001"
    result = await client.post(
        f"/api/v1/admin/mall/orders/{order.id}/cancel",
        headers=headers,
        json={"expectedVersion": order.version, "reason": "买家电话13800001234"},
    )
    assert result.status_code == 202 and result.json()["data"]["status"] == "completed"
    audit = await db_session.scalar(
        select(AuditLog).where(AuditLog.action == "mall_admin_order_closed")
    )
    movement = await db_session.scalar(
        select(MallStockMovement).where(MallStockMovement.kind == "release").limit(1)
    )
    assert audit.user_id is None and audit.detail["adminAccountId"] == str(identity)
    assert movement.actor_type == "admin" and movement.actor_id == identity
    buyer = await client.get(
        f"/api/v1/mall/orders/{order.id}",
        headers=auth_header(make_access_token(user_id=actor.actor_id, user_type="personal")),
    )
    assert buyer.json()["data"]["timeline"][-1]["actorLabel"] == "商家"
    assert "13800001234" not in buyer.text


@pytest.mark.asyncio
async def test_admin_cursor_is_filter_bound_and_time_range_is_half_open(
    client, db_session, monkeypatch
):
    from datetime import datetime

    _, _, _, _, older = await unattempted(db_session, monkeypatch)
    older.created_at = datetime(2026, 11, 1)
    await db_session.commit()
    _, _, _, _, newer = await unattempted(db_session, monkeypatch)
    newer.created_at = datetime(2026, 11, 2)
    await db_session.commit()
    _, _, headers = await admin(db_session, ["mall.orders.read"])
    root = "/api/v1/admin/mall/orders"
    first = (await client.get(root, headers=headers, params={"pageSize": 1})).json()["data"]
    assert first["total"] == 2 and first["items"][0]["id"] == str(newer.id)
    second = (
        await client.get(
            root, headers=headers, params={"pageSize": 1, "cursor": first["nextCursor"]}
        )
    ).json()["data"]
    assert second["items"][0]["id"] == str(older.id) and second["nextCursor"] is None
    assert (
        await client.get(
            root, headers=headers, params={"cursor": first["nextCursor"], "status": "closed"}
        )
    ).status_code == 422
    result = await client.get(
        root, headers=headers, params={"from": "2026-11-01T00:00:00Z", "to": "2026-11-02T00:00:00Z"}
    )
    assert [x["id"] for x in result.json()["data"]["items"]] == [str(older.id)]
    events = (
        await db_session.scalars(
            select(AuditLog).where(AuditLog.action == "mall_admin_orders_read")
        )
    ).all()
    assert any(str(older.id) in e.detail.get("orderIds", []) for e in events)
