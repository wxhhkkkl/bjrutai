"""WeChat Pay APIv2 callbacks ACK only after a verified inbox and work item commit."""

import base64
import hashlib

import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7
from sqlalchemy import func, select

from src.core.config import get_settings
from src.integrations.wechat_pay_crypto import build_v2_xml, parse_v2_xml, sign_v2
from src.models.mall_finance import MallPayment, MallRefund
from src.models.mall_operations import MallGatewayEvent, MallJob
from src.tasks.mall_tasks import run_mall_worker_once
from tests.conftest import TestAsyncSession
from tests.unit.test_mall_payment_service import payable
from tests.unit.test_mall_refund_service import refund_ready

API_V2_KEY = "0123456789abcdef0123456789abcdef"
XML_HEADERS = {"Content-Type": "text/xml"}


@pytest.fixture
def callback_keys(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "mall_gateway_callback_enabled", True, raising=False)
    monkeypatch.setattr(settings, "mall_wechat_api_v2_key", API_V2_KEY, raising=False)
    monkeypatch.setattr(settings, "mall_wechat_api_v2_sign_type", "MD5", raising=False)
    monkeypatch.setattr(settings, "wechat_app_id", "wx-test", raising=False)
    monkeypatch.setattr(settings, "mall_wechat_mchid", "test-merchant", raising=False)
    return API_V2_KEY


def _envelope(payload, *, sign=True, sign_type="MD5"):
    params = {"return_code": "SUCCESS", "nonce_str": "123456789012", **payload}
    if sign:
        params["sign_type"] = sign_type
        params["sign"] = sign_v2(params, API_V2_KEY, sign_type)
    return build_v2_xml(params)


def payment_notification(payment, order, *, sign=True, total_adjust=0, sign_type="MD5"):
    return _envelope(
        {
            "appid": payment.appid_snapshot,
            "mch_id": payment.mchid_snapshot,
            "out_trade_no": payment.out_trade_no,
            "transaction_id": "synthetic-channel-id",
            "trade_state": "SUCCESS",
            "result_code": "SUCCESS",
            "total_fee": str(order.payable_amount_cent + total_adjust),
            "cash_fee": str(order.payable_amount_cent + total_adjust),
            "fee_type": "CNY",
            "time_end": "20261109100000",
            "openid": "payment-test-openid",
        },
        sign=sign,
        sign_type=sign_type,
    )


def _encrypt_req_info(plaintext: bytes) -> str:
    aes_key = hashlib.md5(API_V2_KEY.encode()).hexdigest().encode("ascii")
    encryptor = Cipher(algorithms.AES(aes_key), modes.ECB()).encryptor()
    padder = PKCS7(algorithms.AES.block_size).padder()
    padded = padder.update(plaintext) + padder.finalize()
    return base64.b64encode(encryptor.update(padded) + encryptor.finalize()).decode()


def refund_notification(refund, payment, *, status="SUCCESS"):
    refund_status = {"SUCCESS": "SUCCESS", "CLOSED": "REFUNDCLOSE", "ABNORMAL": "CHANGE"}[status]
    req_info = {
        "out_refund_no": refund.out_refund_no,
        "out_trade_no": payment.out_trade_no,
        "transaction_id": payment.channel_transaction_id,
        "refund_id": "synthetic-refund-id",
        "refund_fee": str(refund.total_cent),
        "total_fee": str(payment.amount_cent),
        "refund_status": refund_status,
    }
    if status == "SUCCESS":
        req_info["success_time"] = "2026-11-09 10:00:00"
    return _envelope(
        {
            "appid": payment.appid_snapshot,
            "mch_id": payment.mchid_snapshot,
            "req_info": _encrypt_req_info(build_v2_xml(req_info)),
        },
        sign=False,
    )


def ack_success(response):
    assert response.status_code == 200
    assert parse_v2_xml(response.content)["return_code"] == "SUCCESS"


