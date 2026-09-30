import hashlib
import time
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from src.main import app
from src.models.article import Article
from src.models.article_video import ArticleVideo, VideoStatus
from src.services.tencent_vod import get_vod_client
from tests.conftest import (
    TestAsyncSession,
    auth_header,
    make_access_token,
    seed_admin,
    vod_media,
    vod_procedure_event,
    vod_upload_event,
)


def headers(admin_id=1):
    return auth_header(
        make_access_token(user_id=admin_id, user_type="admin", permissions=["articles.write"])
    )


def signed(event):
    expiry = int(time.time()) + 600
    return {
        **event,
        "T": expiry,
        "Sign": hashlib.md5(f"test-callback{expiry}".encode()).hexdigest(),
    }


async def upload(client, db_session):
    response = await client.post(
        "/api/v1/admin/article-videos/uploads",
        headers=headers(),
        json={"fileName": "video.mov", "contentType": "video/quicktime", "sizeBytes": 100},
    )
    assert response.status_code == 201
    assert "test-secret" not in response.text
    data = response.json()["data"]
    return await db_session.get(ArticleVideo, int(data["videoId"]))


@pytest.mark.asyncio
async def test_upload_callbacks_draft_publish_replace_remove(client, db_session, vod_settings):
    await seed_admin(db_session)
    cloud = AsyncMock()
    app.dependency_overrides[get_vod_client] = lambda: cloud
    first = await upload(client, db_session)
    own_status = await client.get(f"/api/v1/admin/article-videos/{first.id}", headers=headers())
    assert own_status.status_code == 200
    assert own_status.json()["data"]["status"] == "authorized"
    cloud.describe_media.return_value = vod_media(first.upload_session_id)
    cloud.describe_task.return_value = vod_procedure_event(first.upload_session_id)[
        "ProcedureStateChangeEvent"
    ]
    # Upload notification creates processing state. Drafts may persist it.
    response = await client.post(
        "/api/v1/integrations/tencent-vod/events",
        json=signed(vod_upload_event(first.upload_session_id)),
    )
    assert response.status_code == 200
    response = await client.post(
        "/api/v1/admin/articles",
        headers=headers(),
        json={"title": "视频文章", "content": "<p>图文内容</p>", "videoId": str(first.id)},
    )
    article_id = int(response.json()["data"]["articleId"])
    article = await db_session.get(Article, article_id)
    assert (
        await client.post(f"/api/v1/admin/articles/{article_id}/publish", headers=headers())
    ).status_code == 409
    assert (await client.get(f"/api/v1/articles/{article_id}")).status_code == 404
    event = signed(vod_procedure_event(first.upload_session_id))
    assert (
        await client.post("/api/v1/integrations/tencent-vod/events", json=event)
    ).status_code == 200
    assert (
        await client.post("/api/v1/integrations/tencent-vod/events", json=event)
    ).status_code == 200
    assert (
        await client.post(f"/api/v1/admin/articles/{article_id}/publish", headers=headers())
    ).status_code == 200
    assert (await client.get(f"/api/v1/articles/{article_id}")).json()["data"]["video"][
        "playbackUrl"
    ] == first.playback_url
    admin_list = (await client.get("/api/v1/admin/articles", headers=headers())).json()["data"][
        "items"
    ]
    assert admin_list[0]["video"]["status"] == "ready"
    assert (
        await client.get(f"/api/v1/admin/article-videos/{first.id}", headers=headers(2))
    ).status_code == 200
    second = await upload(client, db_session)
    response = await client.put(
        f"/api/v1/admin/articles/{article_id}",
        headers=headers(),
        json={"version": article.version, "title": "不能覆盖旧内容", "videoId": str(second.id)},
    )
    assert response.status_code == 409
    assert article.video_id == first.id
    assert article.title == "视频文章"
    assert first.unbound_at is None
    cloud.describe_media.return_value = vod_media(second.upload_session_id, "second-file")
    cloud.describe_task.return_value = vod_procedure_event(
        second.upload_session_id, "second-file", "second-task"
    )["ProcedureStateChangeEvent"]
    for event in (
        vod_upload_event(second.upload_session_id, "second-file", "second-task"),
        vod_procedure_event(second.upload_session_id, "second-file", "second-task"),
    ):
        assert (
            await client.post("/api/v1/integrations/tencent-vod/events", json=signed(event))
        ).status_code == 200
    # Successful change increments version; stale changes cannot remove it.
    assert (
        await client.put(
            f"/api/v1/admin/articles/{article_id}",
            headers=headers(),
            json={"version": 1, "videoId": str(second.id)},
        )
    ).status_code == 200
    assert first.unbound_at is not None
    assert (
        await client.put(
            f"/api/v1/admin/articles/{article_id}",
            headers=headers(),
            json={"version": 1, "videoId": None},
        )
    ).status_code == 409
    assert article.video_id == second.id
    assert (
        await client.put(
            f"/api/v1/admin/articles/{article_id}",
            headers=headers(),
            json={"version": 2, "title": "仅改标题"},
        )
    ).status_code == 200
    assert article.video_id == second.id
    assert (
        await client.put(
            f"/api/v1/admin/articles/{article_id}",
            headers=headers(),
            json={"version": 3, "videoId": None},
        )
    ).status_code == 200
    assert article.content == "<p>图文内容</p>"
    assert (await client.get(f"/api/v1/articles/{article_id}")).json()["data"]["video"] is None
    assert second.unbound_at is not None


