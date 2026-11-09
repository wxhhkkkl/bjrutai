"""Independent InnoDB sessions verify the shared single-shipment cooldown."""

import asyncio
from datetime import datetime
from uuid import uuid4

from sqlalchemy import func, select

from src.api.mall_deps import MallActor
from src.integrations.wechat_pay_types import PaymentFact
from src.models.mall_operations import MallJob
from src.models.mall_trade import MallOrder, MallShipment
from src.models.user import User
from src.schemas.mall_catalog import VersionAction
from src.schemas.mall_fulfillment import ShipmentCreate
from src.services.mall_logistics_service import refresh_logistics
from src.services.mall_payment_service import apply_verified_payment, prepare_payment
from src.services.mall_shipment_service import ship_order
from tests.contract.test_admin_mall_orders import admin
from tests.mysql.test_mall_reliability_order_actions import defer_this_cases_payment_double
from tests.mysql.test_mall_reliability_payments import enable, local_order


async def test_two_admins_share_one_shipment_query_and_30_minute_cooldown(
    mall_mysql_sessions, monkeypatch
):
    enable(monkeypatch)
    buyer, order_id, order_version = await local_order(mall_mysql_sessions)
    async with mall_mysql_sessions() as db:
        payment = await prepare_payment(
            db,
            buyer,
            order_id,
            VersionAction(expectedVersion=order_version),
            key="mysql-logistics-payment-" + uuid4().hex,
        )
        await apply_verified_payment(
            db,
            payment.id,
            PaymentFact(
                "wx-test",
                "test-merchant",
                payment.out_trade_no,
                "SUCCESS",
                payment.amount_cent,
                "CNY",
                "mysql-logistics-txn-" + uuid4().hex,
                datetime(2026, 11, 4),
                payment.amount_cent,
                (await db.get(User, buyer.actor_id)).openid,
            ),
        )
        await db.commit()
        await defer_this_cases_payment_double(db, order_id)
        order = await db.get(MallOrder, order_id)
        order_version = order.version

    async with mall_mysql_sessions() as db:
        staff_id, _, _ = await admin(db, ["mall.shipments.write"])
        shipper = MallActor("admin", staff_id, frozenset({"mall.shipments.write"}))
        shipment = await ship_order(
            db,
            shipper,
            order_id,
            ShipmentCreate(
                expectedVersion=order_version,
                courierCode="yuantong",
                trackingNo="YT202611060089",
            ),
            key="mysql-logistics-ship-" + uuid4().hex,
        )
        shipment_id, shipment_version = shipment.id, shipment.version
        await db.commit()

    async def staff_actor():
        async with mall_mysql_sessions() as db:
            identity, _, _ = await admin(db, ["mall.shipments.write"])
            return MallActor("admin", identity, frozenset({"mall.shipments.write"}))

    actors = await asyncio.gather(staff_actor(), staff_actor())

    async def refresh(actor):
        async with mall_mysql_sessions() as db:
            result = await refresh_logistics(
                db,
                actor,
                shipment_id,
                VersionAction(expectedVersion=shipment_version),
                key="mysql-logistics-refresh-" + str(actor.actor_id),
            )
            await db.commit()
            return result

    results = await asyncio.wait_for(
        asyncio.gather(*(refresh(actor) for actor in actors)), timeout=25
    )
    assert sorted(result["scheduled"] for result in results) == [False, True]
    async with mall_mysql_sessions() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(MallJob)
                .where(
                    MallJob.kind == "mall_logistics_query",
                    MallJob.entity_id == shipment_id,
                )
            )
            == 1
        )
        # The later migration round-trip must run against rows without the
        # guarded 029 deadline field, so clear only this test's owned fixture.
        shipment = await db.get(MallShipment, shipment_id)
        shipment.auto_receive_at = None
        await db.commit()
