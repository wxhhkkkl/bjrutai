"""Synthetic RSA keys and signed HTTP doubles, never a merchant account."""

import base64
import json
import re
import time
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID


@pytest.fixture
def pay_keys():
    merchant = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    platform = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    platform_next = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return merchant, platform, platform_next


def pem(key):
    return key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()


def public_pem(key):
    return (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )


def signed_response(key, body, *, status=200, serial="PUB_KEY_ID_1", stamp=None):
    timestamp = str(stamp if stamp is not None else int(time.time()))
    nonce = "response-test-nonce"
    payload = timestamp.encode() + b"\n" + nonce.encode() + b"\n" + body + b"\n"
    signature = base64.b64encode(key.sign(payload, padding.PKCS1v15(), hashes.SHA256())).decode()
    return httpx.Response(
        status,
        content=body,
        headers={
            "Wechatpay-Timestamp": timestamp,
            "Wechatpay-Nonce": nonce,
            "Wechatpay-Serial": serial,
            "Wechatpay-Signature": signature,
            "Wechatpay-Signature-Type": "WECHATPAY2-SHA256-RSA2048",
        },
    )


def make_client(keys, respond, *, outbound=True, **kwargs):
    from src.integrations.wechat_pay_client import WechatPayClient

    return WechatPayClient(
        appid="wx-test",
        mchid="test-merchant",
        merchant_serial="A1",
        private_key_pem=pem(keys[0]),
        verify_keys={"PUB_KEY_ID_1": public_pem(keys[1]), "PUB_KEY_ID_2": public_pem(keys[2])},
        outbound_enabled=outbound,
        transport=httpx.MockTransport(respond),
        **kwargs,
    )


@pytest.mark.asyncio
async def test_create_signs_exact_bytes_and_generates_fresh_invocation(pay_keys):
    seen = []

    def respond(request):
        seen.append(request)
        auth = dict(re.findall(r'(\w+)="([^"]+)"', request.headers["Authorization"]))
        payload = (
            (
                request.method
                + "\n"
                + request.url.raw_path.decode()
                + "\n"
                + auth["timestamp"]
                + "\n"
                + auth["nonce_str"]
                + "\n"
            ).encode()
            + request.content
            + b"\n"
        )
        pay_keys[0].public_key().verify(
            base64.b64decode(auth["signature"]), payload, padding.PKCS1v15(), hashes.SHA256()
        )
        assert request.url.host == "api.mch.weixin.qq.com"
        assert json.loads(request.content)["amount"] == {"total": 21000, "currency": "CNY"}
        return signed_response(pay_keys[1], b'{"prepay_id":"synthetic-prepay"}')

    client = make_client(pay_keys, respond)
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
    message = f'wx-test\n{first["timeStamp"]}\n{first["nonceStr"]}\n{first["package"]}\n'.encode()
    pay_keys[0].public_key().verify(
        base64.b64decode(first["paySign"]), message, padding.PKCS1v15(), hashes.SHA256()
    )
    assert len(seen) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", ["unknown_key", "tampered", "stale", "missing", "probe", "oversize"]
)
async def test_untrusted_responses_are_never_successful(pay_keys, failure):
    from src.integrations.wechat_pay_client import PaymentGatewayError

    def respond(request):
        body = b'{"prepay_id":"test"}'
        result = signed_response(pay_keys[1], body)
        if failure == "unknown_key":
            result.headers["Wechatpay-Serial"] = "PUB_KEY_ID_999"
        elif failure == "tampered":
            result = httpx.Response(200, content=b'{"prepay_id":"changed"}', headers=result.headers)
        elif failure == "stale":
            result = signed_response(pay_keys[1], body, stamp=int(time.time()) - 301)
        elif failure == "missing":
            del result.headers["Wechatpay-Signature"]
        elif failure == "probe":
            result.headers["Wechatpay-Signature"] = "WECHATPAY/SIGNTEST/example"
        elif failure == "oversize":
            result = signed_response(pay_keys[1], b"x" * 1048577)
        return result

    client = make_client(pay_keys, respond)
    with pytest.raises(PaymentGatewayError):
        await client.query("TEST-001")


