"""Independent InnoDB sessions test write fencing and current dispatch facts."""

import asyncio
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text

from src.api.mall_deps import MallActor
from src.core.exceptions import ConflictException, ForbiddenException
from src.models.mall_operations import MallCommand
from src.models.mall_trade import MallAftersale, MallOrder
from src.models.role import Role
from src.models.user import User
from src.schemas.mall_catalog import VersionAction
from src.schemas.mall_fulfillment import OrderNote, ShipmentCreate
from src.services.mall_admin_order_service import mutate_admin_order
from src.services.mall_fulfillment_service import check_fulfillment
from src.services.mall_shipment_service import ship_order
from tests.contract.test_admin_mall_orders import admin
from tests.mysql.test_mall_reliability_order_actions import defer_this_cases_payment_double
from tests.mysql.test_mall_reliability_payments import enable, local_order


async def staff(sessions):
    async with sessions() as db:
        identity, role, _ = await admin(db, ["mall.orders.read", "mall.orders.write"])
        return (
            MallActor("admin", identity, frozenset({"mall.orders.read", "mall.orders.write"})),
            role.id,
        )


async def test_old_role_snapshot_cannot_write_after_external_revocation(
    mall_mysql_sessions, monkeypatch
):
    enable(monkeypatch)
    _, identity, version = await local_order(mall_mysql_sessions)
    actor, role_id = await staff(mall_mysql_sessions)
    async with mall_mysql_sessions() as stale:
        await stale.scalar(text("SELECT COUNT(*) FROM roles"))
        async with mall_mysql_sessions() as writer:
            (await writer.get(Role, role_id)).permissions = {"permissions": []}
            await writer.commit()
        with pytest.raises(ForbiddenException):
            await mutate_admin_order(
                stale,
                actor,
                identity,
                OrderNote(expectedVersion=version, internalNote="不应写入"),
                key="mysql-stale-role-note-001",
            )
        await stale.rollback()
    async with mall_mysql_sessions() as db:
        assert (await db.get(MallOrder, identity)).internal_note == ""
        assert (
            await db.scalar(
                select(func.count())
                .select_from(MallCommand)
                .where(MallCommand.actor_type == "admin", MallCommand.actor_id == actor.actor_id)
            )
            == 0
        )


async def test_two_admins_same_version_one_note_wins_and_replays_once(
    mall_mysql_sessions, monkeypatch
):
    enable(monkeypatch)
    _, identity, version = await local_order(mall_mysql_sessions)
    a, _ = await staff(mall_mysql_sessions)
    b, _ = await staff(mall_mysql_sessions)

    async def change(actor):
        async with mall_mysql_sessions() as db:
            try:
                _, command = await mutate_admin_order(
                    db,
                    actor,
                    identity,
                    OrderNote(expectedVersion=version, internalNote=f"管理员{actor.actor_id}办理"),
                    key="mysql-concurrent-admin-note-001",
                )
                await db.commit()
                return actor, command.id
            except ConflictException:
                await db.rollback()
                return None

    result = await asyncio.wait_for(asyncio.gather(change(a), change(b)), timeout=20)
    winners = [x for x in result if x]
    assert len(winners) == 1
    winner, command_id = winners[0]
    repeats = await asyncio.wait_for(
        asyncio.gather(*[change(winner) for _ in range(20)]), timeout=30
    )
    assert all(x[1] == command_id for x in repeats)
    async with mall_mysql_sessions() as db:
        order = await db.get(MallOrder, identity)
        assert order.version == version + 1


async def test_locked_dispatch_check_sees_aftersale_after_old_snapshot(
    mall_mysql_sessions, monkeypatch
):
    from src.integrations.wechat_pay_types import PaymentFact
    from src.services.mall_payment_service import apply_verified_payment, prepare_payment

    enable(monkeypatch)
    buyer, identity, version = await local_order(mall_mysql_sessions)
    async with mall_mysql_sessions() as db:
        payment = await prepare_payment(
            db,
            buyer,
            identity,
            VersionAction(expectedVersion=version),
            key="mysql-admin-ready-pay-" + uuid4().hex,
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
                "admin-check-" + uuid4().hex,
                datetime(2026, 11, 4),
                payment.amount_cent,
                (await db.get(User, buyer.actor_id)).openid,
            ),
        )
        await db.commit()
        await defer_this_cases_payment_double(db, identity)
    async with mall_mysql_sessions() as stale:
        await stale.scalar(text("SELECT COUNT(*) FROM mall_aftersales"))
        async with mall_mysql_sessions() as writer:
            await writer.scalar(select(MallOrder).where(MallOrder.id == identity).with_for_update())
            writer.add(
                MallAftersale(
                    aftersale_no="A" + uuid4().hex[:31],
                    order_id=identity,
                    buyer_user_id=buyer.actor_id,
                    method="refund_only",
                    reason="处理中",
                )
            )
            await writer.commit()
        order = await stale.scalar(
            select(MallOrder)
            .where(MallOrder.id == identity)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        result = await check_fulfillment(stale, order, lock=True)
        assert not result["businessReady"] and "aftersale_pending" in {
            r["code"] for r in result["blockingReasons"]
        }


async def test_two_admins_cannot_create_two_shipments_for_one_paid_order(
    mall_mysql_sessions, monkeypatch
):
    from src.integrations.wechat_pay_types import PaymentFact
    from src.models.mall_trade import MallShipment
    from src.services.mall_payment_service import apply_verified_payment, prepare_payment

    enable(monkeypatch)
    buyer, identity, version = await local_order(mall_mysql_sessions)
    async with mall_mysql_sessions() as db:
        payment = await prepare_payment(
            db,
            buyer,
            identity,
            VersionAction(expectedVersion=version),
            key="mysql-ship-ready-pay-" + uuid4().hex,
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
                "mysql-ship-paid-" + uuid4().hex,
                datetime(2026, 11, 4),
                payment.amount_cent,
                (await db.get(User, buyer.actor_id)).openid,
            ),
        )
        await db.commit()
        await defer_this_cases_payment_double(db, identity)
        version = (await db.get(MallOrder, identity)).version

    async def new_staff():
        async with mall_mysql_sessions() as db:
            identity, _, _ = await admin(db, ["mall.shipments.write"])
            return MallActor("admin", identity, frozenset({"mall.shipments.write"}))

    first, second = await asyncio.gather(new_staff(), new_staff())

    async def ship(actor):
        async with mall_mysql_sessions() as db:
            try:
                shipment = await ship_order(
                    db,
                    actor,
                    identity,
                    ShipmentCreate(
                        expectedVersion=version,
                        courierCode="yuantong",
                        trackingNo="YT202611060001",
                    ),
                    key="mysql-concurrent-ship-" + str(actor.actor_id),
                )
                await db.commit()
                return shipment.id
            except ConflictException:
                await db.rollback()
                return None

    outcome = await asyncio.wait_for(asyncio.gather(ship(first), ship(second)), timeout=25)
    assert sum(value is not None for value in outcome) == 1
    async with mall_mysql_sessions() as db:
        order = await db.get(MallOrder, identity)
        shipments = (
            await db.scalars(select(MallShipment).where(MallShipment.order_id == identity))
        ).all()
        assert order.status == "pending_receipt" and order.version == version + 1
        assert len(shipments) == 1 and shipments[0].auto_receive_at
