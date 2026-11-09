from datetime import datetime

import pytest
from sqlalchemy import select


@pytest.mark.parametrize("refunded,expected", [(0, 10000), (1, 10000), (9999, 10000), (10000, 0)])
def test_partial_refund_keeps_original_goods_base(refunded, expected):
    from src.services.mall_consumption_service import performance_base

    assert performance_base(10000, refunded) == expected


@pytest.mark.parametrize("original,refunded", [(-1, 0), (100, 101), (100, -1), (True, 0)])
def test_refund_base_rejects_impossible_values(original, refunded):
    from src.services.mall_consumption_service import performance_base

    with pytest.raises(ValueError):
        performance_base(original, refunded)


@pytest.mark.asyncio
async def test_payment_month_is_beijing_month_and_old_frozen_results_untouched(
    db_session, monkeypatch
):
    from src.models.mall_consumption import MallConsumption
    from src.models.mall_operations import MallJob
    from src.models.performance_settlement import PerformanceSettlement, SettlementStatus
    from src.services.mall_payment_service import apply_verified_payment
    from tests.unit.test_mall_payment_service import payable, success

    _, order, _, payment = await payable(db_session, monkeypatch)
    frozen = PerformanceSettlement(period="2026-11", status=SettlementStatus.REVIEWED)
    db_session.add(frozen)
    await db_session.flush()
    await apply_verified_payment(
        db_session, payment.id, success(payment, order, paid_at=datetime(2026, 10, 31, 16, 0))
    )
    source = (await db_session.scalars(select(MallConsumption))).one()
    assert source.business_period == "2026-11" and source.paid_at == datetime(2026, 10, 31, 16, 0)
    assert frozen.status == SettlementStatus.REVIEWED
    job = (
        await db_session.scalars(
            select(MallJob).where(MallJob.kind == "mall_consumption_frozen_source")
        )
    ).one()
    assert job.status == "manual"


@pytest.mark.asyncio
@pytest.mark.parametrize("link", ["authorized", "phone_only", "late", "disabled"])
async def test_attribution_uses_existing_authorized_link_and_never_shipping_phone(
    db_session, monkeypatch, link
):
    from src.models.mall_consumption import MallConsumption
    from src.models.user import ActivationStatus, User
    from src.services.mall_payment_service import apply_verified_payment
    from tests.conftest import seed_bound_customer_with_attribution
    from tests.unit.test_mall_payment_service import payable, success

    actor, order, _, payment = await payable(db_session, monkeypatch)
    bound = await seed_bound_customer_with_attribution(db_session, customer_phone="13800001234")
    customer, distributor = bound["customer"], bound["distributor"]
    customer.bound_at = datetime(2026, 10, 1)
    if link != "phone_only":
        customer.user_id = actor.actor_id
    if link == "late":
        customer.bound_at = datetime(2026, 11, 5)
    if link == "disabled":
        (await db_session.get(User, distributor.user_id)).activation_status = (
            ActivationStatus.DISABLED
        )
    await db_session.flush()
    await apply_verified_payment(db_session, payment.id, success(payment, order))
    source = (await db_session.scalars(select(MallConsumption))).one()
    if link == "authorized":
        assert (
            source.customer_id == customer.id and source.attributed_distributor_id == distributor.id
        )
        assert source.trade_org_id == bound["org"].id
        customer.distributor_id = None
        await db_session.flush()
        await apply_verified_payment(db_session, payment.id, success(payment, order))
        assert source.attributed_distributor_id == distributor.id
    else:
        assert source.status == "unassigned" and source.attributed_distributor_id is None
