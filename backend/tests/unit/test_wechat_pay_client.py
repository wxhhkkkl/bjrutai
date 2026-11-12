"""Synthetic APIv2 XML responses and a 32-byte test key, never a merchant account."""

import re
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from src.integrations.wechat_pay_crypto import (
    build_v2_xml,
    parse_v2_xml,
    sign_v2,
    verify_v2_signature,
)

API_KEY = "0123456789abcdef0123456789abcdef"
BASE = {"appid": "wx-test", "mch_id": "test-merchant"}


def make_client(respond, *, outbound=True, sign_type="MD5", api_key=API_KEY, **kwargs):
    from src.integrations.wechat_pay_client import WechatPayClient

    return WechatPayClient(
        appid="wx-test",
        mchid="test-merchant",
        api_key=api_key,
        spbill_create_ip="203.0.113.9",
        sign_type=sign_type,
        outbound_enabled=outbound,
        transport=httpx.MockTransport(respond),
        **kwargs,
    )


def xml_response(params, *, return_code="SUCCESS", status=200, api_key=API_KEY, sign_type="MD5"):
    """Build a signed APIv2 XML response with the control fields expected by the client."""
    payload = {"return_code": return_code, "appid": "wx-test", "mch_id": "test-merchant", **params}
    payload["sign_type"] = sign_type
    payload["sign"] = sign_v2(payload, api_key, sign_type)
    return httpx.Response(
        status,
        content=build_v2_xml(payload),
        headers={"Content-Type": "text/xml; charset=utf-8"},
    )


def signed_query_response(params, **kwargs):
    return xml_response({"result_code": "SUCCESS", **params}, **kwargs)


def assert_signed_request(request, path, api_key=API_KEY, sign_type="MD5"):
    assert request.method == "POST"
    assert request.url.path == path
    data = parse_v2_xml(request.content)
    assert verify_v2_signature(data, api_key, fallback_sign_type=sign_type)
    assert data["appid"] == "wx-test" and data["mch_id"] == "test-merchant"
    assert data["nonce_str"]
    assert data["sign_type"] == sign_type
    return data


@pytest.mark.asyncio
async def test_prepay_signs_request_xml_and_generates_fresh_invocation():
    seen = []

    def respond(request):
        seen.append(request)
        data = assert_signed_request(request, "/pay/unifiedorder")
        assert data["out_trade_no"] == "TEST-001"
        assert data["total_fee"] == "21000" and data["fee_type"] == "CNY"
        assert data["body"] == "商城订单"
        assert data["trade_type"] == "JSAPI" and data["openid"] == "test-openid"
        assert data["notify_url"] == "https://merchant.invalid/payment-notify"
        assert data["time_expire"] and re.fullmatch(r"\d{14}", data["time_expire"])
        return signed_query_response({"trade_type": "JSAPI", "prepay_id": "synthetic-prepay"})

    client = make_client(respond)
    result = await client.prepay(
        out_trade_no="TEST-001",
        amount_cent=21000,
        openid="test-openid",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=20),
        notify_url="https://merchant.invalid/payment-notify",
    )
    assert result.prepay_id == "synthetic-prepay"
    assert "synthetic-prepay" not in repr(result)
    first, second = client.invocation(result.prepay_id), client.invocation(result.prepay_id)
    assert first["nonceStr"] != second["nonceStr"]
    assert first["paySign"] == sign_v2(
        {
            "appId": "wx-test",
            "nonceStr": first["nonceStr"],
            "package": first["package"],
            "signType": "MD5",
            "timeStamp": first["timeStamp"],
        },
        API_KEY,
    )
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_prepay_supports_hmac_sha256_signature_type():
    def respond(request):
        assert_signed_request(request, "/pay/unifiedorder", sign_type="HMAC-SHA256")
        return signed_query_response(
            {"trade_type": "JSAPI", "prepay_id": "hmac-prepay"}, sign_type="HMAC-SHA256"
        )

    client = make_client(respond, sign_type="HMAC-SHA256")
    result = await client.prepay(
        out_trade_no="TEST-HMAC",
        amount_cent=100,
        openid="test-openid",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=20),
        notify_url="https://merchant.invalid/payment-notify",
    )
    assert result.prepay_id == "hmac-prepay"
    assert client.invocation(result.prepay_id)["signType"] == "HMAC-SHA256"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    ["unsigned", "tampered", "wrong_merchant", "return_fail", "result_error", "oversize", "non200"],
)
async def test_untrusted_responses_are_never_successful(failure):
    from src.integrations.wechat_pay_client import PaymentGatewayError

    def respond(request):
        if failure == "unsigned":
            return httpx.Response(200, content=build_v2_xml({"return_code": "SUCCESS"}))
        if failure == "tampered":
            body = build_v2_xml(
                {
                    "return_code": "SUCCESS",
                    "appid": "wx-test",
                    "mch_id": "test-merchant",
                    "result_code": "SUCCESS",
                    "total_fee": "21000",
                    "sign": sign_v2(
                        {
                            "return_code": "SUCCESS",
                            "appid": "wx-test",
                            "mch_id": "test-merchant",
                            "result_code": "SUCCESS",
                            "total_fee": "21000",
                        },
                        API_KEY,
                    ),
                }
            ).replace(b"21000", b"21001")
            return httpx.Response(200, content=body)
        if failure == "wrong_merchant":
            return signed_query_response(
                {"appid": "wx-alien", "mch_id": "alien-merchant", "out_trade_no": "TEST-001"}
            )
        if failure == "return_fail":
            return xml_response({}, return_code="FAIL")
        if failure == "result_error":
            return signed_query_response({"result_code": "FAIL", "err_code": "SYSTEMERROR"})
        if failure == "oversize":
            return signed_query_response(
                {"result_code": "SUCCESS", "ignored": "x" * 1_100_000}
            )
        return xml_response({"result_code": "SUCCESS"}, status=500)

    with pytest.raises(PaymentGatewayError):
        await make_client(respond).query("TEST-001")


