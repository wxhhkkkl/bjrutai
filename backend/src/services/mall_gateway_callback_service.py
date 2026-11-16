"""Authentication, durable intake, and recovery for WeChat Pay APIv2 callbacks."""

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import get_settings
from ..core.exceptions import ConflictException, NotFoundException
from ..integrations.wechat_pay_crypto import (
    decrypt_refund_req_info,
    parse_v2_xml,
    verify_v2_signature,
)
from ..integrations.wechat_pay_types import (
    PaymentFact,
    PaymentGatewayError,
    RefundFact,
    parse_api_v2_payment_fact,
    parse_api_v2_refund_notification,
)
from ..models.mall_base import utc_now
from ..models.mall_finance import MallPayment, MallRefund
from ..models.mall_operations import MallGatewayEvent
from ..models.user import User
from .mall_gateway_event_service import persist_gateway_event
from .mall_job_service import enqueue_mall_job, locked_mall_lease
from .mall_payment_facts_service import locked_payment
from .mall_refund_service import _lock_refund_context, _verify_refund_fact

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


def _parse_notification_xml(body: bytes) -> dict:
    try:
        return parse_v2_xml(body)
    except PaymentGatewayError:
        raise CallbackFailureError(400, "invalid_callback_xml") from None


def _callback_storage_payload(
    kind: str,
    fact: PaymentFact | RefundFact,
    *,
    api_key: str,
    resource_id: str,
    verified_digest: str,
) -> bytes:
    """Store a MAC-bound normalized fact without buyer openid or raw XML."""
    if kind == "payment" and isinstance(fact, PaymentFact):
        paid_time = fact.paid_at.replace(tzinfo=timezone.utc).astimezone(
            ZoneInfo("Asia/Shanghai")
        )
        payload = {
            "appid": fact.appid,
            "mch_id": fact.mchid,
            "out_trade_no": fact.out_trade_no,
            "trade_state": fact.state,
            "total_fee": str(fact.total_cent),
            "cash_fee": str(fact.payer_total_cent),
            "fee_type": fact.currency,
            "transaction_id": fact.transaction_id,
            "time_end": paid_time.strftime("%Y%m%d%H%M%S"),
        }
    elif kind == "refund" and isinstance(fact, RefundFact):
        statuses = {"SUCCESS": "SUCCESS", "CLOSED": "REFUNDCLOSE", "ABNORMAL": "CHANGE"}
        payload = {
            "out_refund_no": fact.out_refund_no,
            "out_trade_no": fact.out_trade_no,
            "refund_status": statuses[fact.status],
            "total_fee": str(fact.total_cent),
            "refund_fee": str(fact.refund_cent),
            "refund_id": fact.channel_refund_id or "",
            "transaction_id": fact.transaction_id or "",
        }
        if fact.success_at is not None:
            local_time = fact.success_at.replace(tzinfo=timezone.utc).astimezone(
                ZoneInfo("Asia/Shanghai")
            )
            payload["success_time"] = local_time.strftime("%Y-%m-%d %H:%M:%S")
    else:
        raise CallbackFailureError(400, "callback_fact_mismatch")
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    mac_key = hmac.new(
        api_key.encode("utf-8"), b"mall-wechat-api-v2-inbox-mac-key-v1", hashlib.sha256
    ).digest()
    message = b"\n".join(
        (
            b"mall-wechat-api-v2-inbox-v1",
            kind.encode("ascii"),
            resource_id.encode("utf-8"),
            verified_digest.encode("ascii"),
            encoded,
        )
    )
    mac = hmac.new(mac_key, message, hashlib.sha256).hexdigest()
    return json.dumps(
        {"fact": payload, "mac": mac}, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def _verify_stored_callback_fact(event, envelope: dict, api_key: str) -> dict:
    fact = envelope.get("fact")
    supplied = envelope.get("mac")
    if not isinstance(fact, dict) or not isinstance(supplied, str):
        raise RuntimeError("stored callback integrity invalid")
    encoded = json.dumps(fact, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    mac_key = hmac.new(
        api_key.encode("utf-8"), b"mall-wechat-api-v2-inbox-mac-key-v1", hashlib.sha256
    ).digest()
    message = b"\n".join(
        (
            b"mall-wechat-api-v2-inbox-v1",
            event.event_type.encode("ascii"),
            event.resource_id.encode("utf-8"),
            event.verified_digest.encode("ascii"),
            encoded,
        )
    )
    expected = hmac.new(mac_key, message, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(supplied, expected):
        raise RuntimeError("stored callback integrity invalid")
    return fact


def verify_and_decrypt_callback(headers, body: bytes, *, kind: str) -> VerifiedCallback:
    """Verify APIv2 payment XML or decrypt the APIv2 refund notification payload."""
    settings = get_settings()
    if not settings.mall_gateway_callback_enabled:
        raise CallbackFailureError(503, "callback_receiver_disabled")
    api_key = settings.mall_wechat_api_v2_key
    if not isinstance(api_key, str) or len(api_key.encode("utf-8")) != 32:
        raise CallbackFailureError(503, "callback_verification_config_unavailable")
    if kind not in {"payment", "refund"}:
        raise CallbackFailureError(400, "invalid_callback_kind")
    if not isinstance(body, bytes) or not 0 < len(body) <= MAX_CALLBACK_BODY_BYTES:
        raise CallbackFailureError(400, "invalid_callback_body_size")
    envelope = _parse_notification_xml(body)
    if envelope.get("return_code") != "SUCCESS":
        raise CallbackFailureError(400, "provider_notification_failed")
    nonce = envelope.get("nonce_str")
    if not isinstance(nonce, str) or not 0 < len(nonce) <= 32 or "\r" in nonce or "\n" in nonce:
        raise CallbackFailureError(400, "invalid_callback_nonce")
    if (envelope.get("appid"), envelope.get("mch_id")) != (
        settings.wechat_app_id,
        settings.mall_wechat_mchid,
    ):
        raise CallbackFailureError(400, "callback_merchant_mismatch")

    digest = hashlib.sha256(body).hexdigest()
    event_id = ("v2p_" if kind == "payment" else "v2r_") + digest
    if kind == "payment":
        if not verify_v2_signature(
            envelope, api_key, fallback_sign_type=settings.mall_wechat_api_v2_sign_type
        ):
            raise CallbackFailureError(400, "callback_signature_invalid")
        if envelope.get("result_code") != "SUCCESS":
            raise CallbackFailureError(400, "unexpected_payment_state")
        try:
            fact = parse_api_v2_payment_fact(envelope)
        except PaymentGatewayError:
            raise CallbackFailureError(400, "invalid_payment_notification") from None
        if fact.state != "SUCCESS":
            raise CallbackFailureError(400, "unexpected_payment_state")
        resource_id = fact.out_trade_no
    else:
        # V2 refund notifications carry an encrypted req_info rather than a
        # Wechatpay-Signature header or a sign field.
        try:
            decrypted = decrypt_refund_req_info(envelope.get("req_info", ""), api_key)
            fact = parse_api_v2_refund_notification(decrypted)
        except PaymentGatewayError:
            raise CallbackFailureError(400, "invalid_refund_notification") from None
        resource_id = fact.out_refund_no

    return VerifiedCallback(
        kind=kind,
        event_id=event_id,
        event_type=kind,
        resource_id=resource_id,
        resource_json=_callback_storage_payload(
            kind,
            fact,
            api_key=api_key,
            resource_id=resource_id,
            verified_digest=digest,
        ),
        verified_digest=digest,
        fact=fact,
    )


async def validate_callback_fact(db: AsyncSession, callback: VerifiedCallback) -> None:
    """Reject signed/decrypted facts that do not match an existing local payment/refund."""
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

        if not get_settings().mall_gateway_callback_enabled:
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
                stored_payload = _json_object(
                    event.payload_ciphertext or b"", code="invalid_stored_callback_fact"
                )
                fact_data = _verify_stored_callback_fact(
                    event, stored_payload, get_settings().mall_wechat_api_v2_key
                )
                if event.event_type == "payment":
                    fact = parse_api_v2_payment_fact(fact_data)
                    payment = await db.scalar(
                        select(MallPayment).where(MallPayment.out_trade_no == event.resource_id)
                    )
                    if payment is None:
                        raise RuntimeError("callback payment missing")
                    await apply_verified_payment(
                        db, payment.id, fact, payer_identity_verified=True
                    )
                elif event.event_type == "refund":
                    fact = parse_api_v2_refund_notification(fact_data)
                    refund = await db.scalar(
                        select(MallRefund).where(MallRefund.out_refund_no == event.resource_id)
                    )
                    if refund is None:
                        raise RuntimeError("callback refund missing")
                    if refund.status == "succeeded" and fact.status in {"CLOSED", "ABNORMAL"}:
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
