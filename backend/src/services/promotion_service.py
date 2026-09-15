"""Promotion code service – generate, refresh, statistics (US10)."""

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import get_settings
from ..core.exceptions import BadRequestException, ForbiddenException, NotFoundException
from ..models.distributor import Distributor
from ..models.promotion import PromotionCode, PromotionCodeStatus

logger = logging.getLogger(__name__)
settings = get_settings()

SOURCE_CODE = "BJTR"
DEFAULT_SHARE_TITLE = "邀请您绑定儒泰医联业务员"
CHINA_TIMEZONE = timezone(timedelta(hours=8))


# ============================================================================
# Helpers
# ============================================================================
async def _get_promoter(db: AsyncSession, user_id: int) -> Distributor:
    """Look up the Distributor record for the given user. Raises Forbidden if not found."""
    result = await db.execute(
        select(Distributor).where(Distributor.user_id == user_id)
    )
    promoter = result.scalars().first()
    if promoter is None:
        raise ForbiddenException(message="当前账号尚未成为业务员")
    return promoter


async def _check_approved_qualification(db: AsyncSession, distributor_id: int) -> bool:
    """Verify the distributor's org has an approved qualification (FR-008)."""
    from ..services import distributor_service

    result = await db.execute(
        select(Distributor).where(Distributor.id == distributor_id)
    )
    distributor = result.scalars().first()
    if distributor is None or not await distributor_service.is_distributor_selectable(db, distributor):
        raise ForbiddenException(
            message="所属组织资质通过后才能使用客户绑定码"
        )
    return True


def _generate_ref_token() -> str:
    """Generate a WeChat scene-compatible secure 32-character token."""
    return secrets.token_hex(16)


def _format_api_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    return aware.astimezone(CHINA_TIMEZONE).isoformat(timespec="seconds")


def _code_to_response(code: PromotionCode) -> dict:
    """Serialize a PromotionCode model to a response dict."""
    status = code.status.value if hasattr(code.status, "value") else str(code.status)
    public_base = settings.public_api_base_url.rstrip("/")
    return {
        "promotionCodeId": str(code.id),
        "refToken": code.ref_token,
        "sourceCode": code.source_code,
        "qrImageUrl": f"{public_base}/customer-binding-codes/{code.ref_token}/image",
        "shareTitle": code.share_title or DEFAULT_SHARE_TITLE,
        "sharePath": code.share_path
        or f"/pages/patient-binding/index?refToken={code.ref_token}",
        "status": status,
        "statusLabel": "客户绑定码可用" if status == PromotionCodeStatus.AVAILABLE.value else "客户绑定码不可用",
        "expiresAt": _format_api_datetime(code.expires_at),
        "disabledReason": code.disabled_reason,
        "scanCount": code.scan_count,
        "leadCount": code.lead_count,
        "bindCount": code.bind_count,
        "createdAt": _format_api_datetime(code.created_at),
        "updatedAt": _format_api_datetime(code.updated_at),
    }


# ============================================================================
# Get Promotion Code
# ============================================================================
async def get_promotion_code(
    db: AsyncSession,
    user_id: int,
) -> dict:
    """Return the current promotion code for the user, generating one if needed.

    The promoter must have an approved qualification.
    """
    promoter = await _get_promoter(db, user_id)
    await _check_approved_qualification(db, promoter.id)

    # Check for existing available promotion code
    result = await db.execute(
        select(PromotionCode)
        .where(
            PromotionCode.distributor_id == promoter.id,
            PromotionCode.status == PromotionCodeStatus.AVAILABLE,
        )
    )
    code = result.scalars().first()

    if code is not None and len(code.ref_token) <= 32:
        expected_path = f"/pages/patient-binding/index?refToken={code.ref_token}"
        if (
            code.share_path != expected_path
            or code.share_title != DEFAULT_SHARE_TITLE
            or code.qr_image_url is not None
        ):
            # Repair codes created by the former demo-QR implementation so an
            # already deployed account immediately shares the patient flow.
            code.share_path = expected_path
            code.share_title = DEFAULT_SHARE_TITLE
            code.qr_image_url = None
            db.add(code)
            await db.flush()
        return _code_to_response(code)

    if code is not None:
        code.ref_token = _generate_ref_token()
        code.share_path = f"/pages/patient-binding/index?refToken={code.ref_token}"
        code.share_title = DEFAULT_SHARE_TITLE
        code.qr_image_url = None
        db.add(code)
        await db.flush()
        await db.refresh(code)
        return _code_to_response(code)

    # Generate a new promotion code
    ref_token = _generate_ref_token()
    now = datetime.now(timezone.utc)

    code = PromotionCode(
        distributor_id=promoter.id,
        ref_token=ref_token,
        source_code=SOURCE_CODE,
        status=PromotionCodeStatus.AVAILABLE,
        share_title=DEFAULT_SHARE_TITLE,
        share_path=f"/pages/patient-binding/index?refToken={ref_token}",
    )
    db.add(code)
    await db.flush()
    await db.refresh(code)

    logger.info("Promotion code generated: promoter=%d ref_token=%s", promoter.id, ref_token[:8])
    return _code_to_response(code)


