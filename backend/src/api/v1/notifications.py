"""Notification endpoints (T175).

GET  /notifications        – list with category filter, unreadOnly, cursor pagination
POST /notifications/{id}/read – mark as read
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_current_user, get_db
from ...core.exceptions import NotFoundException
from ...models.notification import Notification, NotificationCategory

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _ok(data=None) -> dict:
    return {
        "code": 0,
        "message": "success",
        "data": data,
        "requestId": uuid.uuid4().hex,
        "serverTime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# ──────────────────────────────────────────────────────────────────
# GET /notifications
# ──────────────────────────────────────────────────────────────────
@router.get("")
async def list_notifications(
    category: Optional[str] = Query(None, description="system, binding, promotion, bill, followup, qualification"),
    unreadOnly: bool = Query(False, alias="unreadOnly"),
    cursor: Optional[str] = Query(None, description="Pagination cursor (last id)"),
    pageSize: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """List notifications for the current user with optional filters."""
    user_id = int(payload["sub"])

    query = select(Notification).where(Notification.user_id == user_id)

    if category:
        try:
            cat_enum = getattr(NotificationCategory, category.upper())
            query = query.where(Notification.category == cat_enum)
        except (AttributeError, KeyError):
            pass

    if unreadOnly:
        query = query.where(Notification.is_read == False)

    if cursor:
        try:
            cursor_id = int(cursor)
            query = query.where(Notification.id < cursor_id)
        except (ValueError, TypeError):
            pass

    query = query.order_by(desc(Notification.id)).limit(pageSize + 1)
    result = await db.execute(query)
    rows = result.scalars().all()

    has_more = len(rows) > pageSize
    items = rows[:pageSize]
    next_cursor = str(items[-1].id) if has_more and items else None

    data_items = []
    for n in items:
        data_items.append({
            "id": str(n.id),
            "category": n.category.value if hasattr(n.category, "value") else str(n.category),
            "title": n.title,
            "summary": n.summary,
            "target": n.target,
            "isRead": n.is_read,
            "readAt": n.read_at.isoformat() if n.read_at else None,
            "createdAt": n.created_at.isoformat() if n.created_at else None,
        })

    # Count unread
    unread_result = await db.execute(
        select(Notification).where(
            Notification.user_id == user_id,
            Notification.is_read == False,
        )
    )
    unread_count = len(unread_result.scalars().all())

    return _ok({
        "items": data_items,
        "nextCursor": next_cursor,
        "hasMore": has_more,
        "unreadCount": unread_count,
    })


# ──────────────────────────────────────────────────────────────────
# POST /notifications/{id}/read
# ──────────────────────────────────────────────────────────────────
@router.post("/{notification_id}/read")
async def mark_as_read(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """Mark a notification as read."""
    user_id = int(payload["sub"])

    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
        )
    )
    notification = result.scalars().first()
    if notification is None:
        raise NotFoundException(message="Notification not found")

    notification.is_read = True
    notification.read_at = datetime.now(timezone.utc)
    db.add(notification)
    await db.commit()

    return _ok({
        "id": str(notification.id),
        "isRead": True,
        "readAt": notification.read_at.isoformat() if notification.read_at else None,
    })
