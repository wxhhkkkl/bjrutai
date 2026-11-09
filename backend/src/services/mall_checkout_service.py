"""Five-minute, buyer-bound quotes; no inventory mutation or payment calls."""

import base64
import hashlib
import hmac
import json
from datetime import timedelta, timezone
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select

from ..core.config import get_settings
from ..core.exceptions import ConflictException
from ..models.consent import ConsentRecord
from ..models.mall_base import utc_now
from ..models.mall_catalog import MallSku
from ..models.mall_operations import MallSettings
from ..schemas.mall_checkout import QuoteRequest
from .mall_address_service import audit_address, owned_address, serialize_address
from .mall_cart_service import cart_item_state
from .mall_command_service import canonical_payload_hash
from .mall_settings_service import get_mall_settings, require_mall_purchase_open

MAX_CENT = 9007199254740991
DOMAIN = b"mall-quote-v1."


def _encode(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _signature(payload):
    return hmac.new(
        get_settings().jwt_secret_key.encode(), DOMAIN + payload.encode(), hashlib.sha256
    ).digest()


def _token(actor, body, digest):
    now = utc_now()
    payload = _encode(
        json.dumps(
            {
                "buyer": actor.actor_id,
                "intent": body.model_dump(mode="json"),
                "digest": digest,
                "issued": int(now.replace(tzinfo=timezone.utc).timestamp()),
                "expires": int(
                    (now + timedelta(minutes=5)).replace(tzinfo=timezone.utc).timestamp()
                ),
                "nonce": uuid4().hex,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )
    return payload + "." + _encode(_signature(payload))


def _decode(actor, token):
    try:
        if not isinstance(token, str) or len(token) > 32768:
            raise ValueError()
        payload, signature = token.split(".")
        if not hmac.compare_digest(signature, _encode(_signature(payload))):
            raise ValueError()
        decoded = json.loads(
            base64.b64decode(payload + "=" * (-len(payload) % 4), altchars=b"-_", validate=True)
        )
        now = int(utc_now().replace(tzinfo=timezone.utc).timestamp())
        if (
            actor.actor_type != "user"
            or decoded["buyer"] != actor.actor_id
            or type(decoded["expires"]) is not int
            or type(decoded["issued"]) is not int
            or decoded["expires"] - decoded["issued"] != 300
            or not decoded["issued"] <= now < decoded["expires"]
        ):
            raise ValueError()
        return QuoteRequest(**decoded["intent"]), decoded["digest"]
    except (ValueError, KeyError, TypeError, UnicodeError, ValidationError) as exc:
        raise ConflictException(message="报价已过期或无效，请重新确认") from exc


async def _facts(db, actor, body, *, reserve_stock=False):
    async def current(model, identity, *, write=False):
        return (
            await db.execute(
                select(model)
                .where(model.id == identity)
                .with_for_update(read=not write)
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()

    await get_mall_settings(db)
    # Shared current reads bypass an earlier authentication RR snapshot. This
    # transaction has no network calls and is committed immediately by the API.
    settings = await current(MallSettings, 1)
    require_mall_purchase_open(settings)
    policy = settings.policy_versions.get("policy")
    if not policy:
        raise ConflictException(message="配送售后规则尚未配置")
    address = await owned_address(db, actor, int(body.address_id), lock=True)
    consent = await current(ConsentRecord, address.consent_record_id)
    if (
        consent is None
        or consent.user_id != actor.actor_id
        or not consent.confirmed
        or consent.status != "active"
        or consent.scopes.get("mall_address") is not True
        or (consent.expires_at and consent.expires_at <= utc_now())
    ):
        raise ConflictException(message="收货资料告知已失效，请重新保存地址")
    regions = [address.province_code, address.city_code, address.district_code]
    if set(regions) & set(settings.blocked_regions):
        raise ConflictException(message="当前地区不配送，请选择其他地址")
    lines, versions = [], []
    # Canonical ordering gives the later order writer a fixed SKU lock order.
    for item in sorted(body.items, key=lambda item: int(item.sku_id)):
        sku = await current(MallSku, int(item.sku_id), write=reserve_stock)
        if sku is None:
            raise ConflictException(message="商品规格已失效，请重新确认")
        product, reason = await cart_item_state(db, sku, item.quantity, current=True)
        if reason:
            message = {
                "sku_archived": "商品规格已归档",
                "product_unavailable": "商品已下架",
                "category_disabled": "商品分类已停用",
                "sold_out": "商品已售罄",
                "insufficient_stock": "商品库存不足",
            }[reason]
            raise ConflictException(message=f"{message}，请重新确认")
        amount = sku.sale_price_cent * item.quantity
        if not 0 < amount <= MAX_CENT:
            raise ConflictException(message="商品金额超出范围")
        lines.append(
            {
                "skuId": str(sku.id),
                "productName": product.name,
                "optionsText": " / ".join(f"{k}：{v}" for k, v in sku.options.items()),
                "quantity": item.quantity,
                "unitPriceCent": sku.sale_price_cent,
                "lineAmountCent": amount,
                "skuVersion": sku.version,
            }
        )
        versions.append(
            {
                "sku": sku.id,
                "skuVersion": sku.version,
                "product": product.id,
                "productVersion": product.version,
            }
        )
    goods = sum(line["lineAmountCent"] for line in lines)
    freight = 0 if settings.freight_mode == "free" else settings.freight_cent
    if not 0 < goods + freight <= MAX_CENT:
        raise ConflictException(message="订单金额超出范围")
    # Only this digest goes in the signed token; no recipient or phone is embedded.
    digest = canonical_payload_hash(
        {
            "addressVersion": address.version,
            "address": {
                "recipient": address.recipient_name,
                "phone": address.phone,
                "regions": regions,
                "line": address.address_line,
            },
            "settingsVersion": settings.version,
            "policy": policy,
            "freight": freight,
            "versions": versions,
            "lines": lines,
        }
    )
    audit_address(db, actor, "mall_address_quote", address.id, address.version)
    return {
        "goodsAmountCent": goods,
        "freightAmountCent": freight,
        "payableAmountCent": goods + freight,
        "address": serialize_address(address),
        "policyVersion": policy,
        "changes": [],
        "items": lines,
    }, digest


async def quote_order(db, actor, body):
    result, digest = await _facts(db, actor, body)
    return {
        **result,
        "quoteToken": _token(actor, body, digest),
        "expiresAt": (utc_now() + timedelta(minutes=5)).isoformat() + "Z",
    }


async def validate_quote(db, actor, token, *, reserve_stock=False):
    body, expected = _decode(actor, token)
    result, actual = await _facts(db, actor, body, reserve_stock=reserve_stock)
    if not hmac.compare_digest(expected, actual):
        raise ConflictException(message="报价涉及的价格、地址或规则已变化，请重新确认")
    return body, result