def ack_failure(response):
    assert response.status_code == 200
    assert parse_v2_xml(response.content)["return_code"] == "FAIL"


@pytest.mark.asyncio
async def test_payment_callback_commits_event_and_worker_applies_payment(
    client, db_session, monkeypatch, callback_keys
):
    _, order, _, payment = await payable(db_session, monkeypatch)
    body = payment_notification(payment, order)

    response = await client.post(
        "/api/v1/mall-gateway/wechat/payment-notify", content=body, headers=XML_HEADERS
    )
    ack_success(response)

    async with TestAsyncSession() as committed:
        event = await committed.scalar(select(MallGatewayEvent))
        job = await committed.scalar(select(MallJob).where(MallJob.kind == "gateway_event_apply"))
        assert event and event.status == "pending" and event.payload_ciphertext
        assert job and job.status == "ready" and job.entity_id == event.id
        assert event.payload_ciphertext != body  # Store a normalized fact, never the raw XML.

    from src.services.mall_gateway_callback_service import wechat_callback_handlers

    assert await run_mall_worker_once(
        TestAsyncSession,
        handlers=wechat_callback_handlers(TestAsyncSession),
        enabled=True,
    )
    async with TestAsyncSession() as settled:
        paid = await settled.get(MallPayment, payment.id)
        paid_order = await settled.get(type(order), order.id)
        event = await settled.scalar(select(MallGatewayEvent))
        assert paid.status == "succeeded"
        assert paid_order.status == "pending_shipment"
        assert event.status == "processed"


@pytest.mark.asyncio
async def test_failed_callback_worker_retries_and_recovers_the_committed_event(
    client, db_session, monkeypatch, callback_keys
):
    _, order, _, payment = await payable(db_session, monkeypatch)
    body = payment_notification(payment, order)
    response = await client.post(
        "/api/v1/mall-gateway/wechat/payment-notify", content=body, headers=XML_HEADERS
    )
    ack_success(response)

    from src.services import mall_payment_facts_service
    from src.services.mall_gateway_callback_service import wechat_callback_handlers

    original_apply = mall_payment_facts_service.apply_verified_payment

    async def fail_once(*args, **kwargs):
        raise RuntimeError("synthetic worker interruption")

    monkeypatch.setattr(mall_payment_facts_service, "apply_verified_payment", fail_once)
    handlers = wechat_callback_handlers(TestAsyncSession)
    assert await run_mall_worker_once(TestAsyncSession, handlers=handlers, enabled=True)
    async with TestAsyncSession() as retryable:
        job = await retryable.scalar(
            select(MallJob).where(MallJob.kind == "gateway_event_apply")
        )
        event = await retryable.scalar(select(MallGatewayEvent))
        unpaid = await retryable.get(MallPayment, payment.id)
        assert job.status == "retry" and event.status == "pending"
        assert unpaid.status != "succeeded"
        job.next_run_at = job.next_run_at.replace(year=2000)
        await retryable.commit()

    monkeypatch.setattr(mall_payment_facts_service, "apply_verified_payment", original_apply)
    assert await run_mall_worker_once(TestAsyncSession, handlers=handlers, enabled=True)
    async with TestAsyncSession() as recovered:
        job = await recovered.scalar(
            select(MallJob).where(MallJob.kind == "gateway_event_apply")
        )
        event = await recovered.scalar(select(MallGatewayEvent))
        paid = await recovered.get(MallPayment, payment.id)
        assert job.status == "done" and event.status == "processed"
        assert paid.status == "succeeded"


