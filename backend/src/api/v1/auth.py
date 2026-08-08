"""Auth endpoints: login, token management, session, and phone binding.

All endpoints under ``/api/v1/auth/``.  Responses use the unified envelope
``{code, message, data, requestId, serverTime}`` (rendered by the error handler
for exceptions; success responses are built inline or via a shared helper).
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_current_user, get_db
from ...core.exceptions import UnauthorizedException
from ...schemas.auth import (
    AdminLoginRequest,
    AdminLoginResponse,
    DistributorRegisterRequest,
    DistributorRegisterResponse,
    PhoneBindRequest,
    PhoneBindResponse,
    RefreshRequest,
    RefreshResponse,
    SessionResponse,
    WechatLoginRequest,
    WechatLoginResponse,
)
from ...services.auth_service import get_auth_service
from pydantic import BaseModel, Field

router = APIRouter(prefix="/auth", tags=["auth"])


class DistributorLoginRequest(BaseModel):
    phone: str = Field(..., pattern=r"^\d{11}$")
    password: str = Field(..., min_length=8, max_length=128)


class BindWechatRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=256)


def _ok(data=None) -> dict:
    return {
        "code": 0,
        "message": "success",
        "data": data,
        "requestId": uuid.uuid4().hex,
        "serverTime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# ──────────────────────────────────────────────────────────────────
# POST /auth/wechat-login
# ──────────────────────────────────────────────────────────────────
@router.post("/wechat-login")
async def wechat_login(
    body: WechatLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """WeChat Mini-Program login via ``wx.login()`` code."""
    svc = get_auth_service()
    result = await svc.wechat_login(db, body.code, phone_code=body.phoneCode)
    return _ok(result)


# ──────────────────────────────────────────────────────────────────
# POST /auth/distributor-login
# ──────────────────────────────────────────────────────────────────
@router.post("/distributor-login")
async def distributor_login(
    body: DistributorLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Distributor login via phone + password."""
    svc = get_auth_service()
    result = await svc.distributor_login(db, body.phone, body.password)
    return _ok(result)


# ──────────────────────────────────────────────────────────────────
# POST /auth/distributor-register (012-register-default-dept)
# ──────────────────────────────────────────────────────────────────
@router.post("/distributor-register", status_code=201)
async def distributor_register(
    body: DistributorRegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Self-registration for new distributors (phone + password).

    Creates a User + Distributor auto-mounted to the default org.
    """
    svc = get_auth_service()
    result = await svc.distributor_register(
        db, body.phone, body.password, body.name
    )
    await db.commit()
    return _ok(result)


# ──────────────────────────────────────────────────────────────────
# POST /auth/bind-wechat
# ──────────────────────────────────────────────────────────────────
@router.post("/bind-wechat")
async def bind_wechat(
    body: BindWechatRequest,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """First-login WeChat binding for a distributor."""
    user_id = int(payload["sub"])
    svc = get_auth_service()
    result = await svc.bind_wechat(db, user_id, body.code)
    return _ok(result)


# ──────────────────────────────────────────────────────────────────
# POST /auth/admin-login
# ──────────────────────────────────────────────────────────────────
@router.post("/admin-login")
async def admin_login(
    body: AdminLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Admin account + password login."""
    svc = get_auth_service()
    result = await svc.admin_login(db, body.account, body.password)
    return _ok(result)


# ──────────────────────────────────────────────────────────────────
# POST /auth/phone-bind
# ──────────────────────────────────────────────────────────────────
@router.post("/phone-bind")
async def phone_bind(
    body: PhoneBindRequest,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """Bind a WeChat phone number to the current user.

    Requires a valid access token (Bearer).
    """
    from ...models.user import User
    from sqlalchemy import select

    user_id = int(payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if user is None:
        raise UnauthorizedException(message="Token invalid or malformed")

    svc = get_auth_service()
    masked_phone = await svc.phone_bind(db, user, body.code)

    await db.commit()
    return _ok({"phone": masked_phone})


# ──────────────────────────────────────────────────────────────────
# GET /auth/session
# ──────────────────────────────────────────────────────────────────
@router.get("/session")
async def get_session(
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """Return current user session info."""
    user_id = int(payload["sub"])
    user_type = payload.get("user_type", "promoter")
    token_exp = payload.get("exp", datetime.now(timezone.utc).timestamp() + 3600)

    svc = get_auth_service()
    result = await svc.get_session(db, user_id, user_type, token_exp)
    return _ok(result)


# ──────────────────────────────────────────────────────────────────
# POST /auth/refresh
# ──────────────────────────────────────────────────────────────────
@router.post("/refresh")
async def refresh_token(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Exchange a refresh token for a new access + refresh token pair."""
    svc = get_auth_service()
    result = await svc.refresh_token(db, body.refreshToken)
    await db.commit()
    return _ok(result)


# ──────────────────────────────────────────────────────────────────
# POST /auth/logout
# ──────────────────────────────────────────────────────────────────
@router.post("/logout")
async def logout(
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
    credentials=Depends(__import__("fastapi.security", fromlist=["HTTPBearer"]).HTTPBearer(auto_error=False)),
) -> dict:
    """Invalidate the current access token and all associated refresh tokens."""
    user_id = int(payload["sub"])
    token_str = credentials.credentials if credentials else ""

    svc = get_auth_service()
    await svc.logout(db, user_id, token_str)
    await db.commit()
    return _ok(None)
