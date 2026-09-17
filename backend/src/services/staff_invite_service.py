"""Organization-admin staff invite code flow."""

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import get_settings
from ..core.exceptions import BadRequestException, ConflictException, NotFoundException
from ..integrations.wechat_client import get_wechat_client
from ..models.distributor import Distributor, DistributorStatus, OrgRole
from ..models.organization import Organization, OrgStatus
from ..models.staff_invite import StaffInviteCode, StaffInviteCodeStatus
from ..models.user import ActivationStatus, User, UserType
from .binding_service import _mask_phone, _normalize_phone


INVITE_VALID_DAYS = 7
CHINA_TIMEZONE = timezone(timedelta(hours=8))


def _new_token() -> str:
    return secrets.token_hex(16)


def _format_api_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    # Invite timestamps are stored as UTC-naive values for compatibility with
    # the existing schema; make the API timezone explicit for clients.
    aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    return aware.astimezone(CHINA_TIMEZONE).isoformat(timespec="seconds")


def _response(code: StaffInviteCode, organization: Organization, inviter_name: str) -> dict:
    base = get_settings().public_api_base_url.rstrip("/")
    return {
        "inviteCodeId": str(code.id),
        "orgId": str(code.org_id),
        "organizationName": organization.name,
        "inviterName": inviter_name or "组织管理员",
        "refToken": code.ref_token,
        "sharePath": f"/pages/staff-join/index?refToken={code.ref_token}",
        "qrImageUrl": f"{base}/staff-invite-codes/{code.ref_token}/image",
        "status": code.status.value if hasattr(code.status, "value") else str(code.status),
        "expiresAt": _format_api_datetime(code.expires_at),
        "joinedCount": code.joined_count,
    }


async def get_or_create_code(db: AsyncSession, inviter: Distributor) -> dict:
    organization = await db.get(Organization, inviter.org_id)
    inviter_user = await db.get(User, inviter.user_id)
    code = (
        await db.execute(
            select(StaffInviteCode).where(
                StaffInviteCode.inviter_distributor_id == inviter.id
            )
        )
    ).scalars().first()
    now = datetime.utcnow()
    if code is None:
        code = StaffInviteCode(
            org_id=inviter.org_id,
            inviter_distributor_id=inviter.id,
            ref_token=_new_token(),
            status=StaffInviteCodeStatus.AVAILABLE,
            expires_at=now + timedelta(days=INVITE_VALID_DAYS),
        )
        db.add(code)
        await db.flush()
        await db.refresh(code)
    elif code.status != StaffInviteCodeStatus.AVAILABLE or code.expires_at <= now:
        code.ref_token = _new_token()
        code.status = StaffInviteCodeStatus.AVAILABLE
        code.expires_at = now + timedelta(days=INVITE_VALID_DAYS)
        db.add(code)
        await db.flush()
    return _response(code, organization, inviter_user.name if inviter_user else "")


async def refresh_code(db: AsyncSession, inviter: Distributor) -> dict:
    code = (
        await db.execute(
            select(StaffInviteCode).where(
                StaffInviteCode.inviter_distributor_id == inviter.id
            )
        )
    ).scalars().first()
    if code is not None:
        code.ref_token = _new_token()
        code.status = StaffInviteCodeStatus.AVAILABLE
        code.expires_at = datetime.utcnow() + timedelta(days=INVITE_VALID_DAYS)
        db.add(code)
        await db.flush()
    return await get_or_create_code(db, inviter)


async def revoke_code(db: AsyncSession, inviter: Distributor) -> None:
    code = (
        await db.execute(
            select(StaffInviteCode).where(
                StaffInviteCode.inviter_distributor_id == inviter.id
            )
        )
    ).scalars().first()
    if code is not None:
        code.status = StaffInviteCodeStatus.DISABLED
        db.add(code)
        await db.flush()


async def _valid_code(db: AsyncSession, ref_token: str):
    result = await db.execute(
        select(StaffInviteCode, Distributor, User, Organization)
        .join(Distributor, Distributor.id == StaffInviteCode.inviter_distributor_id)
        .join(User, User.id == Distributor.user_id)
        .join(Organization, Organization.id == StaffInviteCode.org_id)
        .where(StaffInviteCode.ref_token == ref_token)
    )
    row = result.first()
    if row is None:
        raise NotFoundException(message="客户顾问加入码不存在或已失效")
    code, inviter, inviter_user, organization = row
    if (
        code.status != StaffInviteCodeStatus.AVAILABLE
        or code.expires_at <= datetime.utcnow()
        or inviter.org_role != OrgRole.ADMIN
        or inviter.status != DistributorStatus.ACTIVE
        or inviter_user.activation_status != ActivationStatus.ACTIVE
        or organization.status != OrgStatus.ACTIVE
    ):
        raise BadRequestException(message="客户顾问加入码已失效，请联系组织管理员")
    return code, inviter, inviter_user, organization


async def get_code_info(db: AsyncSession, ref_token: str) -> dict:
    code, _inviter, inviter_user, organization = await _valid_code(db, ref_token)
    return {
        "organizationName": organization.name,
        "inviterName": inviter_user.name or "组织管理员",
        "expiresAt": _format_api_datetime(code.expires_at),
        "status": "available",
    }


async def join_organization(
    db: AsyncSession,
    ref_token: str,
    *,
    phone_code: str,
    name: str,
    consent_confirmed: bool,
) -> dict:
    if not consent_confirmed:
        raise BadRequestException(message="请先同意加入组织及账号信息授权")
    normalized_name = name.strip()
    if not normalized_name:
        raise BadRequestException(message="请填写真实姓名")
    code, _inviter, _inviter_user, organization = await _valid_code(db, ref_token)
    phone = _normalize_phone(await get_wechat_client().get_phone_number(phone_code))
    user = (
        await db.execute(select(User).where(User.phone == phone).with_for_update())
    ).scalars().first()
    if user is None:
        user = User(
            name=normalized_name,
            phone=phone,
            phone_masked=_mask_phone(phone),
            user_type=UserType.DISTRIBUTOR,
            phone_authorized=True,
            activation_status=ActivationStatus.ACTIVE,
            profile_completed=True,
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)
    else:
        existing = (
            await db.execute(select(Distributor).where(Distributor.user_id == user.id))
        ).scalars().first()
        if existing is not None and existing.org_id != organization.id:
            raise ConflictException(message="该账号已属于其他组织，请联系后台处理组织迁移")
        if existing is not None:
            return {
                "distributorId": str(existing.id),
                "orgId": str(existing.org_id),
                "organizationName": organization.name,
                "orgRole": existing.org_role.value,
                "joined": False,
            }
        user.name = normalized_name
        user.user_type = UserType.DISTRIBUTOR
        user.phone_authorized = True
        user.profile_completed = True
        db.add(user)

    distributor = Distributor(
        user_id=user.id,
        org_id=organization.id,
        org_role=OrgRole.MEMBER,
        status=DistributorStatus.ACTIVE,
        source_channel="staff_invite",
    )
    db.add(distributor)
    code.joined_count += 1
    db.add(code)
    await db.flush()
    await db.refresh(distributor)
    return {
        "distributorId": str(distributor.id),
        "orgId": str(organization.id),
        "organizationName": organization.name,
        "orgRole": "member",
        "joined": True,
    }
