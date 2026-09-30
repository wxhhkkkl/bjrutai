"""Article VOD upload, binding and public playback contracts."""

from datetime import datetime, timezone

import pytest

from tests.conftest import auth_header, make_access_token, seed_admin, seed_article


@pytest.mark.asyncio
async def test_upload_requires_permission_and_rejects_invalid_media(client):
    url = "/api/v1/admin/article-videos/uploads"
    data = {"fileName": "clip.mp4", "contentType": "video/mp4", "sizeBytes": 1024}
    denied = await client.post(
        url, json=data, headers=auth_header(make_access_token(user_type="admin"))
    )
    assert denied.status_code == 403
    headers = auth_header(make_access_token(user_type="admin", permissions=["articles.write"]))
    for invalid in (
        {**data, "fileName": "../clip.mp4"},
        {**data, "contentType": "video/quicktime"},
        {**data, "sizeBytes": 1_073_741_825},
    ):
        response = await client.post(url, json=invalid, headers=headers)
        assert response.status_code in (400, 422)


@pytest.mark.asyncio
async def test_published_article_exposes_only_ready_video(
    client, db_session, admin_auth_headers, vod_settings
):
    from src.models.article import Article
    from src.models.article_video import ArticleVideo, VideoStatus

    article_id = await seed_article(
        db_session, status="published", published_at=datetime.now(timezone.utc)
    )
    video = ArticleVideo(
        upload_session_id="test-session",
        uploaded_by_admin_id=1,
        file_name="clip.mov",
        content_type="video/quicktime",
        declared_size_bytes=100,
        vod_sub_app_id=1,
        status=VideoStatus.PROCESSING,
    )
    db_session.add(video)
    await db_session.flush()
    article = await db_session.get(Article, article_id)
    article.video_id = video.id
    await db_session.flush()
    response = await client.get(f"/api/v1/articles/{article_id}")
    assert response.status_code == 200
    assert response.json()["data"]["video"] is None
    video.status = VideoStatus.READY
    video.playback_url = "https://vod.example.cn/video.mp4"
    await db_session.flush()
    response = await client.get(f"/api/v1/articles/{article_id}")
    assert response.json()["data"]["video"]["playbackUrl"] == video.playback_url


@pytest.mark.asyncio
async def test_publish_rejects_processing_video(client, db_session, admin_auth_headers):
    from src.models.article import Article
    from src.models.article_video import ArticleVideo, VideoStatus

    article_id = await seed_article(db_session)
    video = ArticleVideo(
        upload_session_id="test-session-2",
        uploaded_by_admin_id=1,
        file_name="clip.mp4",
        content_type="video/mp4",
        declared_size_bytes=100,
        vod_sub_app_id=1,
        status=VideoStatus.PROCESSING,
    )
    db_session.add(video)
    await db_session.flush()
    (await db_session.get(Article, article_id)).video_id = video.id
    await db_session.flush()
    response = await client.post(
        f"/api/v1/admin/articles/{article_id}/publish", headers=admin_auth_headers
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_exact_gigabyte_boundary_and_configuration_error(
    client, db_session, vod_settings, monkeypatch
):
    from src.core.config import get_settings

    await seed_admin(db_session)
    headers = auth_header(make_access_token(user_type="admin", permissions=["articles.write"]))
    data = {"fileName": "clip.MP4", "contentType": "video/mp4", "sizeBytes": 1_073_741_824}
    assert (
        await client.post("/api/v1/admin/article-videos/uploads", json=data, headers=headers)
    ).status_code == 201
    monkeypatch.setattr(get_settings(), "vod_sub_app_id", 0)
    response = await client.post("/api/v1/admin/article-videos/uploads", json=data, headers=headers)
    assert response.status_code == 503
    assert "test-secret" not in response.text
    assert "uploadSignature" not in response.text
