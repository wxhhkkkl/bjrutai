"""Refund handlers for the live gateway and an isolated local simulator."""

from ..core.config import get_settings
from ..integrations.wechat_pay_types import RefundFact
from ..models.mall_base import utc_now
from .mall_payment_runtime import wechat_gateway_client


class LocalRefundSimulator:
    """Return a deterministic synthetic success without contacting a provider."""

    def __init__(self, sessions, payment):
        self.sessions = sessions
        self.payment = payment

    async def query_refund(self, out_refund_no):
        from sqlalchemy import select

        from ..models.mall_finance import MallRefund

        async with self.sessions() as db:
            refund = await db.scalar(
                select(MallRefund).where(MallRefund.out_refund_no == out_refund_no)
            )
        if refund is None:
            from ..integrations.wechat_pay_types import RefundNotFoundError

            raise RefundNotFoundError()
        return RefundFact(
            out_refund_no=refund.out_refund_no,
            out_trade_no=self.payment.out_trade_no,
            status="SUCCESS",
            total_cent=refund.original_amount_cent,
            refund_cent=refund.total_cent,
            currency="CNY",
            transaction_id=self.payment.channel_transaction_id,
            channel_refund_id=f"LOCAL-SIM-{refund.out_refund_no}",
            success_at=utc_now(),
        )


def refund_handlers(sessions):
    from .mall_refund_service import MallRefundExecutor, MallRefundQueryExecutor

    settings = get_settings()
    if (
        settings.mall_refund_simulation_enabled
        and settings.app_environment in {"development", "test"}
        and settings.mall_gateway_mode == "test"
        and not settings.mall_gateway_outbound_enabled
    ):
        def simulator(payment):
            return LocalRefundSimulator(sessions, payment)

        async def handler(item):
            return await MallRefundExecutor(sessions, simulator)(item)

        async def query_handler(item):
            return await MallRefundQueryExecutor(sessions, simulator)(item)

        return {"mall_refund_execute": handler, "mall_refund_query": query_handler}

    if settings.mall_gateway_mode != "live" or not settings.mall_gateway_outbound_enabled:
        return {}

    async def handler(item):
        executor = MallRefundExecutor(sessions, wechat_gateway_client)
        return await executor(item)

    async def query_handler(item):
        executor = MallRefundQueryExecutor(sessions, wechat_gateway_client)
        return await executor(item)

    return {"mall_refund_execute": handler, "mall_refund_query": query_handler}
