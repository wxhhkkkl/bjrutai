"""Single-store configuration with closed defaults and versioned updates."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import get_settings
from ..core.exceptions import ConflictException, ForbiddenException, ValidationException
from ..models.mall_operations import MallSettings


async def get_mall_settings(db: AsyncSession) -> MallSettings:
    settings = await db.get(MallSettings, 1)
    if settings is not None:
        return settings
    settings = MallSettings(id=1, enabled=False, purchase_enabled=False)
    try:
        async with db.begin_nested():
            db.add(settings)
            await db.flush()
    except IntegrityError:
        return (await db.execute(select(MallSettings).where(MallSettings.id == 1))).scalar_one()
    return settings


def require_mall_purchase_open(settings: MallSettings) -> None:
    runtime = get_settings()
    if (
        not runtime.mall_enabled
        or not runtime.mall_purchase_enabled
        or not settings.enabled
        or not settings.purchase_enabled
    ):
        raise ForbiddenException(message="商城购买当前未开放")


async def update_mall_settings(
    db: AsyncSession,
    *,
    expected_version: int,
    **changes,
) -> MallSettings:
    allowed = {
        "enabled",
        "purchase_enabled",
        "freight_mode",
        "freight_cent",
        "blocked_regions",
        "payment_minutes",
        "auto_receive_days",
        "aftersale_days",
        "dispatch_address_snapshot",
        "return_address_snapshot",
        "contact",
        "return_instructions",
        "policy_versions",
    }
    if not changes.keys() <= allowed:
        raise ValidationException(message="商城配置字段不合法")
    await get_mall_settings(db)
    settings = (
        await db.execute(
            select(MallSettings)
            .where(MallSettings.id == 1)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    if settings.version != expected_version:
        raise ConflictException(message="商城配置版本已变化，请刷新")
    for key, value in changes.items():
        setattr(settings, key, value)
    settings.version += 1
    await db.flush()
    return settings


def serialize_mall_settings(settings: MallSettings) -> dict:
    return {
        "version": settings.version,
        "enabled": settings.enabled,
        "purchaseEnabled": settings.purchase_enabled,
        "freightMode": settings.freight_mode,
        "freightCent": settings.freight_cent,
        "paymentMinutes": settings.payment_minutes,
        "autoReceiveDays": settings.auto_receive_days,
        "aftersaleDays": settings.aftersale_days,
        "blockedRegionCodes": settings.blocked_regions,
        "contactText": settings.contact,
        "policyVersion": settings.policy_versions.get("policy", ""),
        "dispatchAddressMasked": "已配置" if settings.dispatch_address_snapshot else "",
        "returnAddressMasked": "已配置" if settings.return_address_snapshot else "",
        "returnInstructions": settings.return_instructions,
    }
