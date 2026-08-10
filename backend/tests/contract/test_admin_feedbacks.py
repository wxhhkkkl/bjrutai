from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token
from src.models.feedback import Feedback
from src.models.notification import Notification
from tests.conftest import seed_admin, seed_user


def _admin_headers(admin_id: int, *permissions: str) -> dict:
    token = create_access_token(data={"sub": str(admin_id), "user_type": "admin", "permissions": list(permissions)})
    return {"Authorization": f"Bearer {token}"}


async def _submit(client: AsyncClient, user_id: int) -> str:
    token = create_access_token(data={"sub": str(user_id), "user_type": "promoter"})
    response = await client.post("/api/v1/feedbacks", json={"type": "suggestion", "content": "建议增加更方便的客户筛选和保存能力", "imageFiles": []}, headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "admin-feedback-seed"})
    return response.json()["data"]["feedbackNo"]


async def test_admin_lists_and_resolves_feedback(client: AsyncClient, db_session: AsyncSession):
    user_id = await seed_user(db_session, openid="admin_feedback_user", phone="13900001234")
    admin_id = await seed_admin(db_session, username="feedback_admin")
    feedback_no = await _submit(client, user_id)
    headers = _admin_headers(admin_id, "feedbacks.read", "feedbacks.write")
    listing = await client.get("/api/v1/admin/feedbacks", headers=headers)
    assert listing.status_code == 200
    assert listing.json()["data"]["items"][0]["submitter"]["phoneMasked"] == "139****1234"
    detail = await client.get(f"/api/v1/admin/feedbacks/{feedback_no}", headers=headers)
    version = detail.json()["data"]["version"]
    resolved = await client.patch(f"/api/v1/admin/feedbacks/{feedback_no}", json={"expectedVersion": version, "status": "resolved", "resolution": "已完成优化，请重新进入页面查看。"}, headers=headers)
    assert resolved.status_code == 200
    assert resolved.json()["data"]["status"] == "resolved"
    assert resolved.json()["data"]["notificationStatus"] == "sent"
    assert (await db_session.execute(select(Notification))).scalars().one().user_id == user_id


async def test_admin_feedback_requires_read_permission(client: AsyncClient, db_session: AsyncSession):
    admin_id = await seed_admin(db_session, username="no_feedback_admin")
    response = await client.get("/api/v1/admin/feedbacks", headers=_admin_headers(admin_id))
    assert response.status_code == 403
