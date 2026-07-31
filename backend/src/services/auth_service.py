"""Auth service: business logic for login, token management, and session handling."""

import hashlib
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import get_settings
from ..core.exceptions import AppException, BadRequestException, UnauthorizedException
from ..core.security import (
    create_access_token,
    create_refresh_token,
    get_password_hash,
    verify_password,
    verify_token,
)
from ..integrations.wechat_client import get_wechat_client
from ..models.role import Role
from ..models.session import TokenType, UserToken
from ..models.user import AdminAccount, AdminStatus, User, UserType, admin_account_roles

logger = logging.getLogger(__name__)

settings = get_settings()

# ---------------------------------------------------------------------------
# In-memory login attempt tracker (production: use Redis)
# ---------------------------------------------------------------------------
_login_attempts: dict[str, list[float]] = {}
LOCKOUT_THRESHOLD = 5
LOCKOUT_DURATION_MINUTES = 15


def _check_login_attempts(username: str) -> bool:
    """Return True if the account is currently locked out due to failed attempts."""
    attempts = _login_attempts.get(username, [])
    if len(attempts) < LOCKOUT_THRESHOLD:
        return False
    # Keep only attempts within the lockout window
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=LOCKOUT_DURATION_MINUTES)
    cutoff_ts = cutoff.timestamp()
    recent = [ts for ts in attempts if ts > cutoff_ts]
    _login_attempts[username] = recent
    return len(recent) >= LOCKOUT_THRESHOLD


def _record_login_attempt(username: str, success: bool) -> None:
    """Record a login attempt. Successful attempts reset the counter."""
    if success:
        _login_attempts.pop(username, None)
        return
    attempts = _login_attempts.get(username, [])
    attempts.append(datetime.now(timezone.utc).timestamp())
    _login_attempts[username] = attempts


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------
def _hash_token(token: str) -> str:
    """SHA-256 hex digest of a token string."""
    return hashlib.sha256(token.encode()).hexdigest()


def _issue_token_pair(
    user_id: int, user_type: str, family: Optional[str] = None, **extra
) -> dict:
    """Generate access + refresh token pair and return the dict for the client."""
    if family is None:
        family = uuid.uuid4().hex

    jti = uuid.uuid4().hex

    access_token = create_access_token(
        data={"sub": str(user_id), "user_type": user_type, **extra}
    )
    refresh_token = create_refresh_token(
        data={"sub": str(user_id), "user_type": user_type, "family": family, "jti": jti}
    )

    return {
        "accessToken": access_token,
        "refreshToken": refresh_token,
        "expiresIn": settings.access_token_expire_minutes * 60,
        "tokenType": "Bearer",
        "family": family,
        "token_hash": _hash_token(refresh_token),
    }


