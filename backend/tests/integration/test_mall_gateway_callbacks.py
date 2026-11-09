"""WeChat Pay callbacks ACK only after a verified inbox and work item commit."""

import base64
import json
import time

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import func, select

from src.core.config import get_settings
from src.models.mall_finance import MallPayment, MallRefund
from src.models.mall_operations import MallGatewayEvent, MallJob
from src.tasks.mall_tasks import run_mall_worker_once
from tests.conftest import TestAsyncSession
from tests.unit.test_mall_payment_service import payable
from tests.unit.test_mall_refund_service import refund_ready

API_V3_KEY = "0123456789abcdef0123456789abcdef"
PUBLIC_KEY_ID = "PUB_KEY_ID_3000000001"


@pytest.fixture
def callback_keys(monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    settings = get_settings()
    monkeypatch.setattr(settings, "mall_gateway_callback_enabled", True, raising=False)
    monkeypatch.setattr(settings, "mall_wechat_api_v3_key", API_V3_KEY, raising=False)
    monkeypatch.setattr(settings, "mall_wechat_verify_keys", {PUBLIC_KEY_ID: public_pem})
    return private_key


def signed_notification(private_key, *, event_id, event_type, original_type, fact, summary="通知"):
    nonce = "123456789012"
    associated_data = ""
    plaintext = json.dumps(fact, ensure_ascii=False, separators=(",", ":")).encode()
    ciphertext = AESGCM(API_V3_KEY.encode()).encrypt(
        nonce.encode(), plaintext, associated_data.encode()
    )
    envelope = {
        "id": event_id,
        "create_time": "2026-11-09T10:00:00+08:00",
        "event_type": event_type,
        "resource_type": "encrypt-resource",
        "summary": summary,
        "resource": {
            "original_type": original_type,
            "algorithm": "AEAD_AES_256_GCM",
            "ciphertext": base64.b64encode(ciphertext).decode(),
            "associated_data": associated_data,
            "nonce": nonce,
        },
    }
    body = json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode()
    timestamp, header_nonce = str(int(time.time())), "signed-callback-nonce"
    message = timestamp.encode() + b"\n" + header_nonce.encode() + b"\n" + body + b"\n"
    signature = base64.b64encode(
        private_key.sign(message, padding.PKCS1v15(), hashes.SHA256())
    ).decode()
    return body, {
        "Wechatpay-Serial": PUBLIC_KEY_ID,
        "Wechatpay-Timestamp": timestamp,
        "Wechatpay-Nonce": header_nonce,
        "Wechatpay-Signature": signature,
        "Content-Type": "application/json",
    }


def payment_payload(payment, order):
    return {
        "appid": payment.appid_snapshot,
        "mchid": payment.mchid_snapshot,
        "out_trade_no": payment.out_trade_no,
        "transaction_id": "synthetic-channel-id",
        "trade_state": "SUCCESS",
        "success_time": "2026-11-09T10:00:00+08:00",
        "amount": {
            "total": order.payable_amount_cent,
            "payer_total": order.payable_amount_cent,
            "currency": "CNY",
            "payer_currency": "CNY",
        },
        "payer": {"openid": "payment-test-openid"},
    }


@pytest.mark.asyncio
async def test_payment_callback_commits_event_and_worker_applies_payment(
    client, db_session, monkeypatch, callback_keys
):
    _, order, _, payment = await payable(db_session, monkeypatch)
    body, headers = signed_notification(
        callback_keys,
        event_id="payment-event-001",
        event_type="TRANSACTION.SUCCESS",
        original_type="transaction",
        fact=payment_payload(payment, order),
    )

    response = await client.post(
        "/api/v1/mall-gateway/wechat/payment-notify", content=body, headers=headers
    )
    assert response.status_code == 204 and response.content == b""

    async with TestAsyncSession() as committed:
        event = await committed.scalar(select(MallGatewayEvent))
        job = await committed.scalar(select(MallJob).where(MallJob.kind == "gateway_event_apply"))
        assert event and event.status == "pending" and event.payload_ciphertext
        assert job and job.status == "ready" and job.entity_id == event.id
        assert event.payload_ciphertext != body  # Store only the encrypted resource object.

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
    body, headers = signed_notification(
        callback_keys,
        event_id="payment-event-worker-retry",
        event_type="TRANSACTION.SUCCESS",
        original_type="transaction",
        fact=payment_payload(payment, order),
    )
    response = await client.post(
        "/api/v1/mall-gateway/wechat/payment-notify", content=body, headers=headers
    )
    assert response.status_code == 204

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
    fact = {
        "out_refund_no": refund.out_refund_no,
        "out_trade_no": payment.out_trade_no,
        "transaction_id": payment.channel_transaction_id,
        "refund_id": "synthetic-refund-id",
        "status": "SUCCESS",
        "success_time": "2026-11-09T10:00:00+08:00",
        "amount": {
            "total": payment.amount_cent,
            "refund": refund.total_cent,
            "currency": "CNY",
        },
    }
    body, headers = signed_notification(
        callback_keys,
        event_id="refund-event-001",
        event_type="REFUND.SUCCESS",
        original_type="refund",
        fact=fact,
    )
    path = "/api/v1/mall-gateway/wechat/refund-notify"
    first = await client.post(path, content=body, headers=headers)
    replay = await client.post(path, content=body, headers=headers)
    assert first.status_code == replay.status_code == 204
    assert first.content == replay.content == b""

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

    stale_fact = {
        "out_refund_no": refund.out_refund_no,
        "out_trade_no": payment.out_trade_no,
        "transaction_id": payment.channel_transaction_id,
        "status": "CLOSED",
        "amount": {
            "total": payment.amount_cent,
            "refund": refund.total_cent,
            "currency": "CNY",
        },
    }
    stale_body, stale_headers = signed_notification(
        callback_keys,
        event_id="refund-event-delayed-closed",
        event_type="REFUND.CLOSED",
        original_type="refund",
        fact=stale_fact,
    )
    stale_response = await client.post(path, content=stale_body, headers=stale_headers)
    assert stale_response.status_code == 204
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
    ("event_type", "status", "expected_status"),
    [
        ("REFUND.CLOSED", "CLOSED", "closed"),
        ("REFUND.ABNORMAL", "ABNORMAL", "abnormal"),
    ],
)
@pytest.mark.asyncio
async def test_refund_callback_applies_closed_and_abnormal_states_without_calling_them_success(
    client, db_session, monkeypatch, callback_keys, event_type, status, expected_status
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
    fact = {
        "out_refund_no": refund.out_refund_no,
        "out_trade_no": payment.out_trade_no,
        "transaction_id": payment.channel_transaction_id,
        "status": status,
        "amount": {
            "total": payment.amount_cent,
            "refund": refund.total_cent,
            "currency": "CNY",
        },
    }
    body, headers = signed_notification(
        callback_keys,
        event_id=f"refund-event-{status.lower()}-001",
        event_type=event_type,
        original_type="refund",
        fact=fact,
    )
    response = await client.post(
        "/api/v1/mall-gateway/wechat/refund-notify", content=body, headers=headers
    )
    assert response.status_code == 204

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
    body, headers = signed_notification(
        callback_keys,
        event_id="bad-signature-event",
        event_type="TRANSACTION.SUCCESS",
        original_type="transaction",
        fact={"placeholder": True},
    )
    headers["Wechatpay-Signature"] = base64.b64encode(b"not-a-signature").decode()
    response = await client.post(
        "/api/v1/mall-gateway/wechat/payment-notify", content=body, headers=headers
    )
    assert response.status_code in {400, 401, 403}
    assert response.json()["code"] == "FAIL"
    assert await db_session.scalar(select(func.count()).select_from(MallGatewayEvent)) == 0


@pytest.mark.asyncio
async def test_callback_never_acks_a_signed_payment_with_mismatched_amount(
    client, db_session, monkeypatch, callback_keys
):
    _, order, _, payment = await payable(db_session, monkeypatch)
    fact = payment_payload(payment, order)
    fact["amount"]["total"] += 1
    fact["amount"]["payer_total"] += 1
    body, headers = signed_notification(
        callback_keys,
        event_id="payment-event-wrong-amount",
        event_type="TRANSACTION.SUCCESS",
        original_type="transaction",
        fact=fact,
    )
    response = await client.post(
        "/api/v1/mall-gateway/wechat/payment-notify", content=body, headers=headers
    )
    assert response.status_code == 400
    assert response.json()["code"] == "FAIL"
    assert await db_session.scalar(select(func.count()).select_from(MallGatewayEvent)) == 0


@pytest.mark.asyncio
async def test_callback_skips_process_local_idempotency_cache_and_reverifies_signature(
    client, db_session, monkeypatch, callback_keys
):
    _, order, _, payment = await payable(db_session, monkeypatch)
    body, headers = signed_notification(
        callback_keys,
        event_id="payment-event-cache-check",
        event_type="TRANSACTION.SUCCESS",
        original_type="transaction",
        fact=payment_payload(payment, order),
    )
    headers["Idempotency-Key"] = "provider-callback-cache-key-001"
    path = "/api/v1/mall-gateway/wechat/payment-notify"
    accepted = await client.post(path, content=body, headers=headers)
    assert accepted.status_code == 204

    headers["Wechatpay-Signature"] = base64.b64encode(b"bad-signature").decode()
    rejected = await client.post(path, content=body, headers=headers)
    assert rejected.status_code == 400
    assert rejected.json()["code"] == "FAIL"
    assert await db_session.scalar(select(func.count()).select_from(MallGatewayEvent)) == 1


@pytest.mark.asyncio
async def test_callback_persistence_failure_returns_retryable_failure_not_success(
    client, db_session, monkeypatch, callback_keys
):
    _, order, _, payment = await payable(db_session, monkeypatch)
    body, headers = signed_notification(
        callback_keys,
        event_id="payment-event-commit-failure",
        event_type="TRANSACTION.SUCCESS",
        original_type="transaction",
        fact=payment_payload(payment, order),
    )

    original_commit = db_session.commit

    async def fail_commit(*args, **kwargs):
        raise RuntimeError("synthetic transaction commit failure")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    response = await client.post(
        "/api/v1/mall-gateway/wechat/payment-notify", content=body, headers=headers
    )
    assert response.status_code == 500
    assert response.json()["code"] == "FAIL"

    # A failed commit can be ambiguous at the storage boundary. The provider
    # must be able to retry the same event, and intake must repair the job
    # without duplicating the durable inbox record.
    monkeypatch.setattr(db_session, "commit", original_commit)
    retry = await client.post(
        "/api/v1/mall-gateway/wechat/payment-notify", content=body, headers=headers
    )
    assert retry.status_code == 204
    assert await db_session.scalar(select(func.count()).select_from(MallGatewayEvent)) == 1
    assert await db_session.scalar(
        select(func.count()).select_from(MallJob).where(MallJob.kind == "gateway_event_apply")
    ) == 1
