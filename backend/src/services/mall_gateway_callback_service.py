"""Authentication, durable intake, and recovery for the two WeChat Pay callbacks."""

import base64
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import timedelta

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import get_settings
from ..core.exceptions import ConflictException, NotFoundException
from ..integrations.wechat_pay_crypto import WechatPayVerifier
from ..integrations.wechat_pay_types import (
    PaymentFact,
    PaymentGatewayError,
    RefundFact,
    parse_payment_fact,
    parse_refund_fact,
)
from ..models.mall_base import utc_now
from ..models.mall_finance import MallPayment, MallRefund
from ..models.mall_operations import MallGatewayEvent
from ..models.user import User
from .mall_gateway_event_service import persist_gateway_event
from .mall_job_service import enqueue_mall_job, locked_mall_lease
from .mall_payment_facts_service import locked_payment
from .mall_refund_service import (
    _lock_refund_context,
    _verify_refund_fact,
)

MAX_CALLBACK_BODY_BYTES = 1_100_000
_EVENT_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")


class CallbackFailureError(Exception):
    def __init__(self, status_code: int, code: str):
        self.status_code = status_code
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class VerifiedCallback:
    kind: str
    event_id: str
    event_type: str
    resource_id: str
    resource_json: bytes
    verified_digest: str
    fact: PaymentFact | RefundFact


def _json_object(data: bytes, *, code: str) -> dict:
    try:
        value = json.loads(data)
    except (UnicodeError, ValueError):
        raise CallbackFailureError(400, code) from None
    if not isinstance(value, dict):
        raise CallbackFailureError(400, code)
    return value


def _decrypt_resource(resource: dict, api_v3_key: str) -> dict:
    if (
        resource.get("algorithm") != "AEAD_AES_256_GCM"
        or not isinstance(resource.get("ciphertext"), str)
        or not isinstance(resource.get("nonce"), str)
        or not isinstance(resource.get("associated_data", ""), str)
        or not isinstance(api_v3_key, str)
        or len(api_v3_key.encode("utf-8")) != 32
    ):
        raise CallbackFailureError(400, "invalid_encrypted_resource")
    try:
        ciphertext = base64.b64decode(resource["ciphertext"], validate=True)
        plaintext = AESGCM(api_v3_key.encode("utf-8")).decrypt(
            resource["nonce"].encode("utf-8"),
            ciphertext,
            resource.get("associated_data", "").encode("utf-8"),
        )
    except (ValueError, UnicodeError, InvalidTag):
        raise CallbackFailureError(400, "invalid_encrypted_resource") from None
    return _json_object(plaintext, code="invalid_decrypted_resource")


