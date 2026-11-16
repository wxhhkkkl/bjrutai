"""Durable, deduplicated mall gateway inbox records."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.exceptions import ConflictException
from ..models.mall_base import utc_now
from ..models.mall_operations import MallGatewayEvent
from .mall_job_service import enqueue_mall_job


@dataclass(frozen=True)
class GatewayEventReceipt:
    event: MallGatewayEvent
    created: bool


async def persist_gateway_event(
    db: AsyncSession,
    *,
    channel: str,
    event_id: str,
    event_type: str,
    resource_id: str,
    payload_ciphertext: bytes | None,
    verified_digest: str,
) -> GatewayEventReceipt:
    """Persist an already verified event; callers ACK only after committing."""
    existing = (
        await db.execute(
            select(MallGatewayEvent).where(
                MallGatewayEvent.channel == channel,
                MallGatewayEvent.event_id == event_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        _check_same_event(existing, event_type, resource_id, verified_digest)
        return GatewayEventReceipt(event=existing, created=False)

    event = MallGatewayEvent(
        channel=channel,
        event_id=event_id,
        event_type=event_type,
        resource_id=resource_id,
        payload_ciphertext=payload_ciphertext,
        verified_digest=verified_digest,
        received_at=utc_now(),
        status="pending",
    )
    try:
        async with db.begin_nested():
            db.add(event)
            await db.flush()
    except IntegrityError:
        existing = (
            await db.execute(
                select(MallGatewayEvent)
                .where(
                    MallGatewayEvent.channel == channel,
                    MallGatewayEvent.event_id == event_id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        _check_same_event(existing, event_type, resource_id, verified_digest)
        return GatewayEventReceipt(event=existing, created=False)
    return GatewayEventReceipt(event=event, created=True)


def _check_same_event(event, event_type, resource_id, verified_digest):
    if (event.event_type, event.resource_id, event.verified_digest) != (
        event_type,
        resource_id,
        verified_digest,
    ):
        raise ConflictException(message="渠道事件身份与已核验内容不一致")


async def accept_verified_gateway_event(session_factory, **fields) -> int:
    """Internal receipt boundary; only accepts already verified channel facts.

    This is not a notification endpoint or signature verifier.  Future approved
    callbacks must verify identity/signature before calling it and respond only
    after it returns.  A dedicated session commits inbox+work atomically.
    """
    async with session_factory() as db:
        try:
            receipt = await persist_gateway_event(db, **fields)
            await enqueue_mall_job(
                db,
                kind="gateway_event_apply",
                entity_type="mall_gateway_event",
                entity_id=receipt.event.id,
                entity_version=receipt.event.version,
                dedupe_key=f"gateway_event:{receipt.event.id}",
            )
            event_id = receipt.event.id
            await db.commit()
            return event_id
        except Exception:
            await db.rollback()
            raise
