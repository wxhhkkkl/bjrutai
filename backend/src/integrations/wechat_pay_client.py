"""Bounded APIv3 adapter. Default closed; no retry or HTTP callback endpoint."""

import asyncio
import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

import httpx

from .wechat_pay_crypto import WechatPayVerifier, load_merchant_key, sign
from .wechat_pay_types import (
    PaymentGatewayError,
    PaymentNotFoundError,
    PrepayResult,
    RefundNotFoundError,
    VerifiedClose,
    parse_payment_fact,
    parse_refund_fact,
)


class WechatPayClient:
    def __init__(
        self,
        *,
        appid,
        mchid,
        merchant_serial,
        private_key_pem,
        verify_keys,
        outbound_enabled=False,
        transport=None,
        timeout_seconds=10,
    ):
        for value in (appid, mchid, merchant_serial):
            if not re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", value):
                raise ValueError("payment identity is invalid")
        self.appid, self.mchid, self.serial = appid, mchid, merchant_serial
        self._key = load_merchant_key(private_key_pem)
        self._verifier = WechatPayVerifier(verify_keys)
        self._outbound, self._transport = outbound_enabled, transport
        if not 0 < timeout_seconds <= 20:
            raise ValueError("payment deadline is invalid")
        self._timeout = timeout_seconds

    @staticmethod
    def _order_no(value):
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", value):
            raise ValueError("payment order identity is invalid")
        return value

    async def _request(
        self, method, path, body=None, *, expected=200, allow_absent=False, absent_code=None
    ):
        try:
            async with asyncio.timeout(self._timeout):
                return await self._bounded_request(
                    method,
                    path,
                    body,
                    expected=expected,
                    allow_absent=allow_absent,
                    absent_code=absent_code or "ORDER_NOT_EXIST",
                )
        except TimeoutError:
            raise PaymentGatewayError("transport_result_unknown") from None

    async def _bounded_request(
        self, method, path, body=None, *, expected=200, allow_absent=False, absent_code=None
    ):
        if not self._outbound:
            raise PaymentGatewayError("payment_outbound_disabled")
        raw = (
            json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
            if body is not None
            else b""
        )
        timestamp, nonce = str(int(time.time())), uuid4().hex
        message = f"{method}\n{path}\n{timestamp}\n{nonce}\n".encode() + raw + b"\n"
        auth = (
            f'WECHATPAY2-SHA256-RSA2048 mchid="{self.mchid}",nonce_str="{nonce}",'
            f'timestamp="{timestamp}",serial_no="{self.serial}",'
            f'signature="{sign(self._key, message)}"'
        )
        try:
            async with httpx.AsyncClient(
                timeout=10, transport=self._transport, trust_env=False, follow_redirects=False
            ) as remote:
                async with remote.stream(
                    method,
                    "https://api.mch.weixin.qq.com" + path,
                    content=raw,
                    headers={
                        "Authorization": auth,
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                    },
                ) as reply:
                    payload = bytearray()
                    async for chunk in reply.aiter_bytes():
                        payload.extend(chunk)
                        if len(payload) > 1048576:
                            raise PaymentGatewayError("response_too_large")
                    content = bytes(payload)
                    self._verifier.verify(reply.headers, content)
                    if reply.status_code != expected:
                        if allow_absent and reply.status_code == 404:
                            error = json.loads(content)
                            if isinstance(error, dict) and error.get("code") == absent_code:
                                if absent_code == "ORDER_NOT_EXIST":
                                    raise PaymentNotFoundError()
                                if absent_code == "RESOURCE_NOT_EXISTS":
                                    raise RefundNotFoundError()
                        # No signed error, timeout or ambiguous transport result is a close fact.
                        raise PaymentGatewayError("gateway_result_requires_query")
                    if expected == 204:
                        if content:
                            raise PaymentGatewayError("invalid_close_response")
                        return None
                    parsed = json.loads(content)
                    if not isinstance(parsed, dict):
                        raise ValueError()
                    return parsed
        except httpx.HTTPError:
            raise PaymentGatewayError("transport_result_unknown") from None
        except (ValueError, UnicodeError):
            raise PaymentGatewayError("invalid_gateway_json") from None

    async def prepay(self, *, out_trade_no, amount_cent, openid, expires_at, notify_url):
        self._order_no(out_trade_no)
        parsed = urlsplit(notify_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.fragment
            or type(amount_cent) is not int
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
            "POST",
            "/v3/pay/transactions/jsapi",
            {
                "appid": self.appid,
                "mchid": self.mchid,
                "description": "商城订单",
                "out_trade_no": out_trade_no,
                "time_expire": expiry.isoformat(timespec="seconds"),
                "notify_url": notify_url,
                "amount": {"total": amount_cent, "currency": "CNY"},
                "payer": {"openid": openid},
            },
        )
        prepay_id = data.get("prepay_id")
        if not isinstance(prepay_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", prepay_id):
            raise PaymentGatewayError("invalid_prepay_response")
        return PrepayResult(prepay_id)

    async def query(self, out_trade_no):
        path = f"/v3/pay/transactions/out-trade-no/{self._order_no(out_trade_no)}"
        path += "?" + urlencode({"mchid": self.mchid})
        fact = parse_payment_fact(await self._request("GET", path, allow_absent=True))
        if (fact.appid, fact.mchid, fact.out_trade_no) != (self.appid, self.mchid, out_trade_no):
            raise PaymentGatewayError("transaction_identity_mismatch")
        return fact

    async def close(self, out_trade_no):
        await self._request(
            "POST",
            f"/v3/pay/transactions/out-trade-no/{self._order_no(out_trade_no)}/close",
            {"mchid": self.mchid},
            expected=204,
        )
        return VerifiedClose(out_trade_no, self.mchid)

    @staticmethod
    def _refund_no(value):
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
            raise ValueError("refund identity is invalid")
        return value

    async def create_refund(self, *, out_trade_no, out_refund_no, total_cent, refund_cent):
        self._order_no(out_trade_no)
        self._refund_no(out_refund_no)
        if (
            type(total_cent) is not int
            or type(refund_cent) is not int
            or not 0 < refund_cent <= total_cent <= 9007199254740991
        ):
            raise ValueError("refund amounts are invalid")
        payload = {
            "out_trade_no": out_trade_no,
            "out_refund_no": out_refund_no,
            "amount": {"refund": refund_cent, "total": total_cent, "currency": "CNY"},
        }
        fact = parse_refund_fact(
            await self._request("POST", "/v3/refund/domestic/refunds", payload)
        )
        if fact.out_refund_no != out_refund_no or fact.out_trade_no != out_trade_no:
            raise PaymentGatewayError("refund_identity_mismatch")
        if fact.total_cent != total_cent or fact.refund_cent != refund_cent:
            raise PaymentGatewayError("refund_amount_mismatch")
        return fact

    async def query_refund(self, out_refund_no):
        out_refund_no = self._refund_no(out_refund_no)
        fact = parse_refund_fact(
            await self._request(
                "GET",
                f"/v3/refund/domestic/refunds/{out_refund_no}",
                allow_absent=True,
                absent_code="RESOURCE_NOT_EXISTS",
            )
        )
        if fact.out_refund_no != out_refund_no:
            raise PaymentGatewayError("refund_identity_mismatch")
        return fact

    def invocation(self, prepay_id):
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", prepay_id):
            raise ValueError("invalid prepay identity")
        timestamp, nonce, package = str(int(time.time())), uuid4().hex, "prepay_id=" + prepay_id
        return {
            "timeStamp": timestamp,
            "nonceStr": nonce,
            "package": package,
            "signType": "RSA",
            "paySign": sign(self._key, f"{self.appid}\n{timestamp}\n{nonce}\n{package}\n".encode()),
        }
