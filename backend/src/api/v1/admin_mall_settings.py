"""Versioned, idempotent settings with live authorization."""

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_db
from ...api.mall_deps import MallActor, require_mall_admin
from ...core.error_handler import _build_response
from ...core.exceptions import ConflictException
from ...schemas.mall_settings import MallSettingsUpdate
from ...services.mall_audit_service import record_mall_admin_audit
from ...services.mall_command_service import complete_mall_command, reserve_mall_command
from ...services.mall_settings_service import (
    get_mall_settings,
    serialize_mall_settings,
    update_mall_settings,
)

router = APIRouter(prefix="/admin/mall/settings", tags=["admin-mall-settings"])


@router.get("")
async def get_settings(
    actor: MallActor = Depends(require_mall_admin("mall.settings.read")),
    db: AsyncSession = Depends(get_db),
):
    settings = await get_mall_settings(db)
    await db.commit()
    can_view_address_details = "mall.settings.write" in actor.permissions
    return _build_response(
        0,
        "success",
        serialize_mall_settings(
            settings, include_address_details=can_view_address_details
        ),
    )


@router.patch("")
async def patch_settings(
    body: MallSettingsUpdate,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(require_mall_admin("mall.settings.write")),
    db: AsyncSession = Depends(get_db),
):
    try:
        reservation = await reserve_mall_command(
            db,
            actor=actor,
            action="updateMallSettings",
            key=idempotency_key,
            payload=body.model_dump(mode="json", by_alias=True),
        )
        if not reservation.created:
            if reservation.command.status != "completed":
                raise ConflictException(message="商城配置请求仍在处理中")
            settings = await get_mall_settings(db)
        else:
            value = body.settings
            changes = dict(
                enabled=value.enabled,
                purchase_enabled=value.purchase_enabled,
                freight_mode=value.freight_mode,
                freight_cent=value.freight_cent,
                blocked_regions=value.default_blocked_region_codes,
                payment_minutes=value.payment_minutes,
                auto_receive_days=value.auto_receive_days,
                aftersale_days=value.aftersale_days,
                contact=value.contact_text,
                return_instructions=value.return_instructions,
            )
            if body.freight_templates is not None:
                changes["freight_templates"] = [
                    item.model_dump(by_alias=True) for item in body.freight_templates
                ]
            if body.dispatch_address is not None:
                changes["dispatch_address_snapshot"] = body.dispatch_address.model_dump(
                    by_alias=True
                )
            if body.return_address is not None:
                changes["return_address_snapshot"] = body.return_address.model_dump(by_alias=True)
            settings = await update_mall_settings(
                db, expected_version=body.expected_version, **changes
            )
            await record_mall_admin_audit(
                db,
                actor=actor,
                action="mall_settings_update",
                entity_type="mall_settings",
                entity_id="1",
                detail={"version": settings.version},
            )
            await complete_mall_command(db, reservation, entity_type="mall_settings", entity_id=1)
        await db.commit()
        return _build_response(
            0,
            "success",
            serialize_mall_settings(settings, include_address_details=True),
        )
    except Exception:
        await db.rollback()
        raise