@pytest.mark.asyncio
async def test_signed_query_establishes_payment_fact_and_close():
    def respond(request):
        if request.url.path == "/pay/orderquery":
            return signed_query_response(
                {
                    "out_trade_no": "TEST-001",
                    "trade_state": "SUCCESS",
                    "transaction_id": "test-channel-id",
                    "total_fee": "21000",
                    "cash_fee": "21000",
                    "fee_type": "CNY",
                    "time_end": "20261104163000",
                    "openid": "test-openid",
                }
            )
        assert request.url.path == "/pay/closeorder"
        return signed_query_response({"out_trade_no": "TEST-001"})

    client = make_client(respond)
    fact = await client.query("TEST-001")
    assert fact.state == "SUCCESS" and fact.total_cent == 21000
    assert fact.openid == "test-openid" and fact.transaction_id == "test-channel-id"
    assert fact.paid_at == datetime(2026, 11, 4, 8, 30)
    assert fact.payer_total_cent == 21000
    closed = await client.close("TEST-001")
    assert closed.out_trade_no == "TEST-001" and closed.mchid == "test-merchant"


@pytest.mark.asyncio
async def test_query_keeps_unpaid_and_closed_states_without_amount_claims():
    def respond(request):
        return signed_query_response(
            {"out_trade_no": "TEST-001", "trade_state": "NOTPAY", "total_fee": "21000"}
        )

    fact = await make_client(respond).query("TEST-001")
    assert fact.state == "NOTPAY" and fact.transaction_id is None and fact.paid_at is None


@pytest.mark.asyncio
async def test_transport_timeout_and_signed_error_are_unknown_not_closed():
    from src.integrations.wechat_pay_client import PaymentGatewayError

    def timeout(request):
        raise httpx.ReadTimeout("private transport detail", request=request)

    with pytest.raises(PaymentGatewayError) as exc:
        await make_client(timeout).close("TEST-001")
    assert "private transport detail" not in str(exc.value)
    with pytest.raises(PaymentGatewayError):
        await make_client(
            lambda _: xml_response({"result_code": "SUCCESS"}, status=500)
        ).close("TEST-001")


@pytest.mark.asyncio
async def test_default_no_outbound_and_reject_path_injection():
    from src.integrations.wechat_pay_client import PaymentGatewayError

    calls = []
    client = make_client(lambda req: calls.append(req), outbound=False)
    with pytest.raises(PaymentGatewayError):
        await client.query("TEST-001")
    assert calls == []
    client = make_client(lambda req: calls.append(req))
    with pytest.raises(ValueError):
        await client.query("../other?mchid=alien")
    assert calls == []


@pytest.mark.asyncio
async def test_only_signed_query_order_not_exist_is_a_verified_absence():
    from src.integrations.wechat_pay_types import PaymentGatewayError, PaymentNotFoundError

    def absent(_):
        return signed_query_response({"result_code": "FAIL", "err_code": "ORDERNOTEXIST"})

    client = make_client(absent)
    with pytest.raises(PaymentNotFoundError):
        await client.query("TEST-ABSENT")
    # Even the same signed absence is never a successful close.
    with pytest.raises(PaymentGatewayError) as error:
        await client.close("TEST-ABSENT")
    assert not isinstance(error.value, PaymentNotFoundError)
    unsigned = make_client(
        lambda _: httpx.Response(200, content=build_v2_xml({"return_code": "SUCCESS"}))
    )
    with pytest.raises(PaymentGatewayError) as error:
        await unsigned.query("TEST-ABSENT")
    assert not isinstance(error.value, PaymentNotFoundError)