@pytest.mark.asyncio
async def test_query_rotation_and_signed_empty_close(pay_keys):
    payload = {
        "appid": "wx-test",
        "mchid": "test-merchant",
        "out_trade_no": "TEST-001",
        "trade_state": "SUCCESS",
        "transaction_id": "test-channel-id",
        "success_time": "2026-11-05T00:30:00+08:00",
        "payer": {"openid": "test-openid"},
        "amount": {
            "total": 21000,
            "payer_total": 21000,
            "currency": "CNY",
            "payer_currency": "CNY",
        },
    }

    def respond(request):
        if request.method == "GET":
            assert str(request.url).endswith("TEST-001?mchid=test-merchant")
            return signed_response(pay_keys[2], json.dumps(payload).encode(), serial="PUB_KEY_ID_2")
        assert request.url.path.endswith("/TEST-001/close")
        return signed_response(pay_keys[1], b"", status=204)

    client = make_client(pay_keys, respond)
    fact = await client.query("TEST-001")
    assert fact.state == "SUCCESS" and fact.total_cent == 21000 and fact.openid == "test-openid"
    assert fact.paid_at == datetime(2026, 11, 4, 16, 30)
    closed = await client.close("TEST-001")
    assert closed.out_trade_no == "TEST-001" and closed.mchid == "test-merchant"


@pytest.mark.asyncio
async def test_transport_timeout_and_signed_error_are_unknown_not_closed(pay_keys):
    from src.integrations.wechat_pay_client import PaymentGatewayError

    def timeout(request):
        raise httpx.ReadTimeout("private transport detail", request=request)

    with pytest.raises(PaymentGatewayError) as exc:
        await make_client(pay_keys, timeout).close("TEST-001")
    assert "private transport detail" not in str(exc.value)
    with pytest.raises(PaymentGatewayError):
        await make_client(
            pay_keys, lambda _: signed_response(pay_keys[1], b'{"code":"ORDERPAID"}', status=400)
        ).close("TEST-001")


@pytest.mark.asyncio
async def test_default_no_outbound_and_reject_path_injection(pay_keys):
    from src.integrations.wechat_pay_client import PaymentGatewayError

    calls = []
    client = make_client(pay_keys, lambda req: calls.append(req), outbound=False)
    with pytest.raises(PaymentGatewayError):
        await client.query("TEST-001")
    assert calls == []
    client = make_client(pay_keys, lambda req: calls.append(req))
    with pytest.raises(ValueError):
        await client.query("../other?mchid=alien")
    assert calls == []


def test_certificate_validity_and_exact_serial_are_checked(pay_keys):
    from src.integrations.wechat_pay_client import PaymentGatewayError
    from src.integrations.wechat_pay_crypto import WechatPayVerifier

    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "synthetic-test")])

    def certificate(before, after):
        return (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(pay_keys[1].public_key())
            .serial_number(0xABC)
            .not_valid_before(before)
            .not_valid_after(after)
            .sign(pay_keys[1], hashes.SHA256())
            .public_bytes(serialization.Encoding.PEM)
            .decode()
        )

    now = datetime.now(timezone.utc)
    good = certificate(now - timedelta(days=1), now + timedelta(days=1))
    verifier = WechatPayVerifier({"ABC": good})
    reply = signed_response(pay_keys[1], b"", serial="ABC", status=204)
    verifier.verify(reply.headers, b"")
    expired = certificate(now - timedelta(days=2), now - timedelta(days=1))
    with pytest.raises(PaymentGatewayError):
        WechatPayVerifier({"ABC": expired}).verify(reply.headers, b"")
    with pytest.raises(ValueError):
        WechatPayVerifier({"WRONG": good})


@pytest.mark.asyncio
async def test_whole_request_has_deadline_even_when_transport_keeps_waiting(pay_keys):
    import asyncio

    from src.integrations.wechat_pay_client import PaymentGatewayError

    async def slow(request):
        await asyncio.sleep(0.1)
        return signed_response(pay_keys[1], b"{}")

    client = make_client(pay_keys, slow, timeout_seconds=0.01)
    with pytest.raises(PaymentGatewayError, match="transport_result_unknown"):
        await client.query("TEST-001")