# ============================================================================
# Refresh Promotion Code
# ============================================================================
async def refresh_code(
    db: AsyncSession,
    user_id: int,
) -> dict:
    """Refresh the promotion code by generating a new ref_token in-place.

    The promoter must have an approved qualification. Since the promotion_codes
    table enforces unique distributor_id, we update the existing record instead of
    creating a new one.
    """
    promoter = await _get_promoter(db, user_id)
    await _check_approved_qualification(db, promoter.id)

    # Find the current code (any status - we'll reactivate it)
    result = await db.execute(
        select(PromotionCode)
        .where(PromotionCode.distributor_id == promoter.id)
    )
    code = result.scalars().first()

    old_ref_token = None
    now = datetime.now(timezone.utc)
    new_ref_token = _generate_ref_token()

    if code is not None:
        old_ref_token = code.ref_token
        code.ref_token = new_ref_token
        code.share_path = f"/pages/patient-binding/index?refToken={new_ref_token}"
        code.share_title = DEFAULT_SHARE_TITLE
        code.qr_image_url = None
        code.status = PromotionCodeStatus.AVAILABLE
        code.disabled_reason = None
        code.updated_at = now
        db.add(code)
    else:
        # No code exists yet; create one
        code = PromotionCode(
            distributor_id=promoter.id,
            ref_token=new_ref_token,
            source_code=SOURCE_CODE,
            status=PromotionCodeStatus.AVAILABLE,
            share_title=DEFAULT_SHARE_TITLE,
            share_path=f"/pages/patient-binding/index?refToken={new_ref_token}",
        )
        db.add(code)

    await db.flush()
    await db.refresh(code)

    logger.info(
        "Promotion code refreshed: promoter=%d old=%s new=%s",
        promoter.id,
        (old_ref_token or "none")[:8],
        new_ref_token[:8],
    )

    response = _code_to_response(code)
    response["oldRefToken"] = old_ref_token
    response["refreshedAt"] = now.isoformat()

    return response


# ============================================================================
# Get Statistics
# ============================================================================
async def get_statistics(
    db: AsyncSession,
    user_id: int,
    period: str = "30d",
) -> dict:
    """Return promotion statistics for the current promoter.

    Args:
        period: Time range identifier (e.g. '7d', '30d', '90d'). Currently
                the counts are cumulative from the PromotionCode record.
    """
    promoter = await _get_promoter(db, user_id)
    await _check_approved_qualification(db, promoter.id)

    # Get the current available code (or most recent)
    result = await db.execute(
        select(PromotionCode)
        .where(PromotionCode.distributor_id == promoter.id)
        .order_by(PromotionCode.updated_at.desc())
        .limit(1)
    )
    code = result.scalars().first()

    if code is None:
        return {
            "period": period,
            "scanCount": 0,
            "leadCount": 0,
            "bindCount": 0,
            "conversionRate": 0.0,
        }

    scan_count = code.scan_count
    lead_count = code.lead_count
    bind_count = code.bind_count
    conversion_rate = round(bind_count / scan_count, 4) if scan_count > 0 else 0.0

    return {
        "period": period,
        "scanCount": scan_count,
        "leadCount": lead_count,
        "bindCount": bind_count,
        "conversionRate": conversion_rate,
    }


# ============================================================================
# Get Poster
# ============================================================================
async def get_poster(
    db: AsyncSession,
    user_id: int,
) -> dict:
    """Return the promotion poster info including QR code image URL.

    The promoter must have an approved qualification.
    """
    promoter = await _get_promoter(db, user_id)
    await _check_approved_qualification(db, promoter.id)

    result = await db.execute(
        select(PromotionCode)
        .where(
            PromotionCode.distributor_id == promoter.id,
            PromotionCode.status == PromotionCodeStatus.AVAILABLE,
        )
    )
    code = result.scalars().first()

    if code is None:
        raise NotFoundException(message="暂无可用客户绑定码，请先生成")

    return {
        "posterUrl": f"{settings.public_api_base_url.rstrip('/')}/customer-binding-codes/{code.ref_token}/image",
        "qrImageUrl": f"{settings.public_api_base_url.rstrip('/')}/customer-binding-codes/{code.ref_token}/image",
        "shareTitle": DEFAULT_SHARE_TITLE,
        "sharePath": f"/pages/patient-binding/index?refToken={code.ref_token}",
        "sourceCode": code.source_code,
    }