def verify_and_decrypt_callback(headers, body: bytes, *, kind: str) -> VerifiedCallback:
    """Verify provider identity before parsing or trusting callback facts."""
    settings = get_settings()
    if not settings.mall_gateway_callback_enabled:
        raise CallbackFailureError(503, "callback_receiver_disabled")
    api_v3_key = settings.mall_wechat_api_v3_key
    verify_keys = settings.mall_wechat_verify_keys
    if not isinstance(api_v3_key, str) or len(api_v3_key.encode("utf-8")) != 32 or not verify_keys:
        raise CallbackFailureError(503, "callback_verification_config_unavailable")
    if not isinstance(body, bytes) or not 0 < len(body) <= MAX_CALLBACK_BODY_BYTES:
        raise CallbackFailureError(400, "invalid_callback_body_size")
    try:
        verifier = WechatPayVerifier(verify_keys)
    except (ValueError, TypeError):
        raise CallbackFailureError(503, "callback_verification_config_invalid") from None
    try:
        verifier.verify(headers, body)
    except PaymentGatewayError:
        raise CallbackFailureError(400, "callback_signature_invalid") from None

    envelope = _json_object(body, code="invalid_callback_json")
    event_id, event_type = envelope.get("id"), envelope.get("event_type")
    resource = envelope.get("resource")
    expected_type = "TRANSACTION.SUCCESS" if kind == "payment" else None
    expected_original = "transaction" if kind == "payment" else "refund"
    if (
        kind not in {"payment", "refund"}
        or not isinstance(event_id, str)
        or not _EVENT_ID.fullmatch(event_id)
        or envelope.get("resource_type") != "encrypt-resource"
        or not isinstance(resource, dict)
        or resource.get("original_type", expected_original) != expected_original
    ):
        raise CallbackFailureError(400, "invalid_callback_envelope")
    if expected_type and event_type != expected_type:
        raise CallbackFailureError(400, "unexpected_callback_event")
    if kind == "refund" and event_type not in {
        "REFUND.SUCCESS",
        "REFUND.CLOSED",
        "REFUND.ABNORMAL",
    }:
        raise CallbackFailureError(400, "unexpected_callback_event")

    fact_data = _decrypt_resource(resource, api_v3_key)
    if kind == "payment":
        fact = parse_payment_fact(fact_data)
        if fact.state != "SUCCESS":
            raise CallbackFailureError(400, "unexpected_payment_state")
        resource_id = fact.out_trade_no
    else:
        fact = parse_refund_fact(fact_data)
        expected_status = {
            "REFUND.SUCCESS": "SUCCESS",
            "REFUND.CLOSED": "CLOSED",
            "REFUND.ABNORMAL": "ABNORMAL",
        }[event_type]
        if fact.status != expected_status:
            raise CallbackFailureError(400, "refund_event_state_mismatch")
        resource_id = fact.out_refund_no

    return VerifiedCallback(
        kind=kind,
        event_id=event_id,
        event_type=event_type,
        resource_id=resource_id,
        resource_json=json.dumps(resource, ensure_ascii=False, separators=(",", ":")).encode(),
        verified_digest=hashlib.sha256(body).hexdigest(),
        fact=fact,
    )


async def validate_callback_fact(db: AsyncSession, callback: VerifiedCallback) -> None:
    """Reject signed events that do not match an existing local payment/refund."""
    if callback.kind == "payment" and isinstance(callback.fact, PaymentFact):
        payment_id = await db.scalar(
            select(MallPayment.id).where(MallPayment.out_trade_no == callback.fact.out_trade_no)
        )
        if payment_id is None:
            raise CallbackFailureError(400, "payment_identity_not_found")
        try:
            order, payment = await locked_payment(db, payment_id)
        except NotFoundException:
            raise CallbackFailureError(400, "payment_identity_not_found") from None
        buyer = await db.get(User, order.buyer_user_id, populate_existing=True)
        fact = callback.fact
        if (
            fact.appid != payment.appid_snapshot
            or fact.mchid != payment.mchid_snapshot
            or fact.out_trade_no != payment.out_trade_no
            or fact.total_cent != payment.amount_cent
            or fact.total_cent != order.payable_amount_cent
            or fact.currency != "CNY"
            or fact.payer_total_cent != payment.amount_cent
            or fact.openid is None
            or buyer is None
            or fact.openid != buyer.openid
            or fact.paid_at is None
            or fact.paid_at < order.created_at.replace(tzinfo=None) - timedelta(minutes=5)
            or fact.paid_at > utc_now() + timedelta(minutes=5)
            or not fact.transaction_id
            or (
                payment.status == "succeeded"
                and (
                    payment.channel_transaction_id != fact.transaction_id
                    or (order.active_payment_id == payment.id and order.paid_at != fact.paid_at)
                )
            )
        ):
            raise CallbackFailureError(400, "payment_fact_mismatch")
        duplicate_transaction = await db.scalar(
            select(MallPayment.id).where(
                MallPayment.channel_transaction_id == fact.transaction_id,
                MallPayment.id != payment.id,
            )
        )
        if duplicate_transaction is not None:
            raise CallbackFailureError(400, "payment_transaction_conflict")
        return

    if callback.kind == "refund" and isinstance(callback.fact, RefundFact):
        refund_id = await db.scalar(
            select(MallRefund.id).where(MallRefund.out_refund_no == callback.fact.out_refund_no)
        )
        if refund_id is None:
            raise CallbackFailureError(400, "refund_identity_not_found")
        try:
            order, _, refund, payment = await _lock_refund_context(db, refund_id)
            _verify_refund_fact(order, payment, refund, callback.fact)
        except (ConflictException, NotFoundException):
            raise CallbackFailureError(400, "refund_fact_mismatch") from None
        if callback.fact.channel_refund_id:
            duplicate_refund = await db.scalar(
                select(MallRefund.id).where(
                    MallRefund.channel_refund_id == callback.fact.channel_refund_id,
                    MallRefund.id != refund.id,
                )
            )
            if duplicate_refund is not None:
                raise CallbackFailureError(400, "refund_channel_identity_conflict")
        return

    raise CallbackFailureError(400, "callback_fact_mismatch")


