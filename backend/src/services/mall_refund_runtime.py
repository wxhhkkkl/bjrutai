"""Production refund worker registration is gated with the existing payment switch."""

from ..core.config import get_settings
from .mall_payment_runtime import wechat_gateway_client


def refund_handlers(sessions):
    from .mall_refund_service import MallRefundExecutor, MallRefundQueryExecutor

    settings = get_settings()
    if settings.mall_gateway_mode != "live" or not settings.mall_gateway_outbound_enabled:
        return {}

    async def handler(item):
        executor = MallRefundExecutor(sessions, wechat_gateway_client)
        return await executor(item)

    async def query_handler(item):
        executor = MallRefundQueryExecutor(sessions, wechat_gateway_client)
        return await executor(item)

    return {"mall_refund_execute": handler, "mall_refund_query": query_handler}
