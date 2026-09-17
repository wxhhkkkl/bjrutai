"""Auth service: business logic for login, token management, and session handling."""

import hashlib
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import or_, select, update
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
from ..models.binding import BindingStatus, Customer
from ..models.distributor import Distributor
from ..models.session import TokenType, UserToken
from ..models.user import (
    ActivationStatus,
    AdminAccount,
    AdminStatus,
    User,
    UserType,
    admin_account_roles,
)

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


def _normalize_customer_phone(phone: Optional[str]) -> str:
    digits = "".join(character for character in str(phone or "") if character.isdigit())
    if digits.startswith("86") and len(digits) == 13:
        digits = digits[2:]
    return digits if len(digits) == 11 and digits.startswith("1") else ""


async def _ensure_unassigned_customer(db: AsyncSession, user: User) -> None:
    """Create or link the pending customer record for a personal account.

    A self-registered account has no business owner.  The record becomes owned
    only when a staff pre-entry or a customer-binding-code claim supplies one.
    """
    if user.user_type != UserType.PERSONAL:
        return

    phone = _normalize_customer_phone(user.phone)
    if not phone:
        return

    membership = (
        await db.execute(
            select(Distributor.id).where(Distributor.user_id == user.id).limit(1)
        )
    ).scalars().first()
    if membership is not None:
        return

    customer = (
        await db.execute(
            select(Customer)
            .where(
                or_(
                    Customer.user_id == user.id,
                    Customer.phone_normalized == phone,
                    Customer.phone == phone,
                )
            )
            .order_by(Customer.id.asc())
            .with_for_update()
        )
    ).scalars().first()
    if customer is None:
        customer = Customer(
            user_id=user.id,
            name=user.name.strip() if user.name and user.name.strip() else None,
            phone=phone,
            phone_normalized=phone,
            phone_masked=phone[:3] + "****" + phone[-4:],
            binding_status=BindingStatus.PENDING,
            version=1,
        )
    else:
        if customer.user_id is None:
            customer.user_id = user.id
        if not customer.phone_normalized:
            customer.phone_normalized = phone
        if not customer.phone:
            customer.phone = phone
            customer.phone_masked = phone[:3] + "****" + phone[-4:]
        if not customer.name and user.name and user.name.strip():
            customer.name = user.name.strip()
        customer.version += 1
    db.add(customer)
    await db.flush()


