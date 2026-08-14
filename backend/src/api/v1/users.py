"""Current user profile endpoints (T169).

GET  /me/profile           – user profile with editableFields, version
PUT  /me/profile           – update name, avatar (optimistic locking via version)
POST /me/avatar/upload-token – file upload token via COS client
GET  /me/account-summary   – lightweight account status data
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, Union

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_current_user, get_db
from ...core.exceptions import BadRequestException, ConflictException, NotFoundException
from ...integrations.cos_client import ALLOWED_CONTENT_TYPES, COSClient, get_cos_client
from ...models.distributor import Distributor
from ...models.organization import Organization
from ...models.user import User

router = APIRouter(prefix="/me", tags=["me"])


def _ok(data=None) -> dict:
    return {
        "code": 0,
        "message": "success",
        "data": data,
        "requestId": uuid.uuid4().hex,
        "serverTime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


async def _organization_name(db: AsyncSession, user: User) -> Optional[str]:
    """Prefer the distributor's assigned organization over legacy profile text."""
    result = await db.execute(
        select(Organization.name)
        .join(Distributor, Distributor.org_id == Organization.id)
        .where(Distributor.user_id == user.id)
    )
    return result.scalars().first() or user.organization


# ──────────────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────────────
class ProfileUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    organization: Optional[str] = Field(None, max_length=200)
    avatar: Optional[str] = Field(None, max_length=500)
    # User has no integer version column; updated_at is the optimistic-lock version.
    # Accept int for backwards compatibility, but the current client sends the ISO string from GET /profile.
    version: Union[str, int] = Field(..., description="Client's current profile version for optimistic locking")


class AvatarUploadTokenRequest(BaseModel):
    fileName: str = Field(..., min_length=1, max_length=255)
    contentType: str = Field(..., min_length=1)
    fileSize: int = Field(..., gt=0, le=10 * 1024 * 1024)


# ──────────────────────────────────────────────────────────────────
# GET /me/profile
# ──────────────────────────────────────────────────────────────────
@router.get("/profile")
async def get_profile(
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """Return the current user's profile."""
    user_id = int(payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if user is None:
        raise NotFoundException(message="User not found")

    editable_fields = ["name", "avatar"]
    organization = await _organization_name(db, user)
    return _ok({
        "userId": str(user.id),
        "name": user.name,
        "phone": user.phone_masked or user.phone,
        "organization": organization,
        "avatar": user.avatar_url,
        "userType": user.user_type.value if hasattr(user.user_type, "value") else str(user.user_type),
        "activationStatus": user.activation_status.value if hasattr(user.activation_status, "value") else str(user.activation_status),
        "qualificationStatus": user.qualification_status.value if hasattr(user.qualification_status, "value") else str(user.qualification_status),
        "wechatBound": user.wechat_bound,
        "editableFields": editable_fields,
        "version": user.updated_at.isoformat() if user.updated_at else None,
    })


# ──────────────────────────────────────────────────────────────────
# PUT /me/profile
# ──────────────────────────────────────────────────────────────────
@router.put("/profile")
async def update_profile(
    body: ProfileUpdateRequest,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """Update the current user's profile with optimistic locking."""
    user_id = int(payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if user is None:
        raise NotFoundException(message="User not found")

    # Optimistic locking: compare versions
    if user.updated_at is not None:
        current_version = user.updated_at.isoformat()
        if str(body.version) != current_version:
            raise ConflictException(
                message="Profile has been modified by another session. Please refresh and retry.",
                code=40901,
            )

    if body.name is not None:
        user.name = body.name
    if body.organization is not None:
        raise BadRequestException(message="所属机构由系统维护，无法手动修改")
    if body.avatar is not None:
        user.avatar_url = body.avatar

    db.add(user)
    await db.commit()
    await db.refresh(user)

    organization = await _organization_name(db, user)
    return _ok({
        "userId": str(user.id),
        "name": user.name,
        "organization": organization,
        "avatar": user.avatar_url,
        "version": user.updated_at.isoformat() if user.updated_at else None,
    })


# ──────────────────────────────────────────────────────────────────
# POST /me/avatar/upload-token
# ──────────────────────────────────────────────────────────────────
@router.post("/avatar/upload-token")
async def get_avatar_upload_token(
    body: AvatarUploadTokenRequest,
    payload: dict = Depends(get_current_user),
) -> dict:
    """Generate a COS pre-signed upload URL for avatar image."""
    user_id = int(payload["sub"])
    cos: COSClient = get_cos_client()

    if body.contentType not in {content_type for content_type in ALLOWED_CONTENT_TYPES if content_type.startswith("image/")}:
        raise BadRequestException(message="头像仅支持 JPG、PNG、GIF 或 WEBP 图片")

    try:
        upload_info = cos.generate_upload_token(
            user_id=user_id,
            file_name=body.fileName,
            content_type=body.contentType,
            file_size=body.fileSize,
            key_prefix="avatars/",
        )
    except ValueError as exc:
        raise BadRequestException(message=str(exc))

    return _ok(upload_info)


# ──────────────────────────────────────────────────────────────────
# GET /me/account-summary
# ──────────────────────────────────────────────────────────────────
@router.get("/account-summary")
async def get_account_summary(
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """Return lightweight account status data for the header/profile bar."""
    user_id = int(payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if user is None:
        raise NotFoundException(message="User not found")

    # Count unread notifications
    from ...models.notification import Notification
    notif_result = await db.execute(
        select(Notification).where(
            Notification.user_id == user_id,
            Notification.is_read == False,
        )
    )
    unread_count = len(notif_result.scalars().all())

    return _ok({
        "userId": str(user.id),
        "name": user.name,
        "avatar": user.avatar_url,
        "role": user.user_type.value if hasattr(user.user_type, "value") else str(user.user_type),
        "qualificationStatus": user.qualification_status.value if hasattr(user.qualification_status, "value") else str(user.qualification_status),
        "unreadNotifications": unread_count,
    })
