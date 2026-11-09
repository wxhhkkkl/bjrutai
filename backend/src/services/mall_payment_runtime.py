"""Explicitly configured production adapter; test mode never opens real funds."""

from ..core.config import get_settings
from ..integrations.wechat_pay_client import WechatPayClient
from ..integrations.wechat_pay_types import PaymentGatewayError
from .mall_prepay_service import PrepayVault


def wechat_gateway_client(payment):
    settings = get_settings()
    if settings.mall_gateway_mode != "live" or not settings.mall_gateway_outbound_enabled:
        raise PaymentGatewayError("payment_outbound_disabled")
    if (payment.appid_snapshot, payment.mchid_snapshot) != (
        settings.wechat_app_id,
        settings.mall_wechat_mchid,
    ):
        raise PaymentGatewayError("payment_configuration_changed")
    try:
        gateway = WechatPayClient(
            appid=payment.appid_snapshot,
            mchid=payment.mchid_snapshot,
            merchant_serial=settings.mall_wechat_merchant_serial,
            private_key_pem=settings.mall_wechat_private_key_pem,
            verify_keys=settings.mall_wechat_verify_keys,
            outbound_enabled=True,
            timeout_seconds=8,
        )
    except (ValueError, TypeError):
        raise PaymentGatewayError("payment_configuration_unavailable") from None
    return gateway


def payment_runtime(payment):
    settings = get_settings()
    gateway = wechat_gateway_client(payment)
    try:
        vault = PrepayVault(settings.mall_prepay_keys, settings.mall_prepay_active_key)
    except (ValueError, TypeError):
        raise PaymentGatewayError("payment_configuration_unavailable") from None
    return gateway, vault


def payment_handlers(sessions):
    from .mall_payment_execution_service import MallPaymentExecutor

    settings = get_settings()
    if settings.mall_gateway_mode != "live" or not settings.mall_gateway_outbound_enabled:
        return {}

    async def handler(item):
        # Validate money configuration within its own leased job. A bad key must
        # not prevent independent, never-attempted orders from expiring locally.
        vault = PrepayVault(settings.mall_prepay_keys, settings.mall_prepay_active_key)
        executor = MallPaymentExecutor(
            sessions,
            lambda payment: payment_runtime(payment)[0],
            vault,
            settings.mall_wechat_notify_url,
        )
        return await executor(item)

    return {
        "mall_payment_create": handler,
        "mall_payment_query": handler,
        "mall_order_close": handler,
    }
