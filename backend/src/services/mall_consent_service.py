"""Versioned mall purpose notices and explicit user acknowledgement evidence.

These records describe a buyer's affirmative action for a specific mall purpose.
They are not a substitute for legal agreements and never grant data-delivery
permissions or override the G-DATA gate.
"""

from ..core.exceptions import ConflictException, ForbiddenException, ValidationException
from ..models.consent import ConsentRecord, ConsentScene, EvidenceType, SubjectType

MALL_NOTICE_COPY_VERSION = "mall-purpose-2026-11-v1"

PURPOSE_SCENES = {
    "recipient": ConsentScene.MALL_ADDRESS,
    "payment": ConsentScene.MALL_CHECKOUT,
    "fulfillment": ConsentScene.MALL_CHECKOUT,
    "invoice": ConsentScene.MALL_INVOICE,
}

PURPOSE_SCOPE_KEYS = {
    "recipient": {"recipient_name", "recipient_phone", "recipient_region", "delivery_address"},
    "payment": {"order_amount", "payment_status", "channel_transaction_reference"},
    "fulfillment": {"recipient_contact", "delivery_address", "courier_tracking", "delivery_status"},
    "invoice": {"invoice_title", "tax_identifier", "delivery_email", "tax_record"},
}

MALL_PURPOSE_NOTICE_DRAFTS = {
    "recipient": {
        "title": "商城收件资料用途说明",
        "body": (
            "收件人姓名、联系电话、收货地区和详细地址用于保存收货地址、完成订单配送，"
            "以及处理与该订单直接相关的履约和售后事项。"
            "为配送所必需的信息会提供给实际承运方。"
            "地址可在商城中维护；已生成的订单地址快照按交易及法定留存要求保留。"
        ),
    },
    "payment": {
        "title": "商城支付信息用途说明",
        "body": (
            "订单金额、订单编号和支付状态用于创建支付请求、核对实际收款、处理退款及订单争议。"
            "支付由微信支付等实际支付渠道处理；商城仅保存完成交易核对所需的支付标识和结果，"
            "不保存支付密码。"
        ),
    },
    "fulfillment": {
        "title": "商城订单履约用途说明",
        "body": (
            "订单商品、收件资料、发货状态、承运方和运单号用于出库、查询物流、确认送达及处理售后。"
            "物流查询服务仅按查询所需接收承运方和运单号；不用于营销画像。"
        ),
    },
    "invoice": {
        "title": "商城发票资料用途说明",
        "body": (
            "发票抬头、企业税号和选填邮箱用于核验交易、办理真实交易发票、交付电子票据，"
            "以及处理票据更正或红冲。税号仅在企业抬头时收集；邮箱仅在填写后用于电子票交付。"
            "开票申请、邮箱通知和实际出票分别记录。申请撤回后，"
            "依法必须留存的交易与财税记录仍按适用期限保存。"
        ),
    },
}


def get_mall_purpose_notice_drafts():
    """Return copy drafts; publishing them still requires business/legal review."""
    return {
        "copyVersion": MALL_NOTICE_COPY_VERSION,
        "reviewStatus": "draft",
        "reviewRequired": True,
        "items": [
            {"purpose": purpose, **notice}
            for purpose, notice in MALL_PURPOSE_NOTICE_DRAFTS.items()
        ],
    }


async def record_mall_notice_acknowledgement(
    db,
    actor,
    *,
    purposes,
    version: str,
    current_version: str,
    confirmed: bool,
    scope_keys=(),
):
    """Append immutable evidence for an explicit, purpose-limited buyer action."""
    if getattr(actor, "actor_type", None) != "user":
        raise ForbiddenException(message="仅买家本人可确认商城用途告知")
    if confirmed is not True:
        raise ValidationException(message="请先阅读并确认本次商城资料用途")
    if not isinstance(version, str) or not version.strip() or version != current_version:
        raise ConflictException(message="商城用途告知版本已变化，请刷新后重新确认")

    selected = tuple(sorted(set(purposes)))
    if not selected or any(purpose not in PURPOSE_SCENES for purpose in selected):
        raise ValidationException(message="商城用途告知范围不合法")
    scenes = {PURPOSE_SCENES[purpose] for purpose in selected}
    if len(scenes) != 1:
        raise ValidationException(message="不同业务场景的用途告知必须分别确认")
    scene = next(iter(scenes))
    if scene == ConsentScene.MALL_ADDRESS and set(selected) != {"recipient"}:
        raise ValidationException(message="收件资料用途必须单独确认")
    if scene == ConsentScene.MALL_CHECKOUT and set(selected) != {"payment", "fulfillment"}:
        raise ValidationException(message="支付和履约用途须与订单确认动作一致")
    if scene == ConsentScene.MALL_INVOICE and set(selected) != {"invoice"}:
        raise ValidationException(message="发票资料用途必须单独确认")

    selected_scopes = set(scope_keys)
    allowed_scopes = set().union(*(PURPOSE_SCOPE_KEYS[purpose] for purpose in selected))
    if not selected_scopes <= allowed_scopes:
        raise ValidationException(message="商城用途告知范围包含未声明资料")

    record = ConsentRecord(
        user_id=actor.actor_id,
        subject_type=SubjectType.USER,
        scene=scene,
        agreement_versions={
            "mall_policy": version,
            **{f"mall_{purpose}_notice": version for purpose in selected},
            "mall_notice_copy": MALL_NOTICE_COPY_VERSION,
        },
        scopes={
            **{f"mall_{purpose}": True for purpose in selected},
            **({"mall_address": True} if "recipient" in selected else {}),
            **({"mall_order": True} if "payment" in selected else {}),
            **{scope: True for scope in sorted(selected_scopes)},
        },
        confirmed=True,
        evidence_type=EvidenceType.CLICK,
        status="active",
    )
    db.add(record)
    await db.flush()
    return record
