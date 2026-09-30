import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock
from urllib.parse import parse_qs

import pytest

from src.core.config import Settings
from src.core.exceptions import AppException, UnauthorizedException
from tests.conftest import vod_media, vod_procedure_event, vod_upload_event


def configured():
    return Settings(
        vod_secret_id="test-id",
        vod_secret_key="test-secret",
        vod_sub_app_id=123,
        vod_procedure="ArticleMp4",
        vod_callback_sign_key="test-callback",
        vod_playback_hosts="vod.example.cn",
    )


def test_upload_signature_is_scoped_and_short_lived():
    from src.services.tencent_vod import create_upload_signature

    value, expires = create_upload_signature(configured(), "session-123", now=1000)
    raw = base64.b64decode(value)
    assert hmac.compare_digest(raw[:20], hmac.new(b"test-secret", raw[20:], hashlib.sha1).digest())
    params = parse_qs(raw[20:].decode())
    assert params["sourceContext"] == ["session-123"]
    assert params["sessionContext"] == ["session-123"]
    assert params["vodSubAppId"] == ["123"]
    assert params["oneTimeValid"] == ["1"]
    assert int(params["expireTime"][0]) == 4600
    assert "test-secret" not in raw[20:].decode()


def test_missing_vod_configuration_fails_without_leaking_secrets():
    from src.services.tencent_vod import create_upload_signature

    with pytest.raises(AppException) as error:
        create_upload_signature(
            Settings(
                vod_secret_id="",
                vod_secret_key="sensitive-example",
                vod_sub_app_id=0,
                vod_procedure="",
                vod_callback_sign_key="",
                vod_playback_hosts="",
            ),
            "session",
        )
    assert error.value.status_code == 503
    assert "sensitive-example" not in str(error.value)


def test_callback_uses_expiry_not_creation_timestamp():
    from src.services.tencent_vod import verify_callback

    config = configured()
    timestamp = 1600
    event = {"T": timestamp, "Sign": hashlib.md5(f"test-callback{timestamp}".encode()).hexdigest()}
    verify_callback(config, event, now=1000)
    with pytest.raises(UnauthorizedException):
        verify_callback(config, event, now=1601)


@pytest.mark.asyncio
async def test_processing_event_before_upload_is_idempotent(db_session):
    from src.models.article_video import ArticleVideo, VideoStatus
    from src.services.article_video_service import handle_event

    video = ArticleVideo(
        upload_session_id="session",
        uploaded_by_admin_id=1,
        file_name="clip.mov",
        content_type="video/quicktime",
        declared_size_bytes=100,
        vod_sub_app_id=123,
    )
    db_session.add(video)
    await db_session.flush()
    metadata = {
        "FileId": "cloud-file",
        "BasicInfo": {"SourceInfo": {"SourceContext": "session"}},
        "MetaData": {"Size": 100, "Duration": 12},
        "TranscodeInfo": {
            "TranscodeSet": [
                {
                    "Definition": 10,
                    "Url": "https://vod.example.cn/clip.mp4",
                    "VideoStreamSet": [{"Codec": "h264"}],
                    "AudioStreamSet": [{"Codec": "aac"}],
                }
            ]
        },
    }
    cloud = AsyncMock()
    cloud.describe_media.return_value = metadata
    procedure = {
        "EventType": "ProcedureStateChanged",
        "ProcedureStateChangeEvent": {
            "SessionContext": "session",
            "FileId": "cloud-file",
            "TaskId": "task",
            "Status": "FINISH",
            "MediaProcessResultSet": [
                {"Type": "Transcode", "TranscodeTask": {"Status": "SUCCESS", "ErrCode": 0}}
            ],
        },
    }
    cloud.describe_task.return_value = procedure["ProcedureStateChangeEvent"]
    await handle_event(db_session, procedure, config=configured(), cloud=cloud)
    assert video.status == VideoStatus.PROCESSING
    upload = {
        "EventType": "NewFileUpload",
        "FileUploadEvent": {
            "MediaBasicInfo": {"SourceInfo": {"SourceContext": "session"}},
            "FileId": "cloud-file",
            "ProcedureTaskId": "task",
        },
    }
    await handle_event(db_session, upload, config=configured(), cloud=cloud)
    assert video.status == VideoStatus.READY
    await handle_event(db_session, procedure, config=configured(), cloud=cloud)
    await handle_event(db_session, upload, config=configured(), cloud=cloud)
    assert video.status == VideoStatus.READY
    assert video.actual_size_bytes == 100


