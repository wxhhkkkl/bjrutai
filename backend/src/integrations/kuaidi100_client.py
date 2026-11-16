"""Bounded Kuaidi100 map-track adapter; no outbound call unless explicitly enabled."""

import asyncio
import hashlib
import json
import re
from datetime import datetime, timedelta

import httpx


class Kuaidi100Error(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _identity(value, pattern, code):
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise ValueError(code)
    return value


class Kuaidi100Client:
    URL = "https://poll.kuaidi100.com/poll/maptrack.do"

    def __init__(
        self,
        *,
        customer,
        key,
        outbound_enabled=False,
        transport=None,
        timeout_seconds=10,
    ):
        self.customer, self._key = customer, key
        self._outbound, self._transport = outbound_enabled, transport
        if not 0 < timeout_seconds <= 20:
            raise ValueError("Kuaidi100 request deadline is invalid")
        self._timeout = timeout_seconds

    @staticmethod
    def param_text(*, courier_code, tracking_no, from_city, to_city, phone=None):
        _identity(courier_code, r"[a-z0-9][a-z0-9_-]{0,31}", "invalid_courier_code")
        _identity(tracking_no, r"[A-Za-z0-9-]{6,32}", "invalid_tracking_number")
        for value, code in ((from_city, "invalid_origin"), (to_city, "invalid_destination")):
            if not isinstance(value, str) or not value.strip() or len(value) > 128:
                raise ValueError(code)
        params = {
            "com": courier_code,
            "num": tracking_no,
            "from": from_city.strip(),
            "to": to_city.strip(),
            "resultv2": "7",
            "show": "0",
            "order": "desc",
            "needCourierInfo": False,
        }
        if phone is not None:
            _identity(phone, r"[0-9+() -]{1,24}", "invalid_phone")
            params["phone"] = phone
        return json.dumps(params, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def signature(param_text, key, customer):
        if not key or not customer:
            raise Kuaidi100Error("config_required")
        return hashlib.md5(f"{param_text}{key}{customer}".encode("utf-8")).hexdigest().upper()

    async def query(self, *, courier_code, tracking_no, from_city, to_city, phone=None):
        param_text = self.param_text(
            courier_code=courier_code,
            tracking_no=tracking_no,
            from_city=from_city,
            to_city=to_city,
            phone=phone,
        )
        if not self._outbound:
            raise Kuaidi100Error("outbound_disabled")
        form = {
            "customer": self.customer,
            "sign": self.signature(param_text, self._key, self.customer),
            "param": param_text,
        }
        try:
            async with asyncio.timeout(self._timeout):
                async with httpx.AsyncClient(
                    timeout=self._timeout,
                    transport=self._transport,
                    trust_env=False,
                    follow_redirects=False,
                ) as remote:
                    async with remote.stream(
                        "POST",
                        self.URL,
                        data=form,
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    ) as reply:
                        body = bytearray()
                        async for chunk in reply.aiter_bytes():
                            body.extend(chunk)
                            if len(body) > 1048576:
                                raise Kuaidi100Error("response_too_large")
                        if reply.status_code != 200:
                            raise Kuaidi100Error("service_error")
                        try:
                            payload = json.loads(body)
                        except (ValueError, UnicodeError):
                            raise Kuaidi100Error("invalid_provider_response") from None
        except TimeoutError:
            raise Kuaidi100Error("service_error") from None
        except httpx.HTTPError:
            raise Kuaidi100Error("service_error") from None

        if not isinstance(payload, dict):
            raise Kuaidi100Error("invalid_provider_response")
        status = str(payload.get("status", payload.get("returnCode", "200")))
        if status != "200" or payload.get("result") is False:
            code = {
                "408": "verification_failed",
                "601": "permission_denied",
                "500": "no_record",
            }.get(status, "service_error")
            raise Kuaidi100Error(code)
        events = payload.get("data")
        if events is not None and not isinstance(events, list):
            raise Kuaidi100Error("invalid_provider_response")
        route = payload.get("predictedRoute")
        if route is not None and not isinstance(route, list):
            raise Kuaidi100Error("invalid_provider_response")
        route_info = payload.get("routeInfo")
        if route_info is not None and not isinstance(route_info, dict):
            raise Kuaidi100Error("invalid_provider_response")
        return {
            "state": payload.get("state"),
            "data": events or [],
            "predictedRoute": route or [],
            "routeInfo": route_info or {},
            "arrivalTime": payload.get("arrivalTime"),
            "trailUrl": payload.get("trailUrl"),
            "totalTime": payload.get("totalTime"),
            "remainTime": payload.get("remainTime"),
        }


class FakeKuaidi100Client:
    """Clearly synthetic result for local/dev acceptance; never calls a network."""

    async def query(self, *, courier_code, tracking_no, **_unused):
        now = datetime.now().astimezone().replace(microsecond=0)
        return {
            "source": "fake",
            "state": "0",
            "data": [
                {
                    "leaveTime": now.isoformat(),
                    "name": f"模拟转运节点（运单尾号{tracking_no[-4:]}）联系电话13800000000",
                    "state": "当前停留节点",
                    "type": "模拟节点",
                }
            ],
            "routeInfo": {"cur": {"name": "合肥市"}},
            "predictedRoute": [
                {
                    "leaveTime": now.isoformat(),
                    "name": "模拟当前节点",
                    "state": "当前停留节点",
                    "type": "模拟节点",
                    "location": "117.2272,31.8206",
                },
                {
                    "arriveTime": (now + timedelta(days=2)).isoformat(),
                    "name": "模拟目的节点",
                    "state": "预估途径节点",
                    "type": "模拟节点",
                    "location": "116.4074,39.9042",
                },
            ],
            "arrivalTime": (now + timedelta(days=2)).strftime("%Y-%m-%d %H"),
        }
