"""Internet-hospital visit intents: public recording and admin aggregation."""

from datetime import datetime, timedelta, timezone
from io import BytesIO
from uuid import uuid4

import pytest
from openpyxl import load_workbook
from sqlalchemy import select

from src.models.audit import AuditLog
from src.models.hospital import HospitalVisitEvent
from src.models.role import Role
from src.models.user import admin_account_roles
from tests.conftest import auth_header, make_access_token, seed_admin, seed_user


def today():
    return (datetime.now(timezone.utc) + timedelta(hours=8)).date()


async def admin(db, permissions):
    identity = await seed_admin(db, username="hospital-admin-" + uuid4().hex)
    role = Role(name="互联网医院统计-" + uuid4().hex, permissions={"permissions": permissions})
    db.add(role)
    await db.flush()
    await db.execute(
        admin_account_roles.insert().values(admin_account_id=identity, role_id=role.id)
    )
    await db.commit()
    return identity, auth_header(
        make_access_token(user_id=identity, user_type="admin", permissions=permissions)
    )


async def post_event(client, event, user_id=None, user_type="personal"):
    headers = {}
    if user_id is not None:
        headers = auth_header(make_access_token(user_id=user_id, user_type=user_type))
    return await client.post("/api/v1/hospital/events", json={"event": event}, headers=headers)


@pytest.mark.asyncio
async def test_records_anonymous_and_identified_events(client, db_session):
    anonymous = await post_event(client, "entry_tap")
    assert anonymous.status_code == 200, anonymous.text
    assert anonymous.json()["data"] == {"recorded": True}

    user_id = await seed_user(db_session, openid="hospital-" + uuid4().hex)
    await db_session.commit()
    logged = await post_event(client, "qr_longpress", user_id=user_id)
    assert logged.status_code == 200, logged.text

    rows = (
        await db_session.execute(select(HospitalVisitEvent).order_by(HospitalVisitEvent.id))
    ).scalars().all()
    assert [row.event_type for row in rows] == ["entry_tap", "qr_longpress"]
    assert rows[0].user_id is None
    assert rows[1].user_id == user_id
    assert rows[1].occurred_date == today().isoformat()


@pytest.mark.asyncio
async def test_rejects_unknown_event_type(client):
    response = await post_event(client, "opened_target")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_admin_stats_aggregate_users_and_require_permission(client, db_session):
    first = await seed_user(
        db_session,
        openid="hospital-a-" + uuid4().hex,
        name="张力",
        phone="13800001234",
        user_type="personal",
    )
    second = await seed_user(
        db_session, openid="hospital-b-" + uuid4().hex, name="王敏", user_type="promoter"
    )
    await db_session.commit()

    for event, user_id in [
        ("entry_tap", first),
        ("qr_longpress", first),
        ("entry_tap", second),
        ("entry_tap", None),
    ]:
        assert (await post_event(client, event, user_id=user_id)).status_code == 200

    _, headers = await admin(db_session, ["hospital.stats.read"])
    result = await client.get("/api/v1/admin/hospital/stats", headers=headers)
    assert result.status_code == 200, result.text
    assert result.headers["cache-control"] == "no-store"
    data = result.json()["data"]

    assert data["range"] == {"from": (today() - timedelta(days=29)).isoformat(), "to": today().isoformat()}
    summary = data["summary"]
    assert summary["entryTapCount"] == 3
    assert summary["entryTapUsers"] == 2
    assert summary["qrLongpressCount"] == 1
    assert summary["qrLongpressUsers"] == 1
    assert summary["anonymousCount"] == 1
    assert summary["longpressRate"] == 0.5

    users = data["users"]["items"]
    assert data["users"]["total"] == 2
    assert users[0]["userId"] == str(first)
    assert users[0]["entryTapCount"] == 1 and users[0]["qrLongpressCount"] == 1
    assert users[0]["phone"] == "13800001234"
    assert users[1]["userId"] == str(second)
    assert users[1]["entryTapCount"] == 1 and users[1]["qrLongpressCount"] == 0
    assert len(data["daily"]) == 30
    assert data["daily"][-1]["date"] == today().isoformat()
    assert data["daily"][-1]["entryTapCount"] == 3

    audit = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.action == "hospital_stats_read")
        )
    ).scalars().first()
    assert audit is not None
    assert audit.user_id is None

    _, denied = await admin(db_session, [])
    forbidden = await client.get("/api/v1/admin/hospital/stats", headers=denied)
    assert forbidden.status_code == 403


