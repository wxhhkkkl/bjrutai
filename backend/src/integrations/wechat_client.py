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
            Masked phone string, e.g. ``138****1234``.

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

        # Mask the phone number for storage: 138****1234
        masked = phone[:3] + "****" + phone[-4:] if len(phone) >= 7 else phone
        return masked

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
