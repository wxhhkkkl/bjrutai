"""Lease-fenced payment execution. Every external call follows a committed unknown state."""

from datetime import timedelta

from sqlalchemy import select

from ..integrations.wechat_pay_types import PaymentGatewayError, PaymentNotFoundError, PrepayResult
from ..models.mall_base import utc_now
from ..models.mall_finance import MallPayment
from ..models.user import User
from ..tasks.mall_tasks import MallJobContinuation
from .mall_funds_state import clear_funds_unknown, mark_funds_unknown
from .mall_job_service import locked_mall_lease
from .mall_payment_facts_service import (
    apply_verified_close,
    apply_verified_payment,
    locked_payment,
)


class MallPaymentExecutor:
    def __init__(self, sessions, gateway_factory, vault, notify_url):
        self.sessions, self.gateway_factory = sessions, gateway_factory
        self.vault, self.notify_url = vault, notify_url

    async def __call__(self, item):
        if (item.kind, item.entity_type) not in {
            ("mall_payment_create", "mall_payment"),
            ("mall_payment_query", "mall_payment"),
            ("mall_order_close", "mall_order"),
        }:
            raise PaymentGatewayError("invalid_payment_work")
        async with self.sessions() as db:
            order, payment = await self._locked(db, item)
            if not await locked_mall_lease(db, item):
                return
            if payment.status in {"succeeded", "closed"}:
                await self._paid_close(db, item, order)
                await db.commit()
                return
            gateway = self.gateway_factory(payment)
            if (gateway.appid, gateway.mchid) != (payment.appid_snapshot, payment.mchid_snapshot):
                raise PaymentGatewayError("payment_configuration_changed")
            buyer = await db.get(User, order.buyer_user_id)
            if item.kind != "mall_payment_query" and (not buyer or not buyer.openid):
                raise PaymentGatewayError("payment_payer_unavailable")
            action = (
                "prepay"
                if (
                    item.kind == "mall_payment_create"
                    and payment.status == "creating"
                    and payment.expires_at > utc_now()
                    and order.status == "pending_payment"
                    and not order.paid_amount_cent
                    and not order.close_requested_at
                )
                else "query"
            )
            request = dict(
                out_trade_no=payment.out_trade_no,
                amount_cent=payment.amount_cent,
                openid=buyer.openid if buyer else None,
                expires_at=payment.expires_at,
                notify_url=self.notify_url,
            )
            # Close the transaction before any I/O, even a query. A crash leaves
            # the original request identity in unknown, never a new payment.
            mark_funds_unknown(payment)
            payment.status, payment.last_error_code = "unknown", "payment_confirmation_pending"
            payment.version += 1
            await db.commit()

        if action == "prepay":
            result = await gateway.prepay(**request)
            return await self._save_prepay(item, result)
        try:
            fact = await gateway.query(request["out_trade_no"])
        except PaymentNotFoundError:
            if item.kind == "mall_payment_query":
                return await self._record_query_absence(item)
            return await self._retry_absent(item, gateway, request)
        async with self.sessions() as db:
            order, payment = await self._locked(db, item)
            if not await locked_mall_lease(db, item):
                return
            await apply_verified_payment(db, payment.id, fact)
            if payment.status in {"succeeded", "closed"}:
                await self._paid_close(db, item, order)
                await db.commit()
                return
            if item.kind == "mall_payment_query":
                await db.commit()
                return
            if fact.state not in {"NOTPAY", "USERPAYING"}:
                # Roll back the ambiguous fact; bounded worker failures eventually
                # form a manual work item, without releasing any reservation.
                raise PaymentGatewayError("payment_requires_reconciliation")
            expired = (
                payment.expires_at <= utc_now()
                or order.status == "closed"
                or order.close_requested_at is not None
            )
            if fact.state == "USERPAYING" and payment.expires_at < utc_now() - timedelta(
                minutes=15
            ):
                raise PaymentGatewayError("payment_requires_reconciliation")
            action = "close" if expired and fact.state == "NOTPAY" else None
            if not expired and fact.state == "NOTPAY" and not payment.prepay_ciphertext:
                action = "prepay"
            if action:
                payment.status, payment.last_error_code = "unknown", "payment_confirmation_pending"
                payment.version += 1
            await db.commit()
        if action == "close":
            result = await gateway.close(request["out_trade_no"])
            async with self.sessions() as db:
                order, payment = await self._locked(db, item)
                if not await locked_mall_lease(db, item):
                    return
                await apply_verified_close(db, payment.id, result)
                await self._paid_close(db, item, order)
                await db.commit()
            return
        if action == "prepay":
            result = await gateway.prepay(**request)
            return await self._save_prepay(item, result)
        return MallJobContinuation()

    async def _record_query_absence(self, item):
        """A signed not-found query is evidence of absence, never permission to prepay."""
        async with self.sessions() as db:
            _order, payment = await self._locked(db, item)
            if not await locked_mall_lease(db, item):
                return
            if payment.status not in {"succeeded", "closed"}:
                observed_at = utc_now()
                mark_funds_unknown(payment, now=observed_at)
                payment.last_query_at = observed_at
                payment.last_error_code = "verified_payment_absent"
                payment.version += 1
            await db.commit()
        return None

    async def _retry_absent(self, item, gateway, request):
        async with self.sessions() as db:
            order, payment = await self._locked(db, item)
            if not await locked_mall_lease(db, item):
                return
            if payment.status in {"succeeded", "closed"}:
                return
            if (
                order.status != "pending_payment"
                or order.paid_amount_cent
                or min(payment.expires_at, order.expires_at) <= utc_now()
                or order.close_requested_at
            ):
                # Absence cannot prove a previous in-flight request is closed.
                raise PaymentGatewayError("absent_payment_requires_reconciliation")
            payment.prepay_ciphertext = None
            mark_funds_unknown(payment)
            payment.version += 1
            await db.commit()
        return await self._save_prepay(item, await gateway.prepay(**request))

    async def _save_prepay(self, item, result):
        if not isinstance(result, PrepayResult):
            raise PaymentGatewayError("invalid_prepay_response")
        async with self.sessions() as db:
            order, payment = await self._locked(db, item)
            if not await locked_mall_lease(db, item):
                return
            if (
                payment.status in {"succeeded", "closed"}
                or order.status != "pending_payment"
                or order.close_requested_at
            ):
                return
            payment.prepay_ciphertext = self.vault.seal(payment, result.prepay_id)
            clear_funds_unknown(payment)
            payment.status, payment.last_error_code = "pending", None
            payment.version += 1
            await db.commit()
        return MallJobContinuation()

    async def _locked(self, db, item):
        identity = item.entity_id
        if item.kind == "mall_order_close":
            ids = (
                await db.scalars(select(MallPayment.id).where(MallPayment.order_id == identity))
            ).all()
            if len(ids) != 1:
                raise PaymentGatewayError("ambiguous_payment_history")
            identity = ids[0]
        order, payment = await locked_payment(db, identity)
        if item.kind == "mall_order_close" and not order.close_requested_at:
            raise PaymentGatewayError("close_intent_missing")
        return order, payment

    async def _paid_close(self, db, item, order):
        if item.kind == "mall_order_close" and order.paid_amount_cent:
            job = await locked_mall_lease(db, item)
            if job:
                job.status, job.last_error_code = "manual", "close_found_paid_order"
                job.lease_owner = job.lease_until = None
