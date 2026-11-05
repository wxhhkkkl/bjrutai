"""Database idempotency survives a new service instance and a new session."""

import pytest
from sqlalchemy import select

from src.api.mall_deps import MallActor
from src.core.exceptions import ConflictException
from src.models.mall_operations import MallCommand
from tests.conftest import TestAsyncSession


@pytest.mark.asyncio
async def test_command_replay_uses_persisted_actor_action_key_and_payload_hash(db_session):
    from src.services.mall_command_service import reserve_mall_command

    actor = MallActor(actor_type="user", actor_id=22, permissions=frozenset())
    first = await reserve_mall_command(
        db_session,
        actor=actor,
        action="mall.checkout.create",
        key="checkout-key-1",
        payload={"skuId": 3, "quantity": 2},
    )
    assert first.created
    assert first.command.status == "running"
    assert "payload" not in MallCommand.__table__.c
    await db_session.commit()

    # A new session simulates retry after a process restart or on another worker.
    async with TestAsyncSession() as retry_session:
        replay = await reserve_mall_command(
            retry_session,
            actor=actor,
            action="mall.checkout.create",
            key="checkout-key-1",
            payload={"quantity": 2, "skuId": 3},
        )
        assert not replay.created
        assert replay.command.id == first.command.id

        with pytest.raises(ConflictException, match="请求内容"):
            await reserve_mall_command(
                retry_session,
                actor=actor,
                action="mall.checkout.create",
                key="checkout-key-1",
                payload={"skuId": 3, "quantity": 3},
            )

    async with TestAsyncSession() as reader:
        commands = (await reader.execute(select(MallCommand))).scalars().all()
        assert len(commands) == 1
