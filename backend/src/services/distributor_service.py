"""Distributor service (US3/US4): account creation, org assignment, roles."""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
)
from ..core.security import get_password_hash
from ..models.distributor import Distributor, DistributorStatus, OrgRole
from ..models.organization import Organization
from ..models.user import ActivationStatus, User, UserType
from ..schemas.distributor import (
    DistributorCreate,
    DistributorRoleUpdate,
    DistributorUpdate,
    ResetPassword,
)
from . import organization_service


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------
async def get_distributor_or_404(db: AsyncSession, distributor_id: int) -> Distributor:
    result = await db.execute(select(Distributor).where(Distributor.id == distributor_id))
    d = result.scalars().first()
    if d is None:
        raise NotFoundException(message="Distributor not found")
    return d


async def get_distributor_by_user(db: AsyncSession, user_id: int) -> Optional[Distributor]:
    result = await db.execute(select(Distributor).where(Distributor.user_id == user_id))
    return result.scalars().first()


async def is_distributor_selectable(db: AsyncSession, distributor: Distributor) -> bool:
    """A distributor is selectable (可开展业务) when its org has an approved,
    non-expired qualification and is not disabled (FR-008)."""
    from . import organization_service

    reasons = await organization_service.get_org_business_blocked_reasons(db, distributor.org_id)
    return not reasons


async def _org_name(db: AsyncSession, org_id: int) -> Optional[str]:
    result = await db.execute(select(Organization.name).where(Organization.id == org_id))
    return result.scalars().first()


