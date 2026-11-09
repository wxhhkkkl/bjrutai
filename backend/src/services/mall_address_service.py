"""Owned recipient data; original values stay inside the backend."""

from sqlalchemy import select

from ..core.exceptions import ConflictException, ForbiddenException, NotFoundException
from ..models.audit import AuditLog
from ..models.mall_base import utc_now
from ..models.mall_operations import MallSettings
from ..models.mall_trade import MallAddress
from ..models.user import ActivationStatus, User
from .mall_catalog_query_service import _page
from .mall_consent_service import record_mall_notice_acknowledgement
from .mall_settings_service import get_mall_settings


async def lock_buyer(db, actor):
    if actor.actor_type != "user":
        raise ForbiddenException(message="仅本人小程序账号可操作")
    user = (
        await db.execute(
            select(User)
            .where(User.id == actor.actor_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if user is None or user.activation_status != ActivationStatus.ACTIVE:
        raise ForbiddenException(message="当前买家账号不可用")


async def owned_address(db, actor, identity, *, include_archived=False, lock=False):
    query = (
        select(MallAddress)
        .where(
            MallAddress.id == identity,
            MallAddress.user_id == actor.actor_id,
        )
        .execution_options(populate_existing=True)
    )
    if actor.actor_type != "user":
        raise NotFoundException(message="地址不存在")
    if not include_archived:
        query = query.where(MallAddress.archived_at.is_(None))
    if lock:
        query = query.with_for_update()
    row = (await db.execute(query)).scalar_one_or_none()
    if row is None:
        raise NotFoundException(message="地址不存在")
    return row


def serialize_address(row):
    return {
        "id": str(row.id),
        "recipientName": row.recipient_name,
        "phoneMasked": row.phone_masked,
        "regionCodes": [row.province_code, row.city_code, row.district_code],
        "regionNames": row.region_names or [],
        "addressMasked": "详细地址已保存",
        "isDefault": row.is_default,
        "version": row.version,
    }


def audit_address(db, actor, action, identity, version):
    db.add(
        AuditLog(
            user_id=actor.actor_id,
            action=action,
            entity_type="mall_address",
            entity_id=str(identity),
            detail={"version": version},
        )
    )


async def save_address(db, actor, data, *, address_id=None):
    if address_id:
        await owned_address(db, actor, address_id)
    await lock_buyer(db, actor)  # Serialize one buyer's defaults, including empty address books.
    if address_id is None and data.consent_confirmed is not True:
        raise ForbiddenException(message="请明确确认收件资料用途后再保存")
    row = await owned_address(db, actor, address_id, lock=True) if address_id else None
    if row and row.version != data.expected_version:
        raise ConflictException(message="地址版本已变化，请刷新")
    if row is None:
        await get_mall_settings(db)
        settings = (
            await db.execute(
                select(MallSettings)
                .where(MallSettings.id == 1)
                .with_for_update(read=True)
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        consent = await record_mall_notice_acknowledgement(
            db,
            actor,
            purposes={"recipient"},
            version=data.consent_version,
            current_version=settings.policy_versions.get("policy", ""),
            confirmed=data.consent_confirmed,
            scope_keys={
                "recipient_name",
                "recipient_phone",
                "recipient_region",
                "delivery_address",
            },
        )
        row = MallAddress(user_id=actor.actor_id, consent_record_id=consent.id, is_default=False)
    else:
        row.version += 1
    fields = data.model_fields_set
    if "is_default" in fields and data.is_default:
        others = (
            await db.scalars(
                select(MallAddress)
                .where(
                    MallAddress.user_id == actor.actor_id,
                    MallAddress.archived_at.is_(None),
                    MallAddress.is_default.is_(True),
                    MallAddress.id != (row.id or 0),
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
        for other in others:
            other.is_default = False
            other.version += 1
    for name in ("recipient_name", "phone", "address_line", "is_default"):
        if name in fields:
            setattr(row, name, getattr(data, name))
    if "region_codes" in fields:
        row.province_code, row.city_code, row.district_code = data.region_codes
        row.region_names = data.region_names
    elif "region_names" in fields:
        row.region_names = data.region_names
    row.phone_masked = row.phone[:3] + "****" + row.phone[-4:]
    db.add(row)
    await db.flush()
    audit_address(db, actor, "mall_address_save", row.id, row.version)
    return row


async def archive_address(db, actor, identity, expected_version):
    await owned_address(db, actor, identity)
    await lock_buyer(db, actor)
    row = await owned_address(db, actor, identity, lock=True)
    if row.version != expected_version:
        raise ConflictException(message="地址版本已变化，请刷新")
    row.archived_at, row.is_default = utc_now(), False
    row.version += 1
    await db.flush()
    audit_address(db, actor, "mall_address_archive", row.id, row.version)
    return row


async def list_addresses(db, actor, *, cursor=None, page_size=20):
    rows, next_cursor, total = await _page(
        db,
        select(MallAddress).where(
            MallAddress.user_id == actor.actor_id, MallAddress.archived_at.is_(None)
        ),
        MallAddress,
        MallAddress.id,
        mode=f"addresses:{actor.actor_id}",
        cursor=cursor,
        page_size=page_size,
    )
    # Reading recipient data is audited too; no raw values in the audit.
    for row in rows:
        audit_address(db, actor, "mall_address_read", row.id, row.version)
    return {
        "items": [serialize_address(row) for row in rows],
        "nextCursor": next_cursor,
        "total": total,
    }