@pytest.mark.asyncio
async def test_refund_callback_replays_safely_and_completes_original_refund(
    client, db_session, monkeypatch, callback_keys
):
    finance, order, aftersale, _, _, payment = await refund_ready(db_session, monkeypatch)
    from src.schemas.mall_catalog import VersionAction
    from src.services.mall_refund_service import execute_refund

    refund = await execute_refund(
        db_session,
        finance,
        aftersale.id,
        VersionAction(expectedVersion=aftersale.version),
        key="callback-refund-execute-001",
    )
    await db_session.commit()
    body = refund_notification(refund, payment)
    path = "/api/v1/mall-gateway/wechat/refund-notify"
    first = await client.post(path, content=body, headers=XML_HEADERS)
    replay = await client.post(path, content=body, headers=XML_HEADERS)
    ack_success(first)
    ack_success(replay)

    assert await db_session.scalar(select(func.count()).select_from(MallGatewayEvent)) == 1
    assert await db_session.scalar(
        select(func.count()).select_from(MallJob).where(MallJob.kind == "gateway_event_apply")
    ) == 1

    from src.services.mall_gateway_callback_service import wechat_callback_handlers

    assert await run_mall_worker_once(
        TestAsyncSession,
        handlers=wechat_callback_handlers(TestAsyncSession),
        enabled=True,
    )
    async with TestAsyncSession() as settled:
        updated = await settled.get(MallRefund, refund.id)
        assert updated.status == "succeeded"

    stale = refund_notification(refund, payment, status="CLOSED")
    stale_response = await client.post(path, content=stale, headers=XML_HEADERS)
    ack_success(stale_response)
    assert await run_mall_worker_once(
        TestAsyncSession,
        handlers=wechat_callback_handlers(TestAsyncSession),
        enabled=True,
    )
    async with TestAsyncSession() as settled:
        updated = await settled.get(MallRefund, refund.id)
        events = (
            await settled.scalars(select(MallGatewayEvent).order_by(MallGatewayEvent.id))
        ).all()
        assert updated.status == "succeeded"
        assert len(events) == 2 and events[1].status == "processed"
        assert events[1].last_error == "stale_after_refund_success"


@pytest.mark.parametrize(
    ("status", "expected_status"),
    [
        ("CLOSED", "closed"),
        ("ABNORMAL", "abnormal"),
    ],
)
@pytest.mark.asyncio
async def test_refund_callback_applies_closed_and_abnormal_states_without_calling_them_success(
    client, db_session, monkeypatch, callback_keys, status, expected_status
):
    finance, order, aftersale, _, _, payment = await refund_ready(db_session, monkeypatch)
    from src.schemas.mall_catalog import VersionAction
    from src.services.mall_refund_service import execute_refund

    refund = await execute_refund(
        db_session,
        finance,
        aftersale.id,
        VersionAction(expectedVersion=aftersale.version),
        key=f"callback-refund-{status.lower()}-001",
    )
    await db_session.commit()
    body = refund_notification(refund, payment, status=status)
    response = await client.post(
        "/api/v1/mall-gateway/wechat/refund-notify", content=body, headers=XML_HEADERS
    )
    ack_success(response)

    from src.services.mall_gateway_callback_service import wechat_callback_handlers

    assert await run_mall_worker_once(
        TestAsyncSession,
        handlers=wechat_callback_handlers(TestAsyncSession),
        enabled=True,
    )
    async with TestAsyncSession() as settled:
        updated = await settled.get(MallRefund, refund.id)
        assert updated.status == expected_status


@pytest.mark.asyncio
async def test_normal_mall_api_still_uses_the_project_response_envelope(client):
    response = await client.get("/api/v1/mall/categories")
    assert response.status_code == 200
    assert {"code", "message", "data", "requestId", "serverTime"}.issubset(
        response.json()
    )


@pytest.mark.asyncio
async def test_callback_signature_failure_never_creates_event(client, db_session, callback_keys):
    body = _envelope(
        {
            "appid": "wx-test",
            "mch_id": "test-merchant",
            "out_trade_no": "NOT-EXISTING",
            "total_fee": "100",
            "result_code": "SUCCESS",
        },
        sign=False,
    )
    response = await client.post(
        "/api/v1/mall-gateway/wechat/payment-notify", content=body, headers=XML_HEADERS
    )
    ack_failure(response)
    assert await db_session.scalar(select(func.count()).select_from(MallGatewayEvent)) == 0