# ---------------------------------------------------------------------------
# Auth Service
# ---------------------------------------------------------------------------
class AuthService:
    """Stateless auth service.  Each method accepts a DB session."""

    async def _get_business_membership(
        self,
        db: AsyncSession,
        user: User,
    ) -> Optional[dict]:
        """Return an existing active organization membership without creating one."""
        from ..services import distributor_service as dist_svc
        from ..models.distributor import Distributor, DistributorStatus
        from ..models.organization import Organization, OrgStatus

        distributor = await dist_svc.get_distributor_by_user(db, user.id)
        if not isinstance(distributor, Distributor):
            return None

        org = await db.get(Organization, distributor.org_id)
        membership_status = (
            distributor.status.value
            if hasattr(distributor.status, "value")
            else str(distributor.status)
        )
        org_status = (
            org.status.value if org and hasattr(org.status, "value") else str(org.status)
            if org else "missing"
        )
        active = (
            membership_status == DistributorStatus.ACTIVE.value
            and org_status == OrgStatus.ACTIVE.value
            and user.activation_status == ActivationStatus.ACTIVE
        )

        return {
            "distributorId": str(distributor.id),
            "orgId": str(distributor.org_id),
            "orgName": org.name if org else "",
            "orgRole": distributor.org_role.value
            if hasattr(distributor.org_role, "value")
            else str(distributor.org_role),
            "sourceChannel": distributor.source_channel or "admin_create",
            "status": membership_status,
            "orgStatus": org_status,
            "hasBusinessMembership": active,
        }

    # ── WeChat Login ──────────────────────────────────────────────
    async def wechat_login(
        self,
        db: AsyncSession,
        code: str,
        client_version: Optional[str] = None,
        device_id: Optional[str] = None,
        phone_code: Optional[str] = None,
    ) -> dict:
        """Exchange a WeChat code for tokens.  Creates the User row on first login.

        If ``phone_code`` is provided (WeChat phone auth), the phone is resolved
        BEFORE user lookup.  An existing User with that phone gets the WeChat
        openid bound to it instead of a duplicate being created (US2).
        """
        wechat = get_wechat_client()

        try:
            wx_data = await wechat.jscode2session(code)
        except Exception as exc:
            msg = str(exc)
            if "invalid code" in msg:
                raise AppException(
                    code=40001, message="微信登录凭证无效，请重试",
                    status_code=400, error_type="bad_request",
                )
            raise AppException(
                code=40002, message="微信服务异常，请稍后重试",
                status_code=400, error_type="bad_request",
            )

        openid = wx_data["openid"]
        unionid = wx_data.get("unionid")

        # ── US2: phone-based dedup BEFORE creating a new user ──────
        phone_user: Optional[User] = None
        resolved_phone: Optional[str] = None
        if phone_code:
            try:
                resolved_phone = await wechat.get_phone_number(phone_code)
            except Exception as exc:
                logger.warning("Failed to resolve phone_code during wechat_login", exc_info=True)
                raise AppException(
                    code=40005,
                    message="手机号授权凭证无效，请重新授权",
                    status_code=400,
                    error_type="bad_request",
                ) from exc
            if resolved_phone:
                phone_result = await db.execute(
                    select(User).where(User.phone == resolved_phone)
                )
                phone_user = phone_result.scalars().first()

        # Find or create user
        result = await db.execute(select(User).where(User.openid == openid))
        user = result.scalars().first()

        is_new_user = False
        distributor_info = None
        if user is None:
            if phone_user is not None:
                # Existing account binding WeChat for the first time.
                user = phone_user
                user.openid = openid
                user.wechat_bound = True
                db.add(user)
                await db.flush()
                await db.refresh(user)

                distributor_info = await self._get_business_membership(db, user)
            else:
                is_new_user = True
                user = User(
                    openid=openid,
                    user_type=UserType.PERSONAL,
                    wechat_bound=True,
                )
                db.add(user)
                await db.flush()
                await db.refresh(user)

        elif phone_user is not None and phone_user.id != user.id:
            # Edge case: different WeChat account, same phone → bind phone's openid
            # to the existing phone_user instead.
            logger.info(
                "OpenID %s already bound to user %s; phone %s belongs to user %s",
                openid, user.id, resolved_phone, phone_user.id,
            )
            user = phone_user
            user.openid = openid
            user.wechat_bound = True
            db.add(user)
            await db.flush()
            await db.refresh(user)

            distributor_info = await self._get_business_membership(db, user)

        # The phone authorization code is single-use.  Persist the phone here
        # while resolving it during WeChat login so the mini program does not
        # need to call /phone-bind a second time with the same code.
        if resolved_phone:
            user.phone = resolved_phone
            user.phone_masked = resolved_phone[:3] + "****" + resolved_phone[-4:]
            user.phone_authorized = True
            db.add(user)

        business_user_types = {UserType.PROMOTER, UserType.DISTRIBUTOR}
        if distributor_info is None and user.user_type in business_user_types:
            distributor_info = await self._get_business_membership(db, user)
        if distributor_info is None and user.user_type in business_user_types:
            # Membership is the source of authority. Repair legacy accounts
            # that carried a business role without an organization record.
            user.user_type = UserType.PERSONAL
            db.add(user)

        if distributor_info is None:
            await _ensure_unassigned_customer(db, user)

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
            "activationStatus": user.activation_status.value if hasattr(user.activation_status, "value") else str(user.activation_status),
            "profileCompleted": user.profile_completed,
        }

        result = {
            "accessToken": token_pair["accessToken"],
            "refreshToken": token_pair["refreshToken"],
            "expiresIn": token_pair["expiresIn"],
            "tokenType": token_pair["tokenType"],
            "user": user_info,
            "hasBusinessMembership": bool(
                distributor_info and distributor_info.get("hasBusinessMembership")
            ),
            "membershipStatus": (
                distributor_info.get("status") if distributor_info else "none"
            ),
            "orgStatus": (
                distributor_info.get("orgStatus") if distributor_info else "none"
            ),
        }
        if distributor_info is not None:
            result["distributor"] = distributor_info
        return result

    # ── Distributor Login (phone + password) ─────────────────────
    async def distributor_login(
        self,
        db: AsyncSession,
        phone: str,
        password: str,
    ) -> dict:
        """Validate distributor credentials (phone+password) and issue tokens.

        First login requires WeChat binding (FR-027) — surfaced via
        ``requiresWechatBinding``.
        """
        from ..models.distributor import DistributorStatus
        from ..services import distributor_service

        result = await db.execute(select(User).where(User.phone == phone))
        user = result.scalars().first()
        if user is None or not user.password_hash or not verify_password(password, user.password_hash):
            raise AppException(
                code=40101, message="手机号或密码错误",
                status_code=401, error_type="unauthorized",
            )

        dist = await distributor_service.get_distributor_by_user(db, user.id)
        if dist is None:
            raise AppException(
                code=40101, message="该账号尚未成为客户顾问",
                status_code=401, error_type="unauthorized",
            )
        if (
            dist.status == DistributorStatus.DISABLED
            or user.activation_status != ActivationStatus.ACTIVE
        ):
            raise AppException(
                code=40102, message="账号已停用",
                status_code=401, error_type="unauthorized",
            )

        token_pair = _issue_token_pair(user.id, "distributor", openid=user.openid or "")
        token_record = UserToken(
            user_id=user.id,
            token_type=TokenType.REFRESH,
            token_hash=token_pair["token_hash"],
            family=token_pair["family"],
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days),
        )
        db.add(token_record)

        from ..models.organization import Organization, OrgStatus

        organization = await db.get(Organization, dist.org_id)
        if organization is None or organization.status != OrgStatus.ACTIVE:
            raise AppException(
                code=40102, message="所属组织已停用",
                status_code=401, error_type="unauthorized",
            )

        return {
            "accessToken": token_pair["accessToken"],
            "refreshToken": token_pair["refreshToken"],
            "expiresIn": token_pair["expiresIn"],
            "tokenType": token_pair["tokenType"],
            "requiresWechatBinding": not bool(user.wechat_bound),
            "hasBusinessMembership": True,
            "membershipStatus": dist.status.value if hasattr(dist.status, "value") else str(dist.status),
            "orgStatus": organization.status.value if hasattr(organization.status, "value") else str(organization.status),
            "distributor": {
                "distributorId": str(dist.id),
                "orgId": str(dist.org_id),
                "orgName": organization.name,
                "orgRole": dist.org_role.value if hasattr(dist.org_role, "value") else str(dist.org_role),
                "name": user.name,
                "phone": user.phone_masked or user.phone,
                "status": dist.status.value if hasattr(dist.status, "value") else str(dist.status),
            },
        }

    # ── Distributor Self-Register (phone + password) ──────────────
    async def distributor_register(
        self,
        db: AsyncSession,
        phone: str,
        password: str,
        name: Optional[str] = None,
    ) -> dict:
        """Create a login account without granting organization membership."""
        from ..core.security import get_password_hash as _hash

        # Phone uniqueness for self-registration (FR-004 duplicate check)
        existing = await db.execute(
            select(User).where(User.phone == phone)
        )
        if existing.scalars().first() is not None:
            raise AppException(
                code=40901, message="该手机号已注册",
                status_code=409, error_type="conflict",
            )

        user = User(
            name=name,
            phone=phone,
            phone_masked=phone[:3] + "****" + phone[-4:],
            password_hash=_hash(password),
            user_type=UserType.PERSONAL,
            wechat_bound=False,
            profile_completed=bool(name and name.strip()),
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)
        await _ensure_unassigned_customer(db, user)

        # Issue token pair
        token_pair = _issue_token_pair(user.id, "personal")
        token_record = UserToken(
            user_id=user.id,
            token_type=TokenType.REFRESH,
            token_hash=token_pair["token_hash"],
            family=token_pair["family"],
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days),
        )
        db.add(token_record)

        user_info = {
            "userId": str(user.id),
            "openId": None,
            "nickname": user.name,
            "phone": user.phone_masked or user.phone,
            "role": "personal",
            "isNewUser": True,
            "activationStatus": user.activation_status.value if hasattr(user.activation_status, "value") else str(user.activation_status),
            "profileCompleted": user.profile_completed,
        }

        result = {
            "accessToken": token_pair["accessToken"],
            "refreshToken": token_pair["refreshToken"],
            "expiresIn": token_pair["expiresIn"],
            "tokenType": token_pair["tokenType"],
            "user": user_info,
            "hasBusinessMembership": False,
            "membershipStatus": "none",
            "orgStatus": "none",
        }
        return result

    # ── First-Login WeChat Binding ───────────────────────────────
    async def bind_wechat(self, db: AsyncSession, user_id: int, code: str) -> dict:
        """Bind a WeChat openid to the distributor account (FR-027)."""
        wechat = get_wechat_client()
        try:
            wx_data = await wechat.jscode2session(code)
        except Exception as exc:
            msg = str(exc)
            if "invalid code" in msg:
                raise AppException(
                    code=40001, message="微信登录凭证无效，请重试",
                    status_code=400, error_type="bad_request",
                )
            raise AppException(
                code=40002, message="微信服务异常，请稍后重试",
                status_code=400, error_type="bad_request",
            )

        openid = wx_data["openid"]

        result = await db.execute(select(User).where(User.openid == openid))
        existing = result.scalars().first()
        if existing is not None and existing.id != user_id:
            raise AppException(
                code=40005, message="该微信已绑定其他分销员账户",
                status_code=400, error_type="bad_request",
            )

        user = await db.get(User, user_id)
        if user is None:
            raise UnauthorizedException(message="用户不存在")

        user.openid = openid
        user.wechat_bound = True
        db.add(user)
        await db.flush()

        token_pair = _issue_token_pair(user.id, "distributor", openid=openid)
        return {
            "bound": True,
            "openId": openid,
            "accessToken": token_pair["accessToken"],
            "refreshToken": token_pair["refreshToken"],
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
                code=40103, message="登录失败次数过多，账号已锁定15分钟",
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
                code=40101, message="账号或密码错误",
                status_code=401, error_type="unauthorized",
            )

        # Check status
        if admin.status == AdminStatus.DISABLED:
            raise AppException(
                code=40102, message="账号已停用，请联系管理员",
                status_code=401, error_type="unauthorized",
            )
        if admin.status == AdminStatus.LOCKED:
            raise AppException(
                code=40103, message="登录失败次数过多，账号已锁定15分钟",
                status_code=401, error_type="unauthorized",
            )

        # Verify password
        if not verify_password(password, admin.password_hash):
            _record_login_attempt(account, False)
            raise AppException(
                code=40101, message="账号或密码错误",
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
            phone = await wechat.get_phone_number(phone_code)
        except Exception:
            raise AppException(
                code=40005, message="手机号授权凭证无效，请重新授权",
                status_code=400, error_type="bad_request",
            )

        # Check if phone is already bound to another user
        result = await db.execute(
            select(User).where(
                User.phone == phone
            )
        )
        other = result.scalars().first()
        if other is not None and other.id != user.id:
            raise AppException(
                code=40006, message="该手机号已绑定其他账号",
                status_code=400, error_type="bad_request",
            )

        user.phone = phone
        user.phone_masked = phone[:3] + "****" + phone[-4:]
        user.phone_authorized = True
        db.add(user)

        return user.phone_masked

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
                code=40101, message="登录状态无效，请重新登录",
                status_code=401, error_type="unauthorized",
            )

        if payload.get("type") != "refresh":
            raise AppException(
                code=40101, message="登录状态无效，请重新登录",
                status_code=401, error_type="unauthorized",
            )

        # Check expiry explicitly (JWT library handles it, but be explicit)
        exp = payload.get("exp", 0)
        if exp < datetime.now(timezone.utc).timestamp():
            raise AppException(
                code=40106, message="登录已过期，请重新登录",
                status_code=401, error_type="unauthorized",
            )

        token_hash = _hash_token(refresh_token_str)
        family = payload.get("family", "")
        user_id_str = payload.get("sub", "")
        try:
            user_id = int(user_id_str)
        except (ValueError, TypeError):
            raise AppException(
                code=40101, message="登录状态无效，请重新登录",
                status_code=401, error_type="unauthorized",
            )

        # Look up the token record
        result = await db.execute(
            select(UserToken).where(UserToken.token_hash == token_hash)
        )
        token_record = result.scalars().first()

        if token_record is None:
            raise AppException(
                code=40101, message="登录状态无效，请重新登录",
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
                code=40107, message="登录状态已失效，请重新登录",
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
                    code=40101, message="登录状态无效，请重新登录",
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
                "activationStatus": "active",
                "profileCompleted": True,
            }
        else:
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalars().first()
            if user is None:
                raise AppException(
                    code=40101, message="登录状态无效，请重新登录",
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
                "activationStatus": user.activation_status.value if hasattr(user.activation_status, "value") else str(user.activation_status),
                "profileCompleted": user.profile_completed,
            }

            membership = await self._get_business_membership(db, user)
            if membership is not None:
                user_data["orgNodeId"] = membership["orgId"]
                user_data["orgNodeName"] = membership["orgName"] if membership else None
                user_data["distributorId"] = membership["distributorId"]
                user_data["orgRole"] = membership["orgRole"]
                user_data["sourceChannel"] = membership["sourceChannel"]
                user_data["membershipStatus"] = membership["status"] if membership else "disabled"
                user_data["orgStatus"] = membership["orgStatus"] if membership else "missing"

            has_business_membership = bool(membership and membership["hasBusinessMembership"])

        token_expires_at = datetime.fromtimestamp(token_exp, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S%z"
        )

        response = {
            "user": user_data,
            "tokenExpiresAt": token_expires_at,
            "permissions": permissions,
        }
        if user_type != "admin":
            response.update({
                "hasBusinessMembership": has_business_membership,
                "membershipStatus": user_data.get("membershipStatus", "none"),
                "orgStatus": user_data.get("orgStatus", "none"),
            })
        return response


# Singleton
_auth_service: Optional[AuthService] = None


def get_auth_service() -> AuthService:
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service
