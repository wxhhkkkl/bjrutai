"""Verified gateway events are durable, deduplicated inbox records."""

import pytest
from sqlalchemy import select

from src.core.exceptions import ConflictException
from src.models.mall_operations import MallGatewayEvent


@pytest.mark.asyncio
async def test_gateway_event_is_persisted_once_without_raw_request_body(db_session):
    from src.services.mall_gateway_event_service import persist_gateway_event

    first = await persist_gateway_event(
        db_session,
        channel="wechat_pay",
        event_id="gateway-event-1",
        event_type="TRANSACTION.SUCCESS",
        resource_id="transaction-1",
        payload_ciphertext=b"test-ciphertext",
        verified_digest="d" * 64,
    )
    assert first.created
    assert first.event.status == "pending"
    await db_session.commit()  # An HTTP callback may ACK only after this commit.

    replay = await persist_gateway_event(
        db_session,
        channel="wechat_pay",
        event_id="gateway-event-1",
        event_type="TRANSACTION.SUCCESS",
        resource_id="transaction-1",
        payload_ciphertext=b"different-ciphertext-must-not-replace",
        verified_digest="d" * 64,
    )
    assert not replay.created
    assert replay.event.id == first.event.id
    events = (await db_session.execute(select(MallGatewayEvent))).scalars().all()
    assert len(events) == 1
    assert events[0].payload_ciphertext == b"test-ciphertext"
    assert "payload" not in MallGatewayEvent.__table__.c


@pytest.mark.asyncio
async def test_duplicate_event_identity_cannot_change_verified_facts(db_session):
    from src.services.mall_gateway_event_service import persist_gateway_event

    params = dict(
        channel="wechat_pay",
        event_id="conflict-event",
        event_type="TRANSACTION.SUCCESS",
        resource_id="transaction-1",
        payload_ciphertext=b"cipher",
        verified_digest="a" * 64,
    )
    await persist_gateway_event(db_session, **params)
    params["verified_digest"] = "b" * 64
    with pytest.raises(ConflictException):
        await persist_gateway_event(db_session, **params)