@pytest.mark.asyncio
async def test_callback_never_acks_a_signed_payment_with_mismatched_amount(
    client, db_session, monkeypatch, callback_keys
):
    _, order, _, payment = await payable(db_session, monkeypatch)
    body = payment_notification(payment, order, total_adjust=1)
    response = await client.post(
        "/api/v1/mall-gateway/wechat/payment-notify", content=body, headers=XML_HEADERS
    )
    ack_failure(response)
    assert await db_session.scalar(select(func.count()).select_from(MallGatewayEvent)) == 0


@pytest.mark.asyncio
async def test_callback_skips_process_local_idempotency_cache_and_reverifies_signature(
    client, db_session, monkeypatch, callback_keys
):
    _, order, _, payment = await payable(db_session, monkeypatch)
    body = payment_notification(payment, order)
    headers = {"Content-Type": "text/xml", "Idempotency-Key": "provider-callback-cache-key-001"}
    path = "/api/v1/mall-gateway/wechat/payment-notify"
    accepted = await client.post(path, content=body, headers=headers)
    ack_success(accepted)

    tampered = payment_notification(payment, order, sign=False)
    rejected = await client.post(path, content=tampered, headers=headers)
    ack_failure(rejected)
    assert await db_session.scalar(select(func.count()).select_from(MallGatewayEvent)) == 1


@pytest.mark.asyncio
async def test_callback_persistence_failure_returns_retryable_failure_not_success(
    client, db_session, monkeypatch, callback_keys
):
    _, order, _, payment = await payable(db_session, monkeypatch)
    body = payment_notification(payment, order)
    headers = {"Content-Type": "text/xml"}
    path = "/api/v1/mall-gateway/wechat/payment-notify"

    original_commit = db_session.commit

    async def fail_commit(*args, **kwargs):
        raise RuntimeError("synthetic transaction commit failure")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    response = await client.post(path, content=body, headers=headers)
    ack_failure(response)

    # A failed commit can be ambiguous at the storage boundary. The provider
    # must be able to retry the same event, and intake must repair the job
    # without duplicating the durable inbox record.
    monkeypatch.setattr(db_session, "commit", original_commit)
    retry = await client.post(path, content=body, headers=headers)
    ack_success(retry)
    assert await db_session.scalar(select(func.count()).select_from(MallGatewayEvent)) == 1
    assert await db_session.scalar(
        select(func.count()).select_from(MallJob).where(MallJob.kind == "gateway_event_apply")
    ) == 1