async def _to_dict(db: AsyncSession, d: Distributor) -> dict:
    user = await db.get(User, d.user_id)
    return {
        "distributorId": str(d.id),
        "orgId": str(d.org_id),
        "orgName": await _org_name(db, d.org_id),
        "name": user.name if user else None,
        "phone": user.phone_masked or user.phone if user else None,
        "orgRole": d.org_role.value if hasattr(d.org_role, "value") else str(d.org_role),
        "status": d.status.value if hasattr(d.status, "value") else str(d.status),
        "wechatBound": bool(user and user.wechat_bound),
        "sourceChannel": d.source_channel or "admin_create",
        "createdAt": d.created_at.isoformat() if d.created_at else None,
    }


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
async def create_distributor(
    db: AsyncSession, org_id: int, data: DistributorCreate, operator_id: Optional[int] = None
) -> dict:
    """Create a distributor account within an org (single org attribution)."""
    await organization_service._get_org_or_404(db, org_id)

    # Phone uniqueness (login identifier)
    result = await db.execute(select(User).where(User.phone == data.phone))
    if result.scalars().first() is not None:
        raise ConflictException(message="该手机号已存在分销员账户")

    user = User(
        name=data.name,
        phone=data.phone,
        phone_masked=data.phone[:3] + "****" + data.phone[-4:],
        password_hash=get_password_hash(data.initial_password),
        user_type=UserType.DISTRIBUTOR,
        activation_status=ActivationStatus.ACTIVE,
        wechat_bound=False,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    distributor = Distributor(
        user_id=user.id,
        org_id=org_id,
        org_role=OrgRole.MEMBER,
        status=DistributorStatus.ACTIVE,
    )
    db.add(distributor)
    await db.flush()
    await db.refresh(distributor)
    return await _to_dict(db, distributor)


async def list_distributors(
    db: AsyncSession,
    org_id: int,
    include_subtree: bool = False,
    role: Optional[str] = None,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """List distributors under an org (optionally the whole subtree)."""
    org_ids = {org_id}
    if include_subtree:
        subtree = await organization_service.get_subtree(db, org_id)
        org_ids |= _collect_org_ids(subtree)

    stmt = (
        select(Distributor)
        .where(Distributor.org_id.in_(org_ids))
        .order_by(Distributor.id.desc())
    )
    if role:
        stmt = stmt.where(Distributor.org_role == role)
    if status:
        stmt = stmt.where(Distributor.status == status)
    if keyword:
        stmt = stmt.join(User).where(User.name.contains(keyword) | User.phone.contains(keyword))

    count_stmt = select(Distributor.id).where(
        Distributor.org_id.in_(org_ids)
    )
    if role:
        count_stmt = count_stmt.where(Distributor.org_role == role)
    total = (await db.execute(count_stmt)).scalars().all()

    result = await db.execute(stmt.limit(limit).offset(offset))
    items = [await _to_dict(db, d) for d in result.scalars().all()]
    return {"items": items, "total": len(total), "hasMore": offset + len(items) < len(total)}


def _collect_org_ids(node: dict, acc: Optional[set] = None) -> set:
    if acc is None:
        acc = set()
    acc.add(int(node["orgId"]))
    for child in node.get("children", []):
        _collect_org_ids(child, acc)
    return acc


async def update_distributor(
    db: AsyncSession, distributor_id: int, data: DistributorUpdate, operator_id: Optional[int] = None
) -> dict:
    """Adjust a distributor's org and/or status."""
    d = await get_distributor_or_404(db, distributor_id)

    if data.org_id is not None:
        if d.org_role == OrgRole.ADMIN:
            raise BadRequestException(message="组织管理员不可调整组织，请先撤销其管理员身份")
        await organization_service._get_org_or_404(db, data.org_id)
        d.org_id = data.org_id

    if data.status is not None:
        if data.status not in {s.value for s in DistributorStatus}:
            raise BadRequestException(message=f"Invalid distributor status: {data.status}")
        d.status = DistributorStatus(data.status)

    db.add(d)
    await db.flush()
    await db.refresh(d)
    return await _to_dict(db, d)


async def reset_password(
    db: AsyncSession, distributor_id: int, data: ResetPassword, operator_id: Optional[int] = None
) -> None:
    """Reset a distributor's login credential."""
    d = await get_distributor_or_404(db, distributor_id)
    user = await db.get(User, d.user_id)
    if user is None:
        raise NotFoundException(message="Distributor user not found")
    user.password_hash = get_password_hash(data.new_password)
    db.add(user)
    await db.flush()


async def set_role(
    db: AsyncSession, distributor_id: int, data: DistributorRoleUpdate, operator_id: Optional[int] = None
) -> dict:
    """Set or revoke org-admin role for a distributor (US4, backend-only).

    Enforces FR-008: each org has at most one admin. Setting a second admin
    in an org that already has one is rejected.
    """
    if data.org_role not in {r.value for r in OrgRole}:
        raise BadRequestException(message="orgRole must be member or admin")
    d = await get_distributor_or_404(db, distributor_id)

    if data.org_role == OrgRole.ADMIN.value:
        existing = await db.execute(
            select(Distributor).where(
                Distributor.org_id == d.org_id,
                Distributor.org_role == OrgRole.ADMIN,
                Distributor.id != d.id,
            )
        )
        if existing.scalars().first() is not None:
            raise BadRequestException(message="该组织已有管理员，请先撤销")

    d.org_role = OrgRole(data.org_role)
    db.add(d)
    await db.flush()
    await db.refresh(d)
    return await _to_dict(db, d)


# ---------------------------------------------------------------------------
# Registration helper (012-register-default-dept)
# ---------------------------------------------------------------------------
async def register_distributor(
    db: AsyncSession,
    user_id: int,
    org_id: int,
    source_channel: str,
) -> Distributor:
    """Create a bare Distributor record for a newly registered user (FR-002/FR-003).

    The caller is responsible for ensuring the User and Organization exist.
    No extra validation — the auth service guards against duplicates.
    """
    distributor = Distributor(
        user_id=user_id,
        org_id=org_id,
        org_role=OrgRole.MEMBER,
        status=DistributorStatus.ACTIVE,
        source_channel=source_channel,
    )
    db.add(distributor)
    await db.flush()
    await db.refresh(distributor)
    return distributor