@pytest.mark.asyncio
async def test_abandoned_upload_and_claimed_video_cannot_be_bound(db_session, vod_settings):
    from src.core.exceptions import ConflictException
    from src.models.article import Article
    from src.models.article_video import ArticleVideo, VideoStatus
    from src.services.article_video_service import bind_video, reconcile_video

    video = ArticleVideo(
        upload_session_id="abandoned",
        uploaded_by_admin_id=1,
        file_name="clip.mp4",
        content_type="video/mp4",
        declared_size_bytes=100,
        vod_sub_app_id=123,
        created_at=datetime.utcnow() - timedelta(days=2),
    )
    db_session.add(video)
    await db_session.flush()
    await reconcile_video(db_session, video)
    assert video.status == VideoStatus.FAILED
    article = Article(title="目标文章", content="")
    db_session.add(article)
    await db_session.flush()
    with pytest.raises(ConflictException):
        await bind_video(db_session, article, video.id, 1)
    video.status = VideoStatus.READY
    video.unbound_at = None
    with pytest.raises(ConflictException):
        await bind_video(db_session, article, video.id, 1)


@pytest.mark.asyncio
async def test_sdk_query_success_uses_expected_application(monkeypatch):
    from tencentcloud.vod.v20180717 import models
    from tencentcloud.vod.v20180717.vod_client_async import VodClient

    from src.services.tencent_vod import TencentVod

    media_response = models.DescribeMediaInfosResponse()
    media_response.from_json_string(json.dumps({"MediaInfoSet": [vod_media("session")]}))
    mock_media = AsyncMock(return_value=media_response)
    monkeypatch.setattr(VodClient, "DescribeMediaInfos", mock_media)
    cloud = TencentVod(configured())
    media = await cloud.describe_media("cloud-file", 123)
    assert media["FileId"] == "cloud-file"
    request = mock_media.call_args.args[0]
    assert request.SubAppId == 123
    assert request.FileIds == ["cloud-file"]
    task_response = models.DescribeTaskDetailResponse()
    task_response.from_json_string(
        json.dumps({"ProcedureTask": vod_procedure_event("session")["ProcedureStateChangeEvent"]})
    )
    monkeypatch.setattr(VodClient, "DescribeTaskDetail", AsyncMock(return_value=task_response))
    assert (await cloud.describe_task("cloud-task", 123))["TaskId"] == "cloud-task"


@pytest.mark.parametrize("enabled,failure", [(False, False), (True, False), (True, True)])
@pytest.mark.asyncio
async def test_cleanup_job_is_opt_in_and_sanitizes_failures(
    monkeypatch, vod_settings, caplog, enabled, failure
):
    import src.services.article_video_cleanup as cleanup
    from src.core.config import get_settings

    monkeypatch.setattr(get_settings(), "vod_cleanup_enabled", enabled)
    run = AsyncMock(
        return_value=1, side_effect=RuntimeError("secret-provider-message") if failure else None
    )
    monkeypatch.setattr(cleanup, "cleanup_orphan_videos", run)
    await cleanup.article_video_cleanup_job()
    assert run.await_count == (1 if enabled else 0)
    assert "secret-provider-message" not in caplog.text


@pytest.mark.asyncio
async def test_wrong_cloud_context_never_becomes_ready(db_session):
    from src.models.article_video import ArticleVideo, VideoStatus
    from src.services.article_video_service import handle_event

    video = ArticleVideo(
        upload_session_id="session",
        uploaded_by_admin_id=1,
        file_name="clip.mp4",
        content_type="video/mp4",
        declared_size_bytes=100,
        vod_sub_app_id=123,
    )
    db_session.add(video)
    await db_session.flush()
    cloud = AsyncMock()
    cloud.describe_media.return_value = {
        "FileId": "other-file",
        "BasicInfo": {"SourceInfo": {"SourceContext": "other"}},
    }
    await handle_event(
        db_session,
        {
            "EventType": "NewFileUpload",
            "FileUploadEvent": {
                "MediaBasicInfo": {"SourceInfo": {"SourceContext": "session"}},
                "FileId": "other-file",
            },
        },
        config=configured(),
        cloud=cloud,
    )
    assert video.status == VideoStatus.FAILED
    assert video.playback_url is None


@pytest.mark.parametrize(
    "field,empty",
    [
        ("vod_secret_id", ""),
        ("vod_secret_key", ""),
        ("vod_sub_app_id", 0),
        ("vod_procedure", ""),
        ("vod_callback_sign_key", ""),
        ("vod_playback_hosts", ""),
    ],
)
def test_each_required_vod_setting_is_checked(field, empty):
    from src.services.tencent_vod import create_upload_signature

    config = configured().model_copy(update={field: empty})
    with pytest.raises(AppException) as error:
        create_upload_signature(config, "session")
    assert error.value.status_code == 503


@pytest.mark.parametrize(
    "url",
    [
        "http://vod.example.cn/a.mp4",
        "https://evil.example.cn/a.mp4",
        "https://vod.example.cn@evil.example.cn/a.mp4",
        "https://vod.example.cn:8080/a.mp4",
    ],
)
def test_untrusted_media_urls_are_rejected(url):
    from src.services.tencent_vod import trusted_https_url

    assert trusted_https_url(url, configured()) is None