@pytest.mark.asyncio
async def test_payment_callback_accepts_hmac_sha256_and_configured_fallback(
    client, db_session, monkeypatch, callback_keys
):
    monkeypatch.setattr(
        get_settings(), "mall_wechat_api_v2_sign_type", "HMAC-SHA256", raising=False
    )
    _, order, _, payment = await payable(db_session, monkeypatch)
    explicit = payment_notification(payment, order, sign_type="HMAC-SHA256")
    response = await client.post(
        "/api/v1/mall-gateway/wechat/payment-notify", content=explicit, headers=XML_HEADERS
    )
    ack_success(response)

    # A notification that omits sign_type is verified against the configured
    # fallback, with the signature computed over the fields actually sent.
    params = {
        "return_code": "SUCCESS",
        "nonce_str": "123456789012",
        "appid": payment.appid_snapshot,
        "mch_id": payment.mchid_snapshot,
        "out_trade_no": payment.out_trade_no,
        "transaction_id": "synthetic-channel-id-2",
        "trade_state": "SUCCESS",
        "result_code": "SUCCESS",
        "total_fee": str(order.payable_amount_cent),
        "cash_fee": str(order.payable_amount_cent),
        "fee_type": "CNY",
        "time_end": "20261109100000",
        "openid": "payment-test-openid",
    }
    params["sign"] = sign_v2(params, API_V2_KEY, "HMAC-SHA256")
    fallback = build_v2_xml(params)
    accepted = await client.post(
        "/api/v1/mall-gateway/wechat/payment-notify", content=fallback, headers=XML_HEADERS
    )
    ack_success(accepted)

    # An explicit sign_type in the payload is honored as the protocol dictates;
    # the configured value only supplies the fallback when the field is absent.
    # What must always fail is a body signed with an unknown key, before any
    # fact validation and without creating an inbox event.
    wrong_key_params = {
        "appid": payment.appid_snapshot,
        "mch_id": payment.mchid_snapshot,
        "out_trade_no": payment.out_trade_no,
        "transaction_id": "synthetic-channel-id-3",
        "trade_state": "SUCCESS",
        "result_code": "SUCCESS",
        "total_fee": str(order.payable_amount_cent),
        "cash_fee": str(order.payable_amount_cent),
        "fee_type": "CNY",
        "time_end": "20261109100000",
        "openid": "payment-test-openid",
    }
    wrong_key_params["sign_type"] = "HMAC-SHA256"
    wrong_key_params["sign"] = sign_v2(
        wrong_key_params, "abcdef0123456789abcdef0123456789", "HMAC-SHA256"
    )
    rejected = await client.post(
        "/api/v1/mall-gateway/wechat/payment-notify",
        content=build_v2_xml(wrong_key_params),
        headers=XML_HEADERS,
    )
    ack_failure(rejected)
    assert await db_session.scalar(select(func.count()).select_from(MallGatewayEvent)) == 2


@pytest.mark.asyncio
async def test_callback_rejects_non_xml_content_type_and_empty_body(
    client, db_session, monkeypatch, callback_keys
):
    _, order, _, payment = await payable(db_session, monkeypatch)
    body = payment_notification(payment, order)
    for headers in ({"Content-Type": "application/json"}, {"Content-Type": "text/plain"}):
        response = await client.post(
            "/api/v1/mall-gateway/wechat/payment-notify", content=body, headers=headers
        )
        ack_failure(response)
    empty = await client.post(
        "/api/v1/mall-gateway/wechat/payment-notify", content=b"", headers=XML_HEADERS
    )
    ack_failure(empty)
    assert await db_session.scalar(select(func.count()).select_from(MallGatewayEvent)) == 0


@pytest.mark.asyncio
async def test_callback_rejects_oversized_body_without_creating_event(
    client, db_session, callback_keys
):
    from src.services.mall_gateway_callback_service import MAX_CALLBACK_BODY_BYTES

    response = await client.post(
        "/api/v1/mall-gateway/wechat/payment-notify",
        content=b"a" * (MAX_CALLBACK_BODY_BYTES + 1),
        headers=XML_HEADERS,
    )
    ack_failure(response)
    assert await db_session.scalar(select(func.count()).select_from(MallGatewayEvent)) == 0


@pytest.mark.asyncio
async def test_callback_fails_closed_when_receiver_disabled_or_key_unconfigured(
    client, db_session, monkeypatch, callback_keys
):
    settings = get_settings()
    _, order, _, payment = await payable(db_session, monkeypatch)
    body = payment_notification(payment, order)

    monkeypatch.setattr(settings, "mall_gateway_callback_enabled", False, raising=False)
    disabled = await client.post(
        "/api/v1/mall-gateway/wechat/payment-notify", content=body, headers=XML_HEADERS
    )
    ack_failure(disabled)

    monkeypatch.setattr(settings, "mall_gateway_callback_enabled", True, raising=False)
    monkeypatch.setattr(settings, "mall_wechat_api_v2_key", "", raising=False)
    unconfigured = await client.post(
        "/api/v1/mall-gateway/wechat/payment-notify", content=body, headers=XML_HEADERS
    )
    ack_failure(unconfigured)
    assert await db_session.scalar(select(func.count()).select_from(MallGatewayEvent)) == 0