async def accept_verified_callback(
    db: AsyncSession, callback: VerifiedCallback
) -> MallGatewayEvent:
    receipt = await persist_gateway_event(
        db,
        channel="wechatpay",
        event_id=callback.event_id,
        event_type=callback.kind,
        resource_id=callback.resource_id,
        payload_ciphertext=callback.resource_json,
        verified_digest=callback.verified_digest,
    )
    await enqueue_mall_job(
        db,
        kind="gateway_event_apply",
        entity_type="mall_gateway_event",
        entity_id=receipt.event.id,
        entity_version=receipt.event.version,
        dedupe_key=f"wechatpay-callback:{receipt.event.id}",
    )
    return receipt.event


def wechat_callback_handlers(session_factory):
    """Register an idempotent worker that applies verified, committed inbox events."""
    if not get_settings().mall_gateway_callback_enabled:
        return {}

    async def apply_event(item):
        from .mall_payment_facts_service import apply_verified_payment
        from .mall_refund_service import apply_verified_refund

        settings = get_settings()
        if not settings.mall_gateway_callback_enabled:
            raise RuntimeError("callback receiver disabled")
        async with session_factory() as db:
            try:
                if not await locked_mall_lease(db, item):
                    return
                event = await db.scalar(
                    select(MallGatewayEvent)
                    .where(MallGatewayEvent.id == item.entity_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                if event is None:
                    raise RuntimeError("callback event missing")
                if event.status == "processed":
                    await db.commit()
                    return
                resource = _json_object(
                    event.payload_ciphertext or b"", code="invalid_stored_resource"
                )
                fact_data = _decrypt_resource(resource, settings.mall_wechat_api_v3_key)
                if event.event_type == "payment":
                    fact = parse_payment_fact(fact_data)
                    payment = await db.scalar(
                        select(MallPayment).where(MallPayment.out_trade_no == event.resource_id)
                    )
                    if payment is None:
                        raise RuntimeError("callback payment missing")
                    await apply_verified_payment(db, payment.id, fact)
                elif event.event_type == "refund":
                    fact = parse_refund_fact(fact_data)
                    refund = await db.scalar(
                        select(MallRefund).where(MallRefund.out_refund_no == event.resource_id)
                    )
                    if refund is None:
                        raise RuntimeError("callback refund missing")
                    if refund.status == "succeeded" and fact.status in {"CLOSED", "ABNORMAL"}:
                        # A delayed non-success notification cannot undo a newer
                        # locally committed refund success.
                        event.last_error = "stale_after_refund_success"
                    else:
                        await apply_verified_refund(db, refund.id, fact)
                else:
                    raise RuntimeError("callback event type invalid")
                event.status = "processed"
                await db.commit()
            except Exception:
                await db.rollback()
                raise

    return {"gateway_event_apply": apply_event}
