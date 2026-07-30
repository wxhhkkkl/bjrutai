"""Pydantic schemas for auth endpoints."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────
# WeChat Login
# ──────────────────────────────────────────────
class WechatLoginRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=256)
    encryptedData: Optional[str] = Field(None, max_length=4096)
    iv: Optional[str] = Field(None, max_length=256)
    promoterCode: Optional[str] = Field(None, min_length=6, max_length=32)


class WechatUserInfo(BaseModel):
    userId: str
    openId: str
    unionId: Optional[str] = None
    nickname: Optional[str] = None
    avatarUrl: Optional[str] = None
    phone: Optional[str] = None
    role: str
    isNewUser: bool


class WechatLoginResponse(BaseModel):
    accessToken: str
    refreshToken: str
    expiresIn: int
    tokenType: str = "Bearer"
    user: WechatUserInfo


# ──────────────────────────────────────────────
# Admin Login
# ──────────────────────────────────────────────
class AdminLoginRequest(BaseModel):
    account: str = Field(..., min_length=4, max_length=64)
    password: str = Field(..., min_length=8, max_length=128)
    captchaToken: Optional[str] = Field(None, max_length=1024)


class AdminUserInfo(BaseModel):
    userId: str
    account: str
    displayName: Optional[str] = None
    role: str
    permissions: list[str] = []
    orgNodeId: Optional[str] = None
    orgNodeName: Optional[str] = None


class AdminLoginResponse(BaseModel):
    accessToken: str
    refreshToken: str
    expiresIn: int
    tokenType: str = "Bearer"
    user: AdminUserInfo


# ──────────────────────────────────────────────
# Phone Bind
# ──────────────────────────────────────────────
class PhoneBindRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=256)


class PhoneBindResponse(BaseModel):
    phone: str


# ──────────────────────────────────────────────
# Token Refresh
# ──────────────────────────────────────────────
class RefreshRequest(BaseModel):
    refreshToken: str = Field(..., min_length=1, max_length=2048)


class RefreshResponse(BaseModel):
    accessToken: str
    refreshToken: str
    expiresIn: int
    tokenType: str = "Bearer"


# ──────────────────────────────────────────────
# Session / Current User
# ──────────────────────────────────────────────
class SessionUser(BaseModel):
    userId: str
    openId: Optional[str] = None
    unionId: Optional[str] = None
    nickname: Optional[str] = None
    avatarUrl: Optional[str] = None
    phone: Optional[str] = None
    role: str
    orgNodeId: Optional[str] = None
    orgNodeName: Optional[str] = None


class SessionResponse(BaseModel):
    user: SessionUser
    tokenExpiresAt: str
    permissions: list[str] = []


# ──────────────────────────────────────────────
# Bootstrap
# ──────────────────────────────────────────────
class BootstrapResponse(BaseModel):
    session: Optional[SessionResponse] = None
    entry: Optional[dict] = None
    unreadNotificationCount: int = 0
    privacyAgreementVersion: Optional[str] = None
    workbenchSummary: Optional[dict] = None
    featureFlags: dict[str, Any] = {}


# ──────────────────────────────────────────────
# Generic response wrapper
# ──────────────────────────────────────────────
class ApiResponse(BaseModel):
    code: int = 0
    message: str = "success"
    data: Any = None
    requestId: str = ""
    serverTime: str = ""