@pytest.mark.asyncio
async def test_other_admin_cannot_bind_or_read_unbound_upload(client, db_session, vod_settings):
    await seed_admin(db_session)
    video = await upload(client, db_session)
    response = await client.get(f"/api/v1/admin/article-videos/{video.id}", headers=headers(2))
    assert response.status_code == 404
    response = await client.post(
        "/api/v1/admin/articles",
        headers=headers(2),
        json={"title": "他人上传", "videoId": str(video.id)},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_video_change_requires_write_permission_but_text_edit_stays_compatible(
    client, db_session, vod_settings
):
    await seed_admin(db_session)
    video = await upload(client, db_session)
    legacy_headers = auth_header(make_access_token(user_type="admin"))
    created = await client.post(
        "/api/v1/admin/articles",
        headers=headers(),
        json={"title": "草稿视频", "videoId": str(video.id)},
    )
    article_id = int(created.json()["data"]["articleId"])
    assert (
        await client.put(
            f"/api/v1/admin/articles/{article_id}",
            headers=legacy_headers,
            json={"version": 1, "videoId": None},
        )
    ).status_code == 403
    assert (
        await client.put(
            f"/api/v1/admin/articles/{article_id}",
            headers=legacy_headers,
            json={"version": 1, "title": "兼容图文编辑"},
        )
    ).status_code == 200
    assert (
        await client.post(
            "/api/v1/admin/articles",
            headers=legacy_headers,
            json={"title": "禁止新增视频", "videoId": str(video.id)},
        )
    ).status_code == 403
    assert (
        await client.post(f"/api/v1/admin/articles/{article_id}/unpublish", headers=headers())
    ).status_code == 400
    # Deleting an unpublished draft detaches the media for delayed cleanup.
    assert (
        await client.delete(f"/api/v1/admin/articles/{article_id}", headers=headers())
    ).status_code == 200
    assert video.unbound_at is not None


@pytest.mark.asyncio
async def test_callback_rejects_invalid_signature_and_acknowledges_unknown_session(
    client, db_session, vod_settings
):
    cloud = AsyncMock()
    app.dependency_overrides[get_vod_client] = lambda: cloud
    event = vod_upload_event("unknown")
    assert (
        await client.post("/api/v1/integrations/tencent-vod/events", json=event)
    ).status_code == 401
    valid = signed(event)
    assert (
        await client.post("/api/v1/integrations/tencent-vod/events", json=valid)
    ).status_code == 200
    expired = {**valid, "T": int(time.time()) - 1}
    assert (
        await client.post("/api/v1/integrations/tencent-vod/events", json=expired)
    ).status_code == 401
    cloud.describe_media.assert_not_awaited()
    assert (
        await client.get("/api/v1/admin/article-videos/999", headers=headers())
    ).status_code == 404
    assert (
        await client.post("/api/v1/integrations/tencent-vod/events", content="not-json")
    ).status_code == 400
    assert (
        await client.post("/api/v1/integrations/tencent-vod/events", json=[])
    ).status_code == 400


@pytest.mark.asyncio
async def test_orphan_cleanup_retention_references_and_retry(db_session, vod_settings):
    from src.services.article_video_cleanup import cleanup_orphan_videos

    now = datetime.utcnow()

    def media(session, age, **values):
        return ArticleVideo(
            upload_session_id=session,
            uploaded_by_admin_id=1,
            file_name="clip.mp4",
            content_type="video/mp4",
            declared_size_bytes=100,
            vod_sub_app_id=123,
            status=VideoStatus.READY,
            ownership_verified=True,
            file_id=session,
            unbound_at=now - timedelta(days=age),
            **values,
        )

    expired = media("expired", 8)
    recent = media("recent", 6)
    bound = media("bound", 8)
    db_session.add_all([expired, recent, bound])
    await db_session.flush()
    db_session.add(Article(title="被引用的视频", content="", video_id=bound.id))
    await db_session.commit()
    cloud = AsyncMock()
    cloud.delete_media.side_effect = RuntimeError("sensitive cloud exception")
    assert await cleanup_orphan_videos(TestAsyncSession, cloud, now=now) == 0
    await db_session.refresh(expired)
    assert expired.status == VideoStatus.DELETING
    cloud.delete_media.assert_awaited_once_with("expired", 123)
    cloud.delete_media.reset_mock(side_effect=True)
    assert (
        await cleanup_orphan_videos(TestAsyncSession, cloud, now=now + timedelta(minutes=20)) == 1
    )
    await db_session.refresh(expired)
    assert expired.status == VideoStatus.DELETED
    await db_session.refresh(recent)
    await db_session.refresh(bound)
    assert recent.status == VideoStatus.READY
    assert bound.status == VideoStatus.READY