@pytest.mark.parametrize("failure", ["oversize", "no_mp4", "wrong_codec", "task_failed"])
@pytest.mark.asyncio
async def test_media_validation_failures_cannot_become_ready(db_session, failure):
    from src.models.article_video import ArticleVideo, VideoStatus
    from src.services.article_video_service import handle_event

    video = ArticleVideo(
        upload_session_id="session",
        uploaded_by_admin_id=1,
        file_name="clip.mp4",
        content_type="video/mp4",
        declared_size_bytes=100,
        vod_sub_app_id=123,
    )
    db_session.add(video)
    await db_session.flush()
    cloud = AsyncMock()
    metadata = vod_media("session")
    if failure == "oversize":
        metadata["MetaData"]["Size"] = 1_073_741_825
    if failure == "no_mp4":
        metadata["TranscodeInfo"]["TranscodeSet"][0]["Url"] = "https://vod.example.cn/a.mov"
    if failure == "wrong_codec":
        metadata["TranscodeInfo"]["TranscodeSet"][0]["VideoStreamSet"][0]["Codec"] = "h265"
    cloud.describe_media.return_value = metadata
    await handle_event(db_session, vod_upload_event("session"), config=configured(), cloud=cloud)
    event = vod_procedure_event("session")
    if failure == "task_failed":
        event["ProcedureStateChangeEvent"]["MediaProcessResultSet"][0]["TranscodeTask"][
            "Status"
        ] = "FAIL"
    cloud.describe_task.return_value = event["ProcedureStateChangeEvent"]
    await handle_event(db_session, event, config=configured(), cloud=cloud)
    assert video.status == VideoStatus.FAILED
    assert video.playback_url is None


@pytest.mark.asyncio
async def test_upload_waits_when_metadata_is_not_yet_available(db_session):
    from src.models.article_video import ArticleVideo, VideoStatus
    from src.services.article_video_service import handle_event

    video = ArticleVideo(
        upload_session_id="session",
        uploaded_by_admin_id=1,
        file_name="clip.mp4",
        content_type="video/mp4",
        declared_size_bytes=100,
        vod_sub_app_id=123,
    )
    db_session.add(video)
    await db_session.flush()
    metadata = vod_media("session")
    metadata["MetaData"] = None
    cloud = AsyncMock()
    cloud.describe_media.return_value = metadata
    await handle_event(db_session, vod_upload_event("session"), config=configured(), cloud=cloud)
    assert video.status == VideoStatus.PROCESSING


@pytest.mark.asyncio
async def test_sdk_errors_are_sanitized_and_delete_missing_file_is_idempotent(monkeypatch):
    from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
    from tencentcloud.vod.v20180717.vod_client_async import VodClient

    from src.services.tencent_vod import TencentVod

    cloud = TencentVod(configured())
    monkeypatch.setattr(
        VodClient, "DescribeMediaInfos", AsyncMock(side_effect=RuntimeError("secret-cloud-request"))
    )
    with pytest.raises(AppException) as error:
        await cloud.describe_media("file-id", 123)
    assert error.value.status_code == 503
    assert "secret-cloud-request" not in str(error.value)
    monkeypatch.setattr(
        VodClient,
        "DeleteMedia",
        AsyncMock(side_effect=TencentCloudSDKException("ResourceNotFound", "already deleted")),
    )
    await cloud.delete_media("file-id", 123)


@pytest.mark.asyncio
async def test_event_body_cannot_claim_cloud_task_finished(db_session):
    from src.models.article_video import ArticleVideo, VideoStatus
    from src.services.article_video_service import handle_event

    video = ArticleVideo(
        upload_session_id="session",
        uploaded_by_admin_id=1,
        file_name="clip.mp4",
        content_type="video/mp4",
        declared_size_bytes=100,
        vod_sub_app_id=123,
    )
    db_session.add(video)
    await db_session.flush()
    cloud = AsyncMock()
    cloud.describe_media.return_value = vod_media("session")
    cloud.describe_task.return_value = {
        **vod_procedure_event("session")["ProcedureStateChangeEvent"],
        "Status": "PROCESSING",
    }
    await handle_event(db_session, vod_upload_event("session"), config=configured(), cloud=cloud)
    await handle_event(db_session, vod_procedure_event("session"), config=configured(), cloud=cloud)
    assert video.status == VideoStatus.PROCESSING
    assert video.processing_confirmed_at is None


@pytest.mark.asyncio
async def test_status_reconciliation_recovers_missing_procedure_callback(db_session):
    from src.models.article_video import ArticleVideo, VideoStatus
    from src.services.article_video_service import handle_event, reconcile_video

    video = ArticleVideo(
        upload_session_id="session",
        uploaded_by_admin_id=1,
        file_name="clip.mp4",
        content_type="video/mp4",
        declared_size_bytes=100,
        vod_sub_app_id=123,
    )
    db_session.add(video)
    await db_session.flush()
    cloud = AsyncMock()
    cloud.describe_media.return_value = vod_media("session")
    cloud.describe_task.return_value = vod_procedure_event("session")["ProcedureStateChangeEvent"]
    await handle_event(db_session, vod_upload_event("session"), config=configured(), cloud=cloud)
    assert video.status == VideoStatus.PROCESSING
    await reconcile_video(db_session, video, config=configured(), cloud=cloud)
    assert video.status == VideoStatus.READY
