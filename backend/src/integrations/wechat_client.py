"""Async WeChat Mini-Program API client."""

import logging
from typing import Optional

import httpx

from ..core.config import get_settings

logger = logging.getLogger(__name__)


class WechatClient:
    """Async client for WeChat Mini-Program backend API.

    Wraps code2session and getphonenumber endpoints with error handling.
    """

    BASE_URL = "https://api.weixin.qq.com"

    def __init__(self) -> None:
        settings = get_settings()
        self._app_id = settings.wechat_app_id
        self._app_secret = settings.wechat_app_secret
        self._http: Optional[httpx.AsyncClient] = None

    @property
    def http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=httpx.Timeout(10.0))
        return self._http

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    # ------------------------------------------------------------------
    # jscode2session
    # ------------------------------------------------------------------
    async def jscode2session(self, code: str) -> dict:
        """Exchange a wx.login() code for openid, session_key, and optional unionid.

        Returns:
            dict with keys: openid, session_key, unionid (optional)

        Raises:
            Exception: if WeChat returns an error code or the request fails.
        """
        url = f"{self.BASE_URL}/sns/jscode2session"
        params = {
            "appid": self._app_id,
            "secret": self._app_secret,
            "js_code": code,
            "grant_type": "authorization_code",
        }

        try:
            resp = await self.http.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            logger.error("WeChat jscode2session HTTP error: %s", exc)
            raise Exception("WeChat service error, please retry") from exc

        if "errcode" in data and data["errcode"] != 0:
            errcode = data.get("errcode")
            errmsg = data.get("errmsg", "unknown error")
            logger.warning("WeChat jscode2session error [%s]: %s", errcode, errmsg)

            if errcode == 40029:
                raise Exception("invalid code")
            if errcode == 45011:
                raise Exception("invalid code")
            if errcode == 40163:
                raise Exception("invalid code")
            raise Exception("WeChat service error, please retry")

        if "openid" not in data:
            raise Exception("WeChat service error, please retry")

        return data

    # ------------------------------------------------------------------
    # get_phone_number
    # ------------------------------------------------------------------
    async def get_phone_number(self, code: str) -> str:
        """Exchange a WeChat phone-number auth code for the user's phone number.

        The ``code`` is obtained from the mini-program's
        ``<button open-type="getPhoneNumber">`` callback.

        Returns:
            The verified pure phone number. Callers must mask it for API output.

        Raises:
            Exception: if the code is invalid or the WeChat API fails.
        """
        # First get an access_token for the mini-program
        access_token = await self._get_access_token()

        url = f"{self.BASE_URL}/wxa/business/getuserphonenumber"
        params = {"access_token": access_token}
        payload = {"code": code}

        try:
            resp = await self.http.post(url, params=params, json=payload)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            logger.error("WeChat getuserphonenumber HTTP error: %s", exc)
            raise Exception("WeChat service error, please retry") from exc

        if data.get("errcode") != 0:
            errcode = data.get("errcode")
            errmsg = data.get("errmsg", "unknown error")
            logger.warning("WeChat getuserphonenumber error [%s]: %s", errcode, errmsg)
            raise Exception("invalid phone code")

        phone_info = data.get("phone_info", {})
        phone = phone_info.get("purePhoneNumber", "")
        if not phone:
            raise Exception("invalid phone code")

        return phone

    async def get_unlimited_wxacode(self, scene: str, page: str) -> bytes:
        """Generate a real unlimited mini-program code for the given scene."""
        if not scene or len(scene) > 32:
            raise ValueError("小程序码参数长度必须为1到32个字符")
        access_token = await self._get_access_token()
        url = f"{self.BASE_URL}/wxa/getwxacodeunlimit"
        params = {"access_token": access_token}
        payload = {
            "scene": scene,
            "page": page.lstrip("/"),
            "check_path": False,
            "env_version": "release",
            "width": 430,
        }
        try:
            response = await self.http.post(url, params=params, json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("WeChat getwxacodeunlimit HTTP error: %s", exc)
            raise Exception("微信小程序码生成失败，请稍后重试") from exc

        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            data = response.json()
            logger.warning(
                "WeChat getwxacodeunlimit error [%s]: %s",
                data.get("errcode"),
                data.get("errmsg"),
            )
            raise Exception("微信小程序码生成失败，请检查发布页面配置")
        return response.content

    # ------------------------------------------------------------------
    # Internal: get access_token
    # ------------------------------------------------------------------
    async def _get_access_token(self) -> str:
        """Obtain a mini-program access_token (cached is preferred in production)."""
        url = f"{self.BASE_URL}/cgi-bin/token"
        params = {
            "grant_type": "client_credential",
            "appid": self._app_id,
            "secret": self._app_secret,
        }

        try:
            resp = await self.http.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            logger.error("WeChat access_token HTTP error: %s", exc)
            raise Exception("WeChat service error, please retry") from exc

        access_token = data.get("access_token", "")
        if not access_token:
            raise Exception("WeChat service error, please retry")

        return access_token


# ------------------------------------------------------------------
# Module-level convenience: get default instance
# ------------------------------------------------------------------
_default_client: Optional[WechatClient] = None


def get_wechat_client() -> WechatClient:
    global _default_client
    if _default_client is None:
        _default_client = WechatClient()
    return _default_client
