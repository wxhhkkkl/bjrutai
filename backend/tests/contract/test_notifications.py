"""Contract tests for the current-user notification center."""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token
from src.models.notification import Notification, NotificationCategory
from tests.conftest import assert_response_envelope, seed_user


def _headers(user_id: int) -> dict:
    token = create_access_token(data={"sub": str(user_id), "user_type": "promoter"})
    return {"Authorization": f"Bearer {token}"}


async def test_notifications_are_scoped_and_read_all_updates_only_current_user(
    client: AsyncClient, db_session: AsyncSession
):
    user_id = await seed_user(db_session, openid="notification_owner")
    other_id = await seed_user(db_session, openid="notification_other")
    db_session.add_all([
        Notification(user_id=user_id, category=NotificationCategory.SYSTEM, title="自己的消息"),
        Notification(user_id=other_id, category=NotificationCategory.SYSTEM, title="别人的消息"),
    ])
    await db_session.commit()

    response = await client.get("/api/v1/notifications", headers=_headers(user_id))
    body = response.json()
    assert response.status_code == 200
    assert_response_envelope(body)
    assert [item["title"] for item in body["data"]["items"]] == ["自己的消息"]
    assert body["data"]["unreadCount"] == 1

    read_all = await client.post("/api/v1/notifications/read-all", headers=_headers(user_id))
    assert read_all.status_code == 200
    assert read_all.json()["data"]["updatedCount"] == 1

    own = (await db_session.execute(select(Notification).where(Notification.user_id == user_id))).scalars().one()
    other = (await db_session.execute(select(Notification).where(Notification.user_id == other_id))).scalars().one()
    assert own.is_read is True
    assert other.is_read is False