@pytest.mark.asyncio
async def test_refund_requires_client_certificate_and_stable_identity(tmp_path):
    from src.integrations.wechat_pay_client import PaymentGatewayError

    client = make_client(lambda req: None)
    with pytest.raises(PaymentGatewayError, match="refund_client_certificate_unavailable"):
        await client.create_refund(
            out_trade_no="TEST-001",
            out_refund_no="R-TEST-001",
            total_cent=21000,
            refund_cent=5000,
        )

    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    cert.write_bytes(b"synthetic certificate")
    key.write_bytes(b"synthetic key")
    seen = []

    def respond(request):
        seen.append(request.url.path)
        if request.url.path == "/secapi/pay/refund":
            data = assert_signed_request(request, "/secapi/pay/refund")
            assert data["out_trade_no"] == "TEST-001" and data["out_refund_no"] == "R-TEST-001"
            assert data["total_fee"] == "21000" and data["refund_fee"] == "5000"
            assert data.get("notify_url", "") == ""
            return signed_query_response(
                {
                    "out_trade_no": "TEST-001",
                    "out_refund_no": "R-TEST-001",
                    "refund_fee": "5000",
                    "total_fee": "21000",
                }
            )
        assert request.url.path == "/pay/refundquery"
        return signed_query_response(
            {
                "out_trade_no": "TEST-001",
                "transaction_id": "synthetic-transaction-id",
                "refund_count": "1",
                "total_fee": "21000",
                "out_refund_no_0": "R-TEST-001",
                "refund_id_0": "synthetic-refund-id",
                "refund_fee_0": "5000",
                "refund_status_0": "PROCESSING",
            }
        )

    client = make_client(
        respond,
        refund_client_cert_path=str(cert),
        refund_client_key_path=str(key),
        refund_notify_url="",
    )
    fact = await client.create_refund(
        out_trade_no="TEST-001",
        out_refund_no="R-TEST-001",
        total_cent=21000,
        refund_cent=5000,
    )
    assert seen == ["/secapi/pay/refund", "/pay/refundquery"]
    assert fact.status == "PROCESSING" and fact.refund_cent == 5000
    assert fact.out_refund_no == "R-TEST-001" and fact.channel_refund_id == "synthetic-refund-id"

    with pytest.raises(ValueError):
        await client.create_refund(
            out_trade_no="TEST-001",
            out_refund_no="R-TEST-001",
            total_cent=21000,
            refund_cent=21001,
        )


@pytest.mark.asyncio
async def test_refund_query_verifies_status_identity_and_signed_absence():
    from src.integrations.wechat_pay_types import PaymentGatewayError, RefundNotFoundError

    def reply(_):
        return signed_query_response(
            {
                "out_trade_no": "TEST-001",
                "transaction_id": "synthetic-transaction-id",
                "refund_count": "1",
                "total_fee": "21000",
                "out_refund_no_0": "R-TEST-001",
                "refund_id_0": "synthetic-refund-id",
                "refund_fee_0": "5000",
                "refund_status_0": "SUCCESS",
                "refund_success_time_0": "2026-11-06 10:30:00",
            }
        )

    fact = await make_client(reply).query_refund("R-TEST-001")
    assert fact.status == "SUCCESS" and fact.success_at is not None
    assert fact.success_at.isoformat() == "2026-11-06T02:30:00"
    assert fact.total_cent == 21000 and fact.transaction_id == "synthetic-transaction-id"

    def absent(_):
        return signed_query_response({"result_code": "FAIL", "err_code": "REFUNDNOTEXIST"})

    with pytest.raises(RefundNotFoundError):
        await make_client(absent).query_refund("R-TEST-ABSENT")
    with pytest.raises(PaymentGatewayError) as error:
        await make_client(
            lambda _: signed_query_response(
                {"result_code": "FAIL", "err_code": "ORDERNOTEXIST"}
            )
        ).query_refund("R-TEST-ABSENT")
    assert not isinstance(error.value, RefundNotFoundError)

    def alien(_):
        return signed_query_response(
            {
                "out_trade_no": "TEST-001",
                "transaction_id": "synthetic-transaction-id",
                "refund_count": "1",
                "out_refund_no_0": "R-ALIEN-001",
                "refund_id_0": "synthetic-refund-id",
                "refund_fee_0": "5000",
                "refund_status_0": "SUCCESS",
                "refund_success_time_0": "2026-11-06 10:30:00",
            }
        )

    with pytest.raises(PaymentGatewayError):
        await make_client(alien).query_refund("R-TEST-001")


@pytest.mark.asyncio
async def test_whole_request_has_deadline_even_when_transport_keeps_waiting():
    import asyncio

    from src.integrations.wechat_pay_client import PaymentGatewayError

    async def slow(request):
        await asyncio.sleep(0.1)
        return signed_query_response({"result_code": "SUCCESS"})

    client = make_client(slow, timeout_seconds=0.01)
    with pytest.raises(PaymentGatewayError, match="transport_result_unknown"):
        await client.query("TEST-001")
