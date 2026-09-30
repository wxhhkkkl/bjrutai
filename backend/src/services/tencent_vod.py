"""Tencent VOD signatures and official asynchronous API client."""

import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timezone
from urllib.parse import urlencode, urlsplit

from ..core.config import Settings, get_settings
from ..core.exceptions import AppException, UnauthorizedException


def unavailable():
    return AppException(
        code=50300,
        message="点播服务暂不可用，请联系管理员或稍后重试",
        status_code=503,
        retryable=True,
    )


def ensure_configured(config: Settings):
    if not all(
        (
            config.vod_secret_id,
            config.vod_secret_key,
            config.vod_sub_app_id > 0,
            config.vod_procedure,
            config.vod_callback_sign_key,
            config.vod_playback_hosts,
        )
    ):
        raise unavailable()


def create_upload_signature(config: Settings, session_id: str, *, now: int | None = None):
    ensure_configured(config)
    current = int(time.time()) if now is None else now
    expires = current + 3600
    original = urlencode(
        {
            "secretId": config.vod_secret_id,
            "currentTimeStamp": current,
            "expireTime": expires,
            "random": secrets.randbits(32),
            "oneTimeValid": 1,
            "vodSubAppId": config.vod_sub_app_id,
            "procedure": config.vod_procedure,
            "sourceContext": session_id,
            "sessionContext": session_id,
            "taskNotifyMode": "Finish",
        }
    ).encode()
    digest = hmac.new(config.vod_secret_key.encode(), original, hashlib.sha1).digest()
    return base64.b64encode(digest + original).decode(), datetime.fromtimestamp(
        expires, timezone.utc
    )


def verify_callback(config: Settings, event: dict, *, now: int | None = None):
    # VOD T is an expiration timestamp. Its documented signature is MD5(SignKey + T).
    try:
        expiry = event["T"]
        if isinstance(expiry, bool) or not isinstance(expiry, int):
            raise ValueError()
        current = int(time.time()) if now is None else now
        if not config.vod_callback_sign_key or expiry < current or expiry > current + 900:
            raise ValueError()
        expected = hashlib.md5(f"{config.vod_callback_sign_key}{expiry}".encode()).hexdigest()
        if not hmac.compare_digest(expected, str(event.get("Sign", "")).lower()):
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise UnauthorizedException(message="点播回调签名无效或已过期") from None


def trusted_https_url(value, config: Settings) -> str | None:
    if not isinstance(value, str) or len(value) > 2048:
        return None
    hosts = {host.strip().lower() for host in config.vod_playback_hosts.split(",") if host.strip()}
    try:
        url = urlsplit(value)
        if (
            url.scheme == "https"
            and url.hostname in hosts
            and url.port in (None, 443)
            and not url.username
            and not url.password
            and not url.fragment
        ):
            return value
    except ValueError:
        pass
    return None


class TencentVod:
    def __init__(self, config: Settings | None = None):
        self.config = config or get_settings()

    async def _request(self, action: str, request_type: str, payload: dict, *, missing_ok=False):
        ensure_configured(self.config)
        from tencentcloud.common.credential import Credential
        from tencentcloud.common.exception.tencent_cloud_sdk_exception import (
            TencentCloudSDKException,
        )
        from tencentcloud.common.profile.client_profile import ClientProfile
        from tencentcloud.common.profile.http_profile import HttpProfile
        from tencentcloud.vod.v20180717 import models
        from tencentcloud.vod.v20180717.vod_client_async import VodClient

        profile = ClientProfile(httpProfile=HttpProfile(reqTimeout=15))
        request = getattr(models, request_type)()
        request.from_json_string(json.dumps(payload))
        try:
            async with VodClient(
                Credential(self.config.vod_secret_id, self.config.vod_secret_key),
                self.config.vod_region,
                profile,
            ) as client:
                response = await getattr(client, action)(request)
                return json.loads(response.to_json_string())
        except TencentCloudSDKException as exc:
            if missing_ok and exc.get_code() == "ResourceNotFound":
                return {}
            raise unavailable() from None
        except Exception:
            # Provider exceptions may contain request credentials or raw media data.
            raise unavailable() from None

    async def describe_media(self, file_id: str, sub_app_id: int):
        response = await self._request(
            "DescribeMediaInfos",
            "DescribeMediaInfosRequest",
            {
                "SubAppId": sub_app_id,
                "FileIds": [file_id],
                "Filters": ["basicInfo", "metaData", "transcodeInfo"],
            },
        )
        return next(
            (item for item in response.get("MediaInfoSet", []) if item.get("FileId") == file_id),
            None,
        )

    async def delete_media(self, file_id: str, sub_app_id: int):
        await self._request(
            "DeleteMedia",
            "DeleteMediaRequest",
            {"FileId": file_id, "SubAppId": sub_app_id},
            missing_ok=True,
        )

    async def describe_task(self, task_id: str, sub_app_id: int):
        response = await self._request(
            "DescribeTaskDetail",
            "DescribeTaskDetailRequest",
            {
                "TaskId": task_id,
                "SubAppId": sub_app_id,
            },
        )
        return response.get("ProcedureTask")


def get_vod_client():
    return TencentVod()
