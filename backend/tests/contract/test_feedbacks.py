"""Core contract coverage for the feedback submission APIs."""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token
from src.models.feedback import Feedback
from tests.conftest import assert_response_envelope, seed_user


def _headers(user_id: int, key: str = "feedback-submit-key") -> dict:
    token = create_access_token(data={"sub": str(user_id), "user_type": "promoter"})
    return {"Authorization": f"Bearer {token}", "Idempotency-Key": key}


async def test_feedback_submit_is_persisted_and_idempotent(client: AsyncClient, db_session: AsyncSession):
    user_id = await seed_user(db_session, openid="feedback_submitter", phone="13800138000")
    payload = {"type": "bug", "content": "客户绑定页面提交后没有显示任何结果", "imageFiles": []}

    first = await client.post("/api/v1/feedbacks", json=payload, headers=_headers(user_id))
    second = await client.post("/api/v1/feedbacks", json=payload, headers=_headers(user_id))
    assert first.status_code == second.status_code == 200
    assert_response_envelope(first.json())
    assert first.json()["data"]["feedbackNo"] == second.json()["data"]["feedbackNo"]
    rows = (await db_session.execute(select(Feedback))).scalars().all()
    assert len(rows) == 1
    assert rows[0].status == "submitted"


async def test_feedback_rejects_same_key_with_different_payload(client: AsyncClient, db_session: AsyncSession):
    user_id = await seed_user(db_session, openid="feedback_conflict")
    headers = _headers(user_id, "same-key")
    await client.post("/api/v1/feedbacks", json={"type": "other", "content": "第一条可以提交的反馈内容", "imageFiles": []}, headers=headers)
    response = await client.post("/api/v1/feedbacks", json={"type": "other", "content": "第二条不同的反馈内容需要拒绝", "imageFiles": []}, headers=headers)
    assert response.status_code == 409
    assert response.json()["code"] == 40911
