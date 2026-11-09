"""Financial projections never turn payment attempts into settled money."""

import pytest

from src.api.mall_deps import MallActor
from tests.unit.test_mall_payment_service import payable


@pytest.mark.asyncio
async def test_payment_list_is_permission_scoped_and_uses_successful_refunds_only(
    db_session, monkeypatch
):
    _, order, _, payment = await payable(db_session, monkeypatch)
    payment.status = "unknown"
    payment.last_error_code = "gateway_timeout"
    reader = MallActor("admin", 901, frozenset({"mall.payments.read"}))

    from src.services.mall_finance_query_service import list_admin_payments

    page = await list_admin_payments(db_session, reader, page_size=20)
    row = next(item for item in page["items"] if item["id"] == str(payment.id))
    assert row["orderId"] == str(order.id)
    assert row["orderNo"] == order.order_no
    assert row["status"] == "unknown"
    assert row["refundSucceededCent"] == 0
    assert row["netReceivedCent"] is None
    assert row["confirmedAt"] is None
    assert "prepayCiphertext" not in row and "openId" not in row


@pytest.mark.asyncio
async def test_payment_detail_exposes_channel_transaction_identity_but_not_prepay_secret(
    db_session, monkeypatch
):
    _, _, _, payment = await payable(db_session, monkeypatch)
    payment.status = "succeeded"
    payment.channel_transaction_id = "synthetic-transaction-001"
    payment.confirmed_at = payment.created_at
    reader = MallActor("admin", 902, frozenset({"mall.payments.read"}))

    from src.services.mall_finance_query_service import get_admin_payment

    row = await get_admin_payment(db_session, reader, payment.id)
    assert row["channelTransactionId"] == "synthetic-transaction-001"
    assert row["netReceivedCent"] == payment.amount_cent
    assert "prepayCiphertext" not in row and "appidSnapshot" not in row
