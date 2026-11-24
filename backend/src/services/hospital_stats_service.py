"""Internet-hospital visit event recording and admin aggregation.

The target mini program is opened by WeChat directly, so only the two events
our mini program can observe are stored. See spec 023 for the metric limits.
"""

import io
from datetime import date, datetime, timedelta, timezone

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from sqlalchemy import case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.exceptions import ValidationException
from ..models.hospital import HospitalEventType, HospitalVisitEvent
from ..models.user import User

SHANGHAI_OFFSET = timedelta(hours=8)
DEFAULT_RANGE_DAYS = 30
MAX_RANGE_DAYS = 366
EXPORT_MAX_USERS = 10000

USER_TYPE_LABELS = {
    "personal": "个人用户",
    "promoter": "推广员",
    "distributor": "客户顾问",
    "doctor": "医生",
    "admin": "管理员",
    "finance": "财务",
    "ops": "运营",
}


def shanghai_today() -> date:
    return (datetime.now(timezone.utc) + SHANGHAI_OFFSET).date()


def shanghai_date_string(moment: datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return (moment.astimezone(timezone.utc) + SHANGHAI_OFFSET).date().isoformat()


def parse_range(from_raw: str | None, to_raw: str | None) -> tuple[date, date]:
    today = shanghai_today()
    try:
        to_date = date.fromisoformat(to_raw) if to_raw else today
        from_date = (
            date.fromisoformat(from_raw)
            if from_raw
            else to_date - timedelta(days=DEFAULT_RANGE_DAYS - 1)
        )
    except ValueError as exc:
        raise ValidationException(message="日期格式必须为 YYYY-MM-DD") from exc
    if from_date > to_date:
        raise ValidationException(message="开始日期不能晚于结束日期")
    if (to_date - from_date).days + 1 > MAX_RANGE_DAYS:
        raise ValidationException(message=f"统计范围不能超过 {MAX_RANGE_DAYS} 天")
    return from_date, to_date


async def user_exists(db: AsyncSession, user_id: int) -> bool:
    return (await db.scalar(select(User.id).where(User.id == user_id))) is not None


async def record_event(
    db: AsyncSession,
    *,
    user_id: int | None,
    event_type: str,
    source: str,
) -> HospitalVisitEvent:
    now = datetime.now(timezone.utc)
    event = HospitalVisitEvent(
        user_id=user_id,
        event_type=HospitalEventType(event_type).value,
        entry_source=source,
        occurred_at=now.replace(tzinfo=None),
        occurred_date=shanghai_date_string(now),
    )
    db.add(event)
    return event


def _timestamp(value: datetime | None) -> str | None:
    return value.isoformat() + "Z" if value else None


def _empty_summary() -> dict[str, int | float]:
    return {
        "entryTapCount": 0,
        "entryTapUsers": 0,
        "qrLongpressCount": 0,
        "qrLongpressUsers": 0,
    }


def _user_aggregate_select(in_range):
    tap_count = func.sum(
        case((HospitalVisitEvent.event_type == HospitalEventType.ENTRY_TAP.value, 1), else_=0)
    )
    longpress_count = func.sum(
        case(
            (HospitalVisitEvent.event_type == HospitalEventType.QR_LONGPRESS.value, 1),
            else_=0,
        )
    )
    first_at = func.min(HospitalVisitEvent.occurred_at)
    last_at = func.max(HospitalVisitEvent.occurred_at)
    return (
        select(
            HospitalVisitEvent.user_id,
            tap_count.label("tapCount"),
            longpress_count.label("longpressCount"),
            first_at.label("firstAt"),
            last_at.label("lastAt"),
        )
        .where(in_range, HospitalVisitEvent.user_id.is_not(None))
        .group_by(HospitalVisitEvent.user_id)
        .order_by(
            longpress_count.desc(),
            tap_count.desc(),
            last_at.desc(),
            HospitalVisitEvent.user_id.asc(),
        )
    )


async def _load_users(db: AsyncSession, identities: list[int]) -> dict[int, User]:
    if not identities:
        return {}
    rows = await db.execute(select(User).where(User.id.in_(identities)))
    return {user.id: user for user in rows.scalars().all()}


def _csv_safe(value) -> str:
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text


def _local_label(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return (value.astimezone(timezone.utc) + SHANGHAI_OFFSET).strftime("%Y-%m-%d %H:%M:%S")


async def export_users_xlsx(
    db: AsyncSession, *, from_date: date, to_date: date
) -> tuple[bytes, int]:
    in_range = HospitalVisitEvent.occurred_date.between(
        from_date.isoformat(), to_date.isoformat()
    )
    rows = (
        await db.execute(_user_aggregate_select(in_range).limit(EXPORT_MAX_USERS + 1))
    ).all()
    if len(rows) > EXPORT_MAX_USERS:
        raise ValidationException(
            message=f"导出用户超过 {EXPORT_MAX_USERS} 人，请缩小日期范围"
        )
    users = await _load_users(db, [row.user_id for row in rows])

    headers = ["序号", "用户", "手机号", "身份", "组织", "点击次数", "长按次数", "首次", "最近"]
    widths = [6, 16, 16, 12, 24, 12, 12, 20, 20]
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "按用户统计"
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    for index, row in enumerate(rows, start=1):
        user = users.get(row.user_id)
        user_type = user.user_type.value if user and user.user_type else ""
        sheet.append(
            [
                index,
                _csv_safe(user.name if user else None),
                _csv_safe(user.phone if user else None),
                USER_TYPE_LABELS.get(user_type, user_type),
                _csv_safe(user.organization if user else None),
                int(row.tapCount or 0),
                int(row.longpressCount or 0),
                _local_label(row.firstAt),
                _local_label(row.lastAt),
            ]
        )
        current = sheet.max_row
        sheet.cell(row=current, column=3).number_format = "@"
        sheet.cell(row=current, column=8).number_format = "@"
        sheet.cell(row=current, column=9).number_format = "@"
    sheet.freeze_panes = "A2"
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue(), len(rows)


async def get_stats(
    db: AsyncSession,
    *,
    from_date: date,
    to_date: date,
    page: int,
    page_size: int,
) -> dict[str, object]:
    start = from_date.isoformat()
    end = to_date.isoformat()
    in_range = HospitalVisitEvent.occurred_date.between(start, end)

    summary_rows = await db.execute(
        select(
            HospitalVisitEvent.event_type,
            func.count().label("total"),
            func.count(distinct(HospitalVisitEvent.user_id)).label("users"),
        )
        .where(in_range)
        .group_by(HospitalVisitEvent.event_type)
    )
    summary = _empty_summary()
    for event_type, total, users in summary_rows:
        if event_type == HospitalEventType.ENTRY_TAP.value:
            summary["entryTapCount"] = int(total)
            summary["entryTapUsers"] = int(users)
        elif event_type == HospitalEventType.QR_LONGPRESS.value:
            summary["qrLongpressCount"] = int(total)
            summary["qrLongpressUsers"] = int(users)

    anonymous = await db.scalar(
        select(func.count())
        .select_from(HospitalVisitEvent)
        .where(in_range, HospitalVisitEvent.user_id.is_(None))
    )
    entry_users = int(summary["entryTapUsers"])
    summary["anonymousCount"] = int(anonymous or 0)
    summary["longpressRate"] = (
        round(int(summary["qrLongpressUsers"]) / entry_users, 4) if entry_users else 0.0
    )

    identified = (in_range, HospitalVisitEvent.user_id.is_not(None))

    total_users = await db.scalar(
        select(func.count(distinct(HospitalVisitEvent.user_id))).where(*identified)
    )
    user_rows = (
        await db.execute(
            _user_aggregate_select(in_range).limit(page_size).offset((page - 1) * page_size)
        )
    ).all()
    users = await _load_users(db, [row.user_id for row in user_rows])

    items = []
    for row in user_rows:
        user = users.get(row.user_id)
        items.append(
            {
                "userId": str(row.user_id),
                "name": (user.name if user else None) or f"用户{row.user_id}",
                "phone": user.phone if user else None,
                "userType": user.user_type.value if user and user.user_type else "",
                "organization": (user.organization if user else None) or "",
                "entryTapCount": int(row.tapCount or 0),
                "qrLongpressCount": int(row.longpressCount or 0),
                "firstAt": _timestamp(row.firstAt),
                "lastAt": _timestamp(row.lastAt),
            }
        )

    daily_rows = await db.execute(
        select(
            HospitalVisitEvent.occurred_date,
            HospitalVisitEvent.event_type,
            func.count().label("total"),
            func.count(distinct(HospitalVisitEvent.user_id)).label("users"),
        )
        .where(in_range)
        .group_by(HospitalVisitEvent.occurred_date, HospitalVisitEvent.event_type)
    )
    daily_map: dict[str, dict[str, int]] = {}
    for event_date, event_type, total, users_count in daily_rows:
        bucket = daily_map.setdefault(
            event_date,
            {
                "entryTapCount": 0,
                "entryTapUsers": 0,
                "qrLongpressCount": 0,
                "qrLongpressUsers": 0,
            },
        )
        if event_type == HospitalEventType.ENTRY_TAP.value:
            bucket["entryTapCount"] = int(total)
            bucket["entryTapUsers"] = int(users_count)
        elif event_type == HospitalEventType.QR_LONGPRESS.value:
            bucket["qrLongpressCount"] = int(total)
            bucket["qrLongpressUsers"] = int(users_count)

    daily = []
    cursor = from_date
    while cursor <= to_date:
        key = cursor.isoformat()
        daily.append(
            {
                "date": key,
                **daily_map.get(
                    key,
                    {
                        "entryTapCount": 0,
                        "entryTapUsers": 0,
                        "qrLongpressCount": 0,
                        "qrLongpressUsers": 0,
                    },
                ),
            }
        )
        cursor += timedelta(days=1)

    return {
        "range": {"from": start, "to": end},
        "summary": summary,
        "users": {
            "items": items,
            "total": int(total_users or 0),
            "page": page,
            "pageSize": page_size,
        },
        "daily": daily,
    }