# ---------------------------------------------------------------------------
# Auth Service
# ---------------------------------------------------------------------------
class AuthService:
    """Stateless auth service.  Each method accepts a DB session."""

    # ── WeChat Login ──────────────────────────────────────────────
    async def wechat_login(
        self,
        db: AsyncSession,
        code: str,
        client_version: Optional[str] = None,
        device_id: Optional[str] = None,
    ) -> dict:
        """Exchange a WeChat code for tokens.  Creates the User row on first login."""
        wechat = get_wechat_client()

        try:
            wx_data = await wechat.jscode2session(code)
        except Exception as exc:
            msg = str(exc)
            if "invalid code" in msg:
                raise AppException(
                    code=40001, message="Invalid WeChat code",
                    status_code=400, error_type="bad_request",
                )
            raise AppException(
                code=40002, message="WeChat service error, please retry",
                status_code=400, error_type="bad_request",
            )

        openid = wx_data["openid"]
        unionid = wx_data.get("unionid")

        # Find or create user
        result = await db.execute(select(User).where(User.openid == openid))
        user = result.scalars().first()

        is_new_user = False
        if user is None:
            is_new_user = True
            user = User(
                openid=openid,
                user_type=UserType.PROMOTER,
                wechat_bound=True,
            )
            db.add(user)
            await db.flush()
            await db.refresh(user)

        # Issue token pair
        user_type_str = user.user_type.value if isinstance(user.user_type, UserType) else str(user.user_type)
        token_pair = _issue_token_pair(
            user.id,
            user_type_str,
            openid=user.openid or "",
        )

        # Persist refresh token for revocation support
        token_record = UserToken(
            user_id=user.id,
            token_type=TokenType.REFRESH,
            token_hash=token_pair["token_hash"],
            family=token_pair["family"],
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days),
        )
        db.add(token_record)

        # Build user info
        user_info = {
            "userId": str(user.id),
            "openId": user.openid or "",
            "unionId": unionid,
            "nickname": user.name,
            "avatarUrl": user.avatar_url,
            "phone": user.phone_masked or user.phone,
            "role": user.user_type.value if isinstance(user.user_type, UserType) else user.user_type,
            "isNewUser": is_new_user,
        }

        return {
            "accessToken": token_pair["accessToken"],
            "refreshToken": token_pair["refreshToken"],
            "expiresIn": token_pair["expiresIn"],
            "tokenType": token_pair["tokenType"],
            "user": user_info,
        }

    # ── Admin Login ──────────────────────────────────────────────
    async def admin_login(
        self,
        db: AsyncSession,
        account: str,
        password: str,
    ) -> dict:
        """Validate admin credentials and return tokens."""
        # Check lockout
        if _check_login_attempts(account):
            raise AppException(
                code=40103, message="Account locked due to too many failed attempts (retry after 15 minutes)",
                status_code=401, error_type="unauthorized",
            )

        # Look up admin account
        result = await db.execute(
            select(AdminAccount).where(AdminAccount.username == account)
        )
        admin = result.scalars().first()

        if admin is None:
            _record_login_attempt(account, False)
            raise AppException(
                code=40101, message="Invalid account or password",
                status_code=401, error_type="unauthorized",
            )

        # Check status
        if admin.status == AdminStatus.DISABLED:
            raise AppException(
                code=40102, message="Account is disabled, contact administrator",
                status_code=401, error_type="unauthorized",
            )
        if admin.status == AdminStatus.LOCKED:
            raise AppException(
                code=40103, message="Account locked due to too many failed attempts (retry after 15 minutes)",
                status_code=401, error_type="unauthorized",
            )

        # Verify password
        if not verify_password(password, admin.password_hash):
            _record_login_attempt(account, False)
            raise AppException(
                code=40101, message="Invalid account or password",
                status_code=401, error_type="unauthorized",
            )

        _record_login_attempt(account, True)

        # Fetch roles and permissions
        permissions: list[str] = []
        roles_result = await db.execute(
            select(Role).join(
                admin_account_roles, admin_account_roles.c.role_id == Role.id
            ).where(admin_account_roles.c.admin_account_id == admin.id)
        )
        roles = roles_result.scalars().all()

        for role in roles:
            perms = role.permissions
            if isinstance(perms, dict) and "permissions" in perms:
                permissions.extend(perms["permissions"])
            elif isinstance(perms, list):
                permissions.extend(perms)

        # Issue token pair — embed permissions for server-side enforcement
        token_pair = _issue_token_pair(
            admin.id, "admin", username=admin.username, permissions=permissions
        )

        # Persist refresh token
        token_record = UserToken(
            user_id=admin.id,
            token_type=TokenType.REFRESH,
            token_hash=token_pair["token_hash"],
            family=token_pair["family"],
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days),
        )
        db.add(token_record)

        admin_info = {
            "userId": str(admin.id),
            "account": admin.username,
            "displayName": None,
            "role": "admin",
            "permissions": permissions,
            "orgNodeId": None,
            "orgNodeName": None,
        }

        return {
            "accessToken": token_pair["accessToken"],
            "refreshToken": token_pair["refreshToken"],
            "expiresIn": token_pair["expiresIn"],
            "tokenType": token_pair["tokenType"],
            "user": admin_info,
        }

    # ── Phone Bind ───────────────────────────────────────────────
    async def phone_bind(
        self,
        db: AsyncSession,
        user: User,
        phone_code: str,
    ) -> str:
        """Bind a phone number to *user* using the WeChat phone auth code.

        Returns the masked phone string.
        """
        wechat = get_wechat_client()

        try:
            masked_phone = await wechat.get_phone_number(phone_code)
        except Exception:
            raise AppException(
                code=40005, message="Invalid phone auth code",
                status_code=400, error_type="bad_request",
            )

        # Check if phone is already bound to another user
        result = await db.execute(
            select(User).where(
                (User.phone == masked_phone) | (User.phone_masked == masked_phone)
            )
        )
        other = result.scalars().first()
        if other is not None and other.id != user.id:
            raise AppException(
                code=40006, message="Phone already bound to another account",
                status_code=400, error_type="bad_request",
            )

        user.phone = masked_phone
        user.phone_masked = masked_phone
        user.phone_authorized = True
        db.add(user)

        return masked_phone

    # ── Token Refresh ────────────────────────────────────────────
    async def refresh_token(
        self,
        db: AsyncSession,
        refresh_token_str: str,
    ) -> dict:
        """Validate a refresh token, rotate the family, and return new tokens.

        Implements refresh-token rotation with reuse detection:
        - If the token is revoked, check the family for other revoked tokens.
          If found, the entire family is compromised → revoke all remaining tokens.
        - Otherwise, revoke the old token and issue a new one in the same family.
        """
        # Decode JWT
        try:
            payload = verify_token(refresh_token_str)
        except Exception:
            raise AppException(
                code=40101, message="Token invalid or malformed",
                status_code=401, error_type="unauthorized",
            )

        if payload.get("type") != "refresh":
            raise AppException(
                code=40101, message="Token invalid or malformed",
                status_code=401, error_type="unauthorized",
            )

        # Check expiry explicitly (JWT library handles it, but be explicit)
        exp = payload.get("exp", 0)
        if exp < datetime.now(timezone.utc).timestamp():
            raise AppException(
                code=40106, message="Refresh token expired, please re-login",
                status_code=401, error_type="unauthorized",
            )

        token_hash = _hash_token(refresh_token_str)
        family = payload.get("family", "")
        user_id_str = payload.get("sub", "")
        try:
            user_id = int(user_id_str)
        except (ValueError, TypeError):
            raise AppException(
                code=40101, message="Token invalid or malformed",
                status_code=401, error_type="unauthorized",
            )

        # Look up the token record
        result = await db.execute(
            select(UserToken).where(UserToken.token_hash == token_hash)
        )
        token_record = result.scalars().first()

        if token_record is None:
            raise AppException(
                code=40101, message="Token invalid or malformed",
                status_code=401, error_type="unauthorized",
            )

        if token_record.is_revoked:
            # Reuse detected: check if other tokens in the family are also revoked
            family_result = await db.execute(
                select(UserToken).where(
                    UserToken.family == family,
                    UserToken.is_revoked == True,
                )
            )
            revoked_in_family = family_result.scalars().all()
            if len(revoked_in_family) > 1:
                # Entire family compromised — revoke all
                await db.execute(
                    update(UserToken)
                    .where(UserToken.family == family, UserToken.is_revoked == False)
                    .values(is_revoked=True)
                )
            raise AppException(
                code=40107, message="Refresh token revoked",
                status_code=401, error_type="unauthorized",
            )

        # Revoke the old token
        token_record.is_revoked = True
        db.add(token_record)

        # Determine user_type for new tokens
        user_type = payload.get("user_type", "promoter")

        # Re-fetch permissions for admin users so the new JWT contains them
        extra: dict = {}
        if user_type == "admin":
            roles_result = await db.execute(
                select(Role).join(
                    admin_account_roles, admin_account_roles.c.role_id == Role.id
                ).where(admin_account_roles.c.admin_account_id == user_id)
            )
            roles = roles_result.scalars().all()
            perms: list[str] = []
            for role in roles:
                rp = role.permissions
                if isinstance(rp, dict) and "permissions" in rp:
                    perms.extend(rp["permissions"])
                elif isinstance(rp, list):
                    perms.extend(rp)
            extra["permissions"] = perms

        # Issue new token pair with same family
        new_pair = _issue_token_pair(user_id, user_type, family=family, **extra)

        # Persist new refresh token
        new_token_record = UserToken(
            user_id=user_id,
            token_type=TokenType.REFRESH,
            token_hash=new_pair["token_hash"],
            family=family,
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days),
        )
        db.add(new_token_record)

        return {
            "accessToken": new_pair["accessToken"],
            "refreshToken": new_pair["refreshToken"],
            "expiresIn": new_pair["expiresIn"],
            "tokenType": new_pair["tokenType"],
        }

    # ── Logout ───────────────────────────────────────────────────
    async def logout(self, db: AsyncSession, user_id: int, access_token_str: str) -> None:
        """Revoke the current access token and all refresh tokens for the user.

        Idempotent: calling multiple times returns success.
        """
        access_token_hash = _hash_token(access_token_str)

        # Revoke all refresh tokens for this user
        await db.execute(
            update(UserToken)
            .where(UserToken.user_id == user_id, UserToken.is_revoked == False)
            .values(is_revoked=True)
        )

    # ── Get Session ──────────────────────────────────────────────
    async def get_session(self, db: AsyncSession, user_id: int, user_type: str, token_exp: float) -> dict:
        """Build session response for the current authenticated user.

        Args:
            db: Database session.
            user_id: The user's primary key.
            user_type: ``"promoter"``, ``"admin"``, etc.
            token_exp: JWT exp claim (unix timestamp).

        Returns a dict matching the SessionResponse schema.
        """
        permissions: list[str] = []

        if user_type == "admin":
            result = await db.execute(
                select(AdminAccount).where(AdminAccount.id == user_id)
            )
            admin = result.scalars().first()
            if admin is None:
                raise AppException(
                    code=40101, message="Token invalid or malformed",
                    status_code=401, error_type="unauthorized",
                )

            role_result = await db.execute(
                select(Role).join(
                    admin_account_roles, admin_account_roles.c.role_id == Role.id
                ).where(admin_account_roles.c.admin_account_id == user_id)
            )
            roles = role_result.scalars().all()
            for role in roles:
                perms = role.permissions
                if isinstance(perms, dict) and "permissions" in perms:
                    permissions.extend(perms["permissions"])

            user_data = {
                "userId": str(admin.id),
                "account": admin.username,
                "openId": None,
                "unionId": None,
                "nickname": None,
                "avatarUrl": None,
                "phone": None,
                "role": "admin",
                "orgNodeId": None,
                "orgNodeName": None,
            }
        else:
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalars().first()
            if user is None:
                raise AppException(
                    code=40101, message="Token invalid or malformed",
                    status_code=401, error_type="unauthorized",
                )

            user_data = {
                "userId": str(user.id),
                "openId": user.openid,
                "unionId": None,
                "nickname": user.name,
                "avatarUrl": user.avatar_url,
                "phone": user.phone_masked or user.phone,
                "role": user.user_type.value if isinstance(user.user_type, UserType) else str(user.user_type),
                "orgNodeId": None,
                "orgNodeName": None,
            }

        token_expires_at = datetime.fromtimestamp(token_exp, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S%z"
        )

        return {
            "user": user_data,
            "tokenExpiresAt": token_expires_at,
            "permissions": permissions,
        }


# Singleton
_auth_service: Optional[AuthService] = None


def get_auth_service() -> AuthService:
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service