@pytest.mark.asyncio
async def test_only_signed_query_order_not_exist_is_a_verified_absence(pay_keys):
    from src.integrations.wechat_pay_types import PaymentGatewayError, PaymentNotFoundError

    def reply(_):
        return signed_response(pay_keys[1], b'{"code":"ORDER_NOT_EXIST"}', status=404)

    client = make_client(pay_keys, reply)
    with pytest.raises(PaymentNotFoundError):
        await client.query("TEST-ABSENT")
    # Even the same signed 404 is never a successful close.
    with pytest.raises(PaymentGatewayError) as error:
        await client.close("TEST-ABSENT")
    assert not isinstance(error.value, PaymentNotFoundError)
    unsigned = make_client(
        pay_keys, lambda _: httpx.Response(404, json={"code": "ORDER_NOT_EXIST"})
    )
    with pytest.raises(PaymentGatewayError) as error:
        await unsigned.query("TEST-ABSENT")
    assert not isinstance(error.value, PaymentNotFoundError)


@pytest.mark.asyncio
async def test_refund_uses_original_payment_and_stable_refund_identity(pay_keys):
    seen = []
    response = {
        "refund_id": "synthetic-refund-id",
        "out_refund_no": "R-TEST-001",
        "transaction_id": "synthetic-transaction-id",
        "out_trade_no": "TEST-001",
        "status": "PROCESSING",
        "amount": {"total": 21000, "refund": 5000, "currency": "CNY"},
    }

    def reply(request):
        seen.append(request)
        assert request.method == "POST"
        assert request.url.path == "/v3/refund/domestic/refunds"
        payload = json.loads(request.content)
        assert payload == {
            "out_trade_no": "TEST-001",
            "out_refund_no": "R-TEST-001",
            "amount": {"refund": 5000, "total": 21000, "currency": "CNY"},
        }
        assert "notify_url" not in payload and "account" not in payload
        return signed_response(pay_keys[1], json.dumps(response).encode())

    fact = await make_client(pay_keys, reply).create_refund(
        out_trade_no="TEST-001",
        out_refund_no="R-TEST-001",
        total_cent=21000,
        refund_cent=5000,
    )
    assert fact.status == "PROCESSING" and fact.refund_cent == 5000
    assert fact.out_refund_no == "R-TEST-001" and len(seen) == 1


@pytest.mark.asyncio
async def test_refund_query_verifies_status_identity_and_signed_absence(pay_keys):
    from src.integrations.wechat_pay_types import PaymentGatewayError, RefundNotFoundError

    response = {
        "refund_id": "synthetic-refund-id",
        "out_refund_no": "R-TEST-001",
        "transaction_id": "synthetic-transaction-id",
        "out_trade_no": "TEST-001",
        "success_time": "2026-11-06T10:30:00+08:00",
        "status": "SUCCESS",
        "amount": {"total": 21000, "refund": 5000, "currency": "CNY"},
    }

    fact = await make_client(
        pay_keys, lambda _: signed_response(pay_keys[1], json.dumps(response).encode())
    ).query_refund("R-TEST-001")
    assert fact.status == "SUCCESS" and fact.success_at is not None
    assert fact.success_at.isoformat() == "2026-11-06T02:30:00"

    def absent(_):
        return signed_response(pay_keys[1], b'{"code":"RESOURCE_NOT_EXISTS"}', status=404)

    with pytest.raises(RefundNotFoundError):
        await make_client(pay_keys, absent).query_refund("R-TEST-ABSENT")
    with pytest.raises(PaymentGatewayError) as error:
        await make_client(
            pay_keys,
            lambda _: signed_response(pay_keys[1], b'{"code":"ORDER_NOT_EXIST"}', status=404),
        ).query_refund("R-TEST-ABSENT")
    assert not isinstance(error.value, RefundNotFoundError)

    bad = {**response, "out_refund_no": "R-ALIEN-001"}
    with pytest.raises(PaymentGatewayError):
        await make_client(
            pay_keys, lambda _: signed_response(pay_keys[1], json.dumps(bad).encode())
        ).query_refund("R-TEST-001")
