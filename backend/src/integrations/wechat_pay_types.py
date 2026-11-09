"""Internal verified facts, never input contracts for a public API."""

from dataclasses import dataclass, field
from datetime import datetime, timezone


class PaymentGatewayError(Exception):
    def __init__(self, code="gateway_unavailable"):
        self.code = code
        super().__init__(code)


class PaymentNotFoundError(PaymentGatewayError):
    """Only the signed query response may establish absence; never a close fact."""

    def __init__(self):
        super().__init__("verified_payment_absent")


class RefundNotFoundError(PaymentGatewayError):
    """Only the signed refund query response may establish absence."""

    def __init__(self):
        super().__init__("verified_refund_absent")


@dataclass(frozen=True)
class PrepayResult:
    prepay_id: str = field(repr=False)


@dataclass(frozen=True)
class VerifiedClose:
    out_trade_no: str
    mchid: str


@dataclass(frozen=True)
class PaymentFact:
    appid: str
    mchid: str
    out_trade_no: str
    state: str
    total_cent: int
    currency: str
    transaction_id: str | None = None
    paid_at: datetime | None = None
    payer_total_cent: int | None = None
    openid: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class RefundFact:
    out_refund_no: str
    out_trade_no: str
    status: str
    total_cent: int
    refund_cent: int
    currency: str
    transaction_id: str | None = None
    channel_refund_id: str | None = None
    success_at: datetime | None = None


def parse_payment_fact(data):
    try:

        def text(name, limit=64):
            value = data[name]
            if not isinstance(value, str) or not 0 < len(value) <= limit:
                raise ValueError()
            return value

        amount = data["amount"]
        total = amount["total"]
        payer_total = amount.get("payer_total")
        state = text("trade_state", 20)
        if (
            type(total) is not int
            or not 0 < total <= 9007199254740991
            or amount["currency"] != "CNY"
            or amount.get("payer_currency", "CNY") != "CNY"
            or (payer_total is not None and (type(payer_total) is not int or payer_total < 0))
            or state
            not in {"SUCCESS", "REFUND", "NOTPAY", "CLOSED", "REVOKED", "USERPAYING", "PAYERROR"}
        ):
            raise ValueError()
        transaction_id, paid_at = data.get("transaction_id"), None
        if state == "SUCCESS":
            transaction_id = text("transaction_id")
            parsed = datetime.fromisoformat(data["success_time"].replace("Z", "+00:00"))
            if parsed.tzinfo is None or payer_total is None:
                raise ValueError()
            paid_at = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        openid = data.get("payer", {}).get("openid")
        if openid is not None and (not isinstance(openid, str) or not 0 < len(openid) <= 128):
            raise ValueError()
        return PaymentFact(
            text("appid"),
            text("mchid"),
            text("out_trade_no", 32),
            state,
            total,
            "CNY",
            transaction_id,
            paid_at,
            payer_total,
            openid,
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        raise PaymentGatewayError("invalid_transaction_response") from None


def parse_refund_fact(data):
    """Parse the minimal APIv3 refund identity, status and amount evidence."""
    try:

        def text(name, limit=64):
            value = data[name]
            if not isinstance(value, str) or not 0 < len(value) <= limit:
                raise ValueError()
            return value

        amount = data["amount"]
        total, refund = amount["total"], amount["refund"]
        currency = amount["currency"]
        status = text("status", 20)
        if (
            status not in {"SUCCESS", "CLOSED", "PROCESSING", "ABNORMAL"}
            or type(total) is not int
            or type(refund) is not int
            or not 0 < total <= 9007199254740991
            or not 0 < refund <= total
            or currency != "CNY"
        ):
            raise ValueError()
        transaction_id = data.get("transaction_id")
        channel_refund_id = data.get("refund_id")
        for value in (transaction_id, channel_refund_id):
            if value is not None and (not isinstance(value, str) or not 0 < len(value) <= 64):
                raise ValueError()
        success_at = None
        if status == "SUCCESS":
            parsed = datetime.fromisoformat(data["success_time"].replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError()
            success_at = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return RefundFact(
            text("out_refund_no"),
            text("out_trade_no", 32),
            status,
            total,
            refund,
            currency,
            transaction_id,
            channel_refund_id,
            success_at,
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        raise PaymentGatewayError("invalid_refund_response") from None