@pytest.mark.asyncio
async def test_admin_stats_rejects_invalid_ranges(client, db_session):
    _, headers = await admin(db_session, ["hospital.stats.read"])
    bad_format = await client.get(
        "/api/v1/admin/hospital/stats", params={"from": "2026-13-01"}, headers=headers
    )
    assert bad_format.status_code == 422
    reversed_range = await client.get(
        "/api/v1/admin/hospital/stats",
        params={"from": "2026-11-24", "to": "2026-11-01"},
        headers=headers,
    )
    assert reversed_range.status_code == 422
    too_long = await client.get(
        "/api/v1/admin/hospital/stats",
        params={"from": "2024-01-01", "to": "2026-11-24"},
        headers=headers,
    )
    assert too_long.status_code == 422


@pytest.mark.asyncio
async def test_export_users_xlsx_matches_range_and_audits(client, db_session):
    first = await seed_user(
        db_session,
        openid="hospital-export-a-" + uuid4().hex,
        name="张力",
        phone="13800001234",
        user_type="personal",
    )
    second = await seed_user(
        db_session, openid="hospital-export-b-" + uuid4().hex, name="王敏", user_type="promoter"
    )
    await db_session.commit()

    assert (await post_event(client, "entry_tap", user_id=first)).status_code == 200
    assert (await post_event(client, "qr_longpress", user_id=first)).status_code == 200
    assert (await post_event(client, "entry_tap", user_id=second)).status_code == 200

    _, headers = await admin(db_session, ["hospital.stats.read"])
    day = today().isoformat()
    response = await client.get(
        "/api/v1/admin/hospital/stats/export",
        params={"from": day, "to": day},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert ".xlsx" in response.headers["content-disposition"]
    assert response.headers["cache-control"] == "no-store"

    sheet = load_workbook(BytesIO(response.content)).active
    rows = list(sheet.iter_rows(values_only=True))
    assert rows[0] == ("序号", "用户", "手机号", "身份", "组织", "点击次数", "长按次数", "首次", "最近")
    assert len(rows) == 3
    assert rows[1][:4] == (1, "张力", "13800001234", "个人用户")
    assert rows[1][5] == 1 and rows[1][6] == 1
    assert isinstance(rows[1][7], str) and rows[1][7].startswith("20")
    assert rows[2][1] == "王敏" and rows[2][2] in (None, "")
    assert rows[2][3] == "推广员" and rows[2][5] == 1 and rows[2][6] == 0

    audit = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.action == "hospital_stats_export")
        )
    ).scalars().first()
    assert audit is not None
    assert audit.user_id is None
    assert audit.detail["rowCount"] == 2

    empty_day = (today() - timedelta(days=5)).isoformat()
    empty = await client.get(
        "/api/v1/admin/hospital/stats/export",
        params={"from": empty_day, "to": empty_day},
        headers=headers,
    )
    assert empty.status_code == 200
    empty_rows = list(load_workbook(BytesIO(empty.content)).active.iter_rows(values_only=True))
    assert len(empty_rows) == 1

    _, denied = await admin(db_session, [])
    forbidden = await client.get(
        "/api/v1/admin/hospital/stats/export",
        params={"from": day, "to": day},
        headers=denied,
    )
    assert forbidden.status_code == 403
