"""Internal verified facts, never input contracts for a public API."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


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


def _api_v2_int(data, key, *, minimum=0, maximum=9007199254740991):
    value = data[key]
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal():
        raise ValueError()
    parsed = int(value)
    if not minimum <= parsed <= maximum:
        raise ValueError()
    return parsed


def _api_v2_text(data, key, limit=128, *, optional=False):
    value = data.get(key) if optional else data[key]
    if optional and (value is None or value == ""):
        return None
    if not isinstance(value, str) or not 0 < len(value) <= limit:
        raise ValueError()
    return value


def _wechat_local_time(value):
    parsed = datetime.strptime(value, "%Y%m%d%H%M%S")
    return parsed.replace(tzinfo=ZoneInfo("Asia/Shanghai")).astimezone(timezone.utc).replace(
        tzinfo=None
    )


def parse_api_v2_payment_fact(data):
    """Normalize a signed APIv2 query or payment notification into a payment fact."""
    try:
        state = _api_v2_text(data, "trade_state", 20, optional=True)
        if state is None:
            state = "SUCCESS" if data.get("result_code") == "SUCCESS" else "PAYERROR"
        if state == "ACCEPT":
            state = "USERPAYING"
        if state not in {
            "SUCCESS",
            "REFUND",
            "NOTPAY",
            "CLOSED",
            "REVOKED",
            "USERPAYING",
            "PAYERROR",
        }:
            raise ValueError()
        total = _api_v2_int(data, "total_fee", minimum=1)
        payer_total = (
            _api_v2_int(data, "cash_fee", minimum=0)
            if data.get("cash_fee") not in (None, "")
            else None
        )
        currency = data.get("fee_type") or "CNY"
        if currency != "CNY" or (data.get("cash_fee_type") or "CNY") != "CNY":
            raise ValueError()
        transaction_id = _api_v2_text(data, "transaction_id", optional=True)
        openid = _api_v2_text(data, "openid", 128, optional=True)
        paid_at = None
        if state == "SUCCESS":
            transaction_id = _api_v2_text(data, "transaction_id", 64)
            paid_at = _wechat_local_time(_api_v2_text(data, "time_end", 14))
            if payer_total is None or payer_total <= 0:
                raise ValueError()
        return PaymentFact(
            appid=_api_v2_text(data, "appid", 32),
            mchid=_api_v2_text(data, "mch_id", 32),
            out_trade_no=_api_v2_text(data, "out_trade_no", 32),
            state=state,
            total_cent=total,
            currency=currency,
            transaction_id=transaction_id,
            paid_at=paid_at,
            payer_total_cent=payer_total,
            openid=openid,
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        raise PaymentGatewayError("invalid_transaction_response") from None


def parse_api_v2_refund_fact(data, out_refund_no):
    """Find and normalize one refund in an APIv2 refund-query response."""
    try:
        if not isinstance(out_refund_no, str) or not 0 < len(out_refund_no) <= 64:
            raise ValueError()
        count = _api_v2_int(data, "refund_count", minimum=1, maximum=100)
        index = None
        for candidate in range(count):
            if data.get(f"out_refund_no_{candidate}") == out_refund_no:
                index = candidate
                break
        if index is None:
            raise ValueError()
        raw_status = _api_v2_text(data, f"refund_status_{index}", 20)
        statuses = {
            "SUCCESS": "SUCCESS",
            "REFUNDCLOSE": "CLOSED",
            "PROCESSING": "PROCESSING",
            "CHANGE": "ABNORMAL",
        }
        status = statuses[raw_status]
        success_at = None
        if status == "SUCCESS":
            raw_time = _api_v2_text(data, f"refund_success_time_{index}", 20)
            local_time = datetime.strptime(raw_time, "%Y-%m-%d %H:%M:%S")
            success_at = local_time.replace(tzinfo=ZoneInfo("Asia/Shanghai")).astimezone(
                timezone.utc
            ).replace(tzinfo=None)
        return RefundFact(
            out_refund_no=out_refund_no,
            out_trade_no=_api_v2_text(data, "out_trade_no", 32),
            status=status,
            total_cent=_api_v2_int(data, "total_fee", minimum=1),
            refund_cent=_api_v2_int(data, f"refund_fee_{index}", minimum=1),
            currency=data.get("fee_type") or "CNY",
            transaction_id=_api_v2_text(data, "transaction_id", 64),
            channel_refund_id=_api_v2_text(data, f"refund_id_{index}", 64),
            success_at=success_at,
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        raise PaymentGatewayError("invalid_refund_response") from None


def parse_api_v2_refund_notification(data):
    """Normalize the decrypted `req_info` payload from a V2 refund callback."""
    try:
        raw_status = _api_v2_text(data, "refund_status", 20)
        statuses = {
            "SUCCESS": "SUCCESS",
            "REFUNDCLOSE": "CLOSED",
            "CHANGE": "ABNORMAL",
        }
        status = statuses[raw_status]
        success_at = None
        if status == "SUCCESS":
            raw_time = _api_v2_text(data, "success_time", 20)
            local_time = datetime.strptime(raw_time, "%Y-%m-%d %H:%M:%S")
            success_at = local_time.replace(tzinfo=ZoneInfo("Asia/Shanghai")).astimezone(
                timezone.utc
            ).replace(tzinfo=None)
        return RefundFact(
            out_refund_no=_api_v2_text(data, "out_refund_no", 64),
            out_trade_no=_api_v2_text(data, "out_trade_no", 32),
            status=status,
            total_cent=_api_v2_int(data, "total_fee", minimum=1),
            refund_cent=_api_v2_int(data, "refund_fee", minimum=1),
            currency="CNY",
            transaction_id=_api_v2_text(data, "transaction_id", 64),
            channel_refund_id=_api_v2_text(data, "refund_id", 64),
            success_at=success_at,
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        raise PaymentGatewayError("invalid_refund_response") from None
