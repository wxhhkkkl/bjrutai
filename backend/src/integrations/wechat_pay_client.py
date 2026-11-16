"""Bounded WeChat Pay APIv2 adapter. Default closed; no retries or redirects."""

import asyncio
import ipaddress
import re
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import httpx

from .wechat_pay_crypto import build_v2_xml, parse_v2_xml, sign_v2, verify_v2_signature
from .wechat_pay_types import (
    PaymentGatewayError,
    PaymentNotFoundError,
    PrepayResult,
    RefundNotFoundError,
    VerifiedClose,
    parse_api_v2_payment_fact,
    parse_api_v2_refund_fact,
)

_BASE_URL = "https://api.mch.weixin.qq.com"


class WechatPayClient:
    def __init__(
        self,
        *,
        appid,
        mchid,
        api_key,
        spbill_create_ip,
        sign_type="MD5",
        refund_notify_url="",
        refund_client_cert_path="",
        refund_client_key_path="",
        outbound_enabled=False,
        transport=None,
        timeout_seconds=10,
    ):
        for value in (appid, mchid):
            if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,32}", value):
                raise ValueError("payment identity is invalid")
        if not isinstance(api_key, str) or len(api_key.encode("utf-8")) != 32:
            raise ValueError("APIv2 key must contain 32 bytes")
        if sign_type not in {"MD5", "HMAC-SHA256"}:
            raise ValueError("unsupported APIv2 signature type")
        try:
            self._spbill_create_ip = str(ipaddress.ip_address(spbill_create_ip))
        except (TypeError, ValueError):
            raise ValueError("payment client IP is invalid") from None
        self.appid, self.mchid = appid, mchid
        self._api_key, self._sign_type = api_key, sign_type
        self._refund_notify_url = refund_notify_url
        self._refund_cert = (refund_client_cert_path, refund_client_key_path)
        self._outbound, self._transport = outbound_enabled, transport
        if not 0 < timeout_seconds <= 20:
            raise ValueError("payment deadline is invalid")
        self._timeout = timeout_seconds

    @staticmethod
    def _order_no(value):
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", value):
            raise ValueError("payment order identity is invalid")
        return value

    @staticmethod
    def _refund_no(value):
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
            raise ValueError("refund identity is invalid")
        return value

    @staticmethod
    def _callback_url(value, *, optional=False):
        if not isinstance(value, str) or (optional and not value):
            if optional and value == "":
                return
            raise ValueError("callback URL is invalid")
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("callback URL must be a public HTTPS URL without query parameters")

    def _signed_xml(self, params):
        payload = {
            **params,
            "appid": self.appid,
            "mch_id": self.mchid,
            "nonce_str": secrets.token_hex(16),
            "sign_type": self._sign_type,
        }
        payload["sign"] = sign_v2(payload, self._api_key, self._sign_type)
        return payload, build_v2_xml(payload)

    async def _request(
        self,
        path,
        params,
        *,
        client_certificate=False,
        allow_absent_code=None,
        tolerate_error_codes=(),
    ):
        if not self._outbound:
            raise PaymentGatewayError("payment_outbound_disabled")
        cert = None
        if client_certificate:
            cert_path, key_path = self._refund_cert
            if not cert_path or not key_path or not Path(cert_path).is_file() or not Path(key_path).is_file():
                raise PaymentGatewayError("refund_client_certificate_unavailable")
            cert = (cert_path, key_path)
        _, request_body = self._signed_xml(params)
        try:
            async with asyncio.timeout(self._timeout):
                client_options = {
                    "timeout": self._timeout,
                    "transport": self._transport,
                    "trust_env": False,
                    "follow_redirects": False,
                }
                if cert:
                    client_options["cert"] = cert
                async with httpx.AsyncClient(**client_options) as remote:
                    async with remote.stream(
                        "POST",
                        _BASE_URL + path,
                        content=request_body,
                        headers={
                            "Accept": "application/xml, text/xml",
                            "Content-Type": "text/xml; charset=utf-8",
                        },
                    ) as response:
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            body.extend(chunk)
                            if len(body) > 1_100_000:
                                raise PaymentGatewayError("response_too_large")
                        if response.status_code != 200:
                            raise PaymentGatewayError("gateway_result_requires_query")
                        data = parse_v2_xml(bytes(body))
            if data.get("return_code") != "SUCCESS":
                # APIv2 communication failures are not financial facts.
                raise PaymentGatewayError("gateway_result_requires_query")
            if not verify_v2_signature(
                data, self._api_key, fallback_sign_type=self._sign_type
            ):
                raise PaymentGatewayError("response_verification_failed")
            if data.get("appid") != self.appid or data.get("mch_id") != self.mchid:
                raise PaymentGatewayError("transaction_identity_mismatch")
            if data.get("result_code") != "SUCCESS":
                error_code = data.get("err_code")
                if allow_absent_code and error_code == allow_absent_code:
                    if allow_absent_code == "ORDERNOTEXIST":
                        raise PaymentNotFoundError()
                    raise RefundNotFoundError()
                if error_code in tolerate_error_codes:
                    return data
                raise PaymentGatewayError("gateway_result_requires_query")
            return data
        except (PaymentNotFoundError, RefundNotFoundError, PaymentGatewayError):
            raise
        except TimeoutError:
            raise PaymentGatewayError("transport_result_unknown") from None
        except (httpx.HTTPError, OSError):
            raise PaymentGatewayError("transport_result_unknown") from None

    async def prepay(self, *, out_trade_no, amount_cent, openid, expires_at, notify_url):
        self._order_no(out_trade_no)
        self._callback_url(notify_url)
        if (
            type(amount_cent) is not int
            or not 0 < amount_cent <= 9007199254740991
            or not isinstance(openid, str)
            or not 0 < len(openid) <= 128
        ):
            raise ValueError("invalid payment request")
        expiry = (
            expires_at.replace(tzinfo=timezone.utc)
            if expires_at.tzinfo is None
            else expires_at.astimezone(timezone.utc)
        )
        if expiry <= datetime.now(timezone.utc):
            raise ValueError("payment request expired")
        data = await self._request(
            "/pay/unifiedorder",
            {
                "body": "商城订单",
                "out_trade_no": out_trade_no,
                "total_fee": amount_cent,
                "fee_type": "CNY",
                "spbill_create_ip": self._spbill_create_ip,
                "time_expire": expiry.astimezone(ZoneInfo("Asia/Shanghai")).strftime(
                    "%Y%m%d%H%M%S"
                ),
                "notify_url": notify_url,
                "trade_type": "JSAPI",
                "openid": openid,
            },
        )
        if data.get("trade_type") != "JSAPI":
            raise PaymentGatewayError("invalid_prepay_response")
        prepay_id = data.get("prepay_id")
        if not isinstance(prepay_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", prepay_id):
            raise PaymentGatewayError("invalid_prepay_response")
        return PrepayResult(prepay_id)

    async def query(self, out_trade_no):
        out_trade_no = self._order_no(out_trade_no)
        data = await self._request(
            "/pay/orderquery",
            {"out_trade_no": out_trade_no},
            allow_absent_code="ORDERNOTEXIST",
        )
        fact = parse_api_v2_payment_fact(data)
        if (fact.appid, fact.mchid, fact.out_trade_no) != (
            self.appid,
            self.mchid,
            out_trade_no,
        ):
            raise PaymentGatewayError("transaction_identity_mismatch")
        return fact

    async def close(self, out_trade_no):
        out_trade_no = self._order_no(out_trade_no)
        data = await self._request(
            "/pay/closeorder",
            {"out_trade_no": out_trade_no},
            tolerate_error_codes={"ORDERCLOSED"},
        )
        if data.get("out_trade_no") not in {None, "", out_trade_no}:
            raise PaymentGatewayError("transaction_identity_mismatch")
        return VerifiedClose(out_trade_no, self.mchid)

    async def create_refund(self, *, out_trade_no, out_refund_no, total_cent, refund_cent):
        out_trade_no = self._order_no(out_trade_no)
        out_refund_no = self._refund_no(out_refund_no)
        if (
            type(total_cent) is not int
            or type(refund_cent) is not int
            or not 0 < refund_cent <= total_cent <= 9007199254740991
        ):
            raise ValueError("refund amounts are invalid")
        self._callback_url(self._refund_notify_url, optional=True)
        accepted = await self._request(
            "/secapi/pay/refund",
            {
                "out_trade_no": out_trade_no,
                "out_refund_no": out_refund_no,
                "total_fee": total_cent,
                "refund_fee": refund_cent,
                "refund_fee_type": "CNY",
                "notify_url": self._refund_notify_url,
            },
            client_certificate=True,
        )
        if (
            accepted.get("out_refund_no") != out_refund_no
            or accepted.get("out_trade_no") != out_trade_no
            or accepted.get("refund_fee") != str(refund_cent)
            or accepted.get("total_fee") != str(total_cent)
        ):
            raise PaymentGatewayError("refund_identity_mismatch")
        # Acceptance only means the provider received the request. The separate,
        # signed refund query supplies the status fact consumed by the state machine.
        return await self.query_refund(out_refund_no)

    async def query_refund(self, out_refund_no):
        out_refund_no = self._refund_no(out_refund_no)
        data = await self._request(
            "/pay/refundquery",
            {"out_refund_no": out_refund_no},
            allow_absent_code="REFUNDNOTEXIST",
        )
        fact = parse_api_v2_refund_fact(data, out_refund_no)
        if fact.out_refund_no != out_refund_no:
            raise PaymentGatewayError("refund_identity_mismatch")
        return fact

    def invocation(self, prepay_id):
        if not isinstance(prepay_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", prepay_id):
            raise ValueError("invalid prepay identity")
        timestamp = str(int(time.time()))
        nonce = secrets.token_hex(16)
        package = "prepay_id=" + prepay_id
        params = {
            "appId": self.appid,
            "nonceStr": nonce,
            "package": package,
            "signType": self._sign_type,
            "timeStamp": timestamp,
        }
        return {
            "timeStamp": timestamp,
            "nonceStr": nonce,
            "package": package,
            "signType": self._sign_type,
            "paySign": sign_v2(params, self._api_key, self._sign_type),
        }
