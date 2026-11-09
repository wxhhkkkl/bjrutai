import hashlib
import json
from urllib.parse import parse_qs

import httpx
import pytest

from src.integrations.kuaidi100_client import Kuaidi100Client, Kuaidi100Error


@pytest.mark.asyncio
async def test_map_query_signs_exact_param_and_never_extracts_courier_contacts():
    captured = {}

    async def handler(request):
        captured["url"] = str(request.url)
        captured["body"] = (await request.aread()).decode()
        return httpx.Response(
            200,
            json={
                "status": "200",
                "state": "0",
                "data": [
                    {
                        "leaveTime": "2026-11-06 12:00:00",
                        "name": "北京转运中心",
                        "state": "当前停留节点",
                        "type": "转运中心",
                        "location": "39,116",
                    }
                ],
                "trailUrl": "https://api.kuaidi100.com/tools/map/private-token",
                "courierInfo": {"deliveryManPhone": "13800000000"},
            },
        )

    client = Kuaidi100Client(
        customer="customer-test",
        key="key-test",
        outbound_enabled=True,
        transport=httpx.MockTransport(handler),
    )
    result = await client.query(
        courier_code="yuantong",
        tracking_no="YT1234567890",
        from_city="北京市朝阳区",
        to_city="上海市浦东新区",
    )

    assert captured["url"] == "https://poll.kuaidi100.com/poll/maptrack.do"
    form = parse_qs(captured["body"])
    param_text = form["param"][0]
    assert form["sign"] == [
        hashlib.md5((param_text + "key-testcustomer-test").encode()).hexdigest().upper()
    ]
    params = json.loads(param_text)
    assert params == {
        "com": "yuantong",
        "num": "YT1234567890",
        "from": "北京市朝阳区",
        "to": "上海市浦东新区",
        "resultv2": "5",
        "show": "0",
        "order": "desc",
        "needCourierInfo": False,
    }
    assert "trailUrl" not in result and "courierInfo" not in result


@pytest.mark.asyncio
async def test_map_query_is_closed_without_outbound_authorization():
    called = False

    async def handler(_request):
        nonlocal called
        called = True
        return httpx.Response(200, json={})

    client = Kuaidi100Client(
        customer="customer-test",
        key="key-test",
        outbound_enabled=False,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(Kuaidi100Error, match="outbound_disabled"):
        await client.query(
            courier_code="yuantong",
            tracking_no="YT1234567890",
            from_city="北京市朝阳区",
            to_city="上海市浦东新区",
        )
    assert not called


@pytest.mark.asyncio
async def test_carrier_verification_failure_is_mapped_to_safe_error_code():
    async def handler(_request):
        return httpx.Response(200, json={"status": "408", "message": "phone mismatch"})

    client = Kuaidi100Client(
        customer="customer-test",
        key="key-test",
        outbound_enabled=True,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(Kuaidi100Error) as failure:
        await client.query(
            courier_code="shunfeng",
            tracking_no="SF1234567890",
            from_city="北京市朝阳区",
            to_city="上海市浦东新区",
        )
    assert failure.value.code == "verification_failed"
    assert "phone mismatch" not in str(failure.value)


@pytest.mark.parametrize(
    ("provider_status", "expected"),
    [("500", "no_record"), ("601", "permission_denied"), ("408", "verification_failed")],
)
@pytest.mark.asyncio
async def test_provider_business_errors_map_to_safe_codes(provider_status, expected):
    async def handler(_request):
        return httpx.Response(200, json={"status": provider_status, "message": "private detail"})

    client = Kuaidi100Client(
        customer="customer-test",
        key="key-test",
        outbound_enabled=True,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(Kuaidi100Error) as failure:
        await client.query(
            courier_code="yuantong",
            tracking_no="YT1234567890",
            from_city="北京市朝阳区",
            to_city="上海市浦东新区",
        )
    assert failure.value.code == expected
    assert "private detail" not in str(failure.value)


@pytest.mark.asyncio
async def test_provider_transport_timeout_maps_to_retryable_safe_error():
    async def handler(_request):
        raise httpx.ReadTimeout("private host/network diagnostic")

    client = Kuaidi100Client(
        customer="customer-test",
        key="key-test",
        outbound_enabled=True,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(Kuaidi100Error) as failure:
        await client.query(
            courier_code="yuantong",
            tracking_no="YT1234567890",
            from_city="北京市朝阳区",
            to_city="上海市浦东新区",
        )
    assert failure.value.code == "service_error"
    assert "private host" not in str(failure.value)