@pytest.mark.asyncio
async def test_callback_rejects_merchant_mismatch_and_provider_failure_envelope(
    client, db_session, callback_keys
):
    foreign = _envelope(
        {
            "appid": "wx-other-app",
            "mch_id": "other-merchant",
            "out_trade_no": "FOREIGN-TRADE-001",
            "total_fee": "100",
            "result_code": "SUCCESS",
        }
    )
    response = await client.post(
        "/api/v1/mall-gateway/wechat/payment-notify", content=foreign, headers=XML_HEADERS
    )
    ack_failure(response)

    provider_failed = _envelope({"return_code": "FAIL", "return_msg": "provider down"})
    failed = await client.post(
        "/api/v1/mall-gateway/wechat/payment-notify",
        content=provider_failed,
        headers=XML_HEADERS,
    )
    ack_failure(failed)
    assert await db_session.scalar(select(func.count()).select_from(MallGatewayEvent)) == 0


@pytest.mark.asyncio
async def test_callback_rejects_payment_with_result_code_failure(
    client, db_session, monkeypatch, callback_keys
):
    _, order, _, payment = await payable(db_session, monkeypatch)
    body = _envelope(
        {
            "appid": payment.appid_snapshot,
            "mch_id": payment.mchid_snapshot,
            "out_trade_no": payment.out_trade_no,
            "transaction_id": "synthetic-channel-id",
            "trade_state": "PAYERROR",
            "result_code": "FAIL",
            "total_fee": str(order.payable_amount_cent),
            "cash_fee": str(order.payable_amount_cent),
            "fee_type": "CNY",
            "time_end": "20261109100000",
            "openid": "payment-test-openid",
        }
    )
    response = await client.post(
        "/api/v1/mall-gateway/wechat/payment-notify", content=body, headers=XML_HEADERS
    )
    ack_failure(response)
    assert await db_session.scalar(select(func.count()).select_from(MallGatewayEvent)) == 0


@pytest.mark.asyncio
async def test_refund_callback_rejects_tampered_req_info_and_unknown_refund(
    client, db_session, monkeypatch, callback_keys
):
    from src.schemas.mall_catalog import VersionAction
    from src.services.mall_refund_service import execute_refund

    finance, order, aftersale, _, _, payment = await refund_ready(db_session, monkeypatch)
    refund = await execute_refund(
        db_session,
        finance,
        aftersale.id,
        VersionAction(expectedVersion=aftersale.version),
        key="callback-refund-tamper-001",
    )
    await db_session.commit()
    path = "/api/v1/mall-gateway/wechat/refund-notify"

    tampered = _envelope(
        {
            "appid": payment.appid_snapshot,
            "mch_id": payment.mchid_snapshot,
            "req_info": base64.b64encode(b"not-pkcs7-padded").decode(),
        },
        sign=False,
    )
    bad_crypto = await client.post(path, content=tampered, headers=XML_HEADERS)
    ack_failure(bad_crypto)

    # A well-formed encrypted payload for a refund this platform never issued
    # must be rejected at identity validation, without an inbox event.
    unknown_req_info = build_v2_xml(
        {
            "out_refund_no": "UNKNOWN-OUT-REFUND-001",
            "out_trade_no": payment.out_trade_no,
            "transaction_id": payment.channel_transaction_id,
            "refund_id": "synthetic-refund-id",
            "refund_fee": str(refund.total_cent),
            "total_fee": str(payment.amount_cent),
            "refund_status": "SUCCESS",
            "success_time": "2026-11-09 10:00:00",
        }
    )
    unknown = _envelope(
        {
            "appid": payment.appid_snapshot,
            "mch_id": payment.mchid_snapshot,
            "req_info": _encrypt_req_info(unknown_req_info),
        },
        sign=False,
    )
    not_found = await client.post(path, content=unknown, headers=XML_HEADERS)
    ack_failure(not_found)
    assert await db_session.scalar(select(func.count()).select_from(MallGatewayEvent)) == 0
