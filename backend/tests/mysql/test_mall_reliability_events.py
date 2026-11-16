"""A verified inbox receipt succeeds only after event+job commit.

Runs after the empty-schema migration round-trip and other reliability probes.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from src.models.mall_operations import MallGatewayEvent, MallJob


async def test_atomic_event_acceptance_is_visible_from_new_connection(mall_mysql_sessions):
    from src.services.mall_gateway_event_service import accept_verified_gateway_event

    fields = dict(
        channel="test",
        event_id="atomic-event",
        event_type="probe",
        resource_id="probe-1",
        payload_ciphertext=bytes(range(256)),
        verified_digest="a" * 64,
    )
    ids = await asyncio.wait_for(
        asyncio.gather(
            accept_verified_gateway_event(mall_mysql_sessions, **fields),
            accept_verified_gateway_event(mall_mysql_sessions, **fields),
        ),
        timeout=10,
    )
    assert ids[0] == ids[1]
    async with mall_mysql_sessions() as session:
        event = await session.get(MallGatewayEvent, ids[0])
        assert event.event_id == "atomic-event"
        assert event.payload_ciphertext == bytes(range(256))
        jobs = (
            (
                await session.execute(
                    select(MallJob).where(MallJob.dedupe_key == f"gateway_event:{ids[0]}")
                )
            )
            .scalars()
            .all()
        )
        assert len(jobs) == 1


async def test_commit_failure_never_returns_acceptance(mall_mysql_sessions):
    from src.services.mall_gateway_event_service import accept_verified_gateway_event

    session = mall_mysql_sessions()
    session.commit = AsyncMock(side_effect=RuntimeError("simulated commit failure"))
    with pytest.raises(RuntimeError, match="commit failure"):
        await accept_verified_gateway_event(
            lambda: session,
            channel="test",
            event_id="failed-event",
            event_type="probe",
            resource_id="probe-2",
            payload_ciphertext=b"cipher",
            verified_digest="b" * 64,
        )
    async with mall_mysql_sessions() as reader:
        assert (
            await reader.execute(
                select(MallGatewayEvent).where(MallGatewayEvent.event_id == "failed-event")
            )
        ).scalar_one_or_none() is None
