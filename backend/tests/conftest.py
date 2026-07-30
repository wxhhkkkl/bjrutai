"""Shared test fixtures for contract and integration tests."""

import os
import sys
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import MagicMock, patch

# Prevent production engine creation at import time by providing a mock.
# The production database.py creates an engine with MySQL-specific pool
# settings that fail with SQLite.
_mock_engine = MagicMock()
_mock_engine.dispose = MagicMock()
sys.modules["src.core.database"] = MagicMock()

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Now build the real test engine and import models.
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestAsyncSession = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

# We need the real Base from database.py.  Since we mocked the module above,
# import it directly from the file path, bypassing the engine creation.
import importlib

# Remove the mock so we can import the real thing in a controlled way.
del sys.modules["src.core.database"]

# The database.py creates engine at top level.  We intercept this by setting
# the env var AND using a test-safe engine.  We still need the real Base class
# and get_db, so import after fixing the env.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

# Disable rate limiting in tests
os.environ["RATE_LIMIT_ENABLED"] = "false"

# Override create_async_engine in sqlalchemy.ext.asyncio temporarily so
# database.py's top-level call uses our test-safe parameters.
_original_create_async_engine = create_async_engine

def _safe_create_async_engine(url, **kwargs):
    kwargs.pop("pool_size", None)
    kwargs.pop("max_overflow", None)
    kwargs.pop("pool_recycle", None)
    kwargs.pop("pool_pre_ping", None)
    return _original_create_async_engine(url, **kwargs)

# Patch before importing src.core
import sqlalchemy.ext.asyncio as _sa_asyncio
_sa_asyncio.create_async_engine = _safe_create_async_engine

try:
    from src.core.database import Base, get_db
finally:
    _sa_asyncio.create_async_engine = _original_create_async_engine

from src.core.security import (
    create_access_token,
    create_refresh_token,
    get_password_hash,
)

# Ensure all models are imported so their tables are registered in Base.metadata
# before create_all() is called in the db_session fixture.
import src.models  # noqa: F401

from src.main import app

import tempfile

TEST_DB_DIR = tempfile.mkdtemp(prefix="bjrutai_test_")
TEST_DATABASE_URL = f"sqlite+aiosqlite:///{TEST_DB_DIR}/test.db"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)
TestAsyncSession = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create tables fresh for each test, yield session, then drop."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestAsyncSession() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Return an httpx AsyncClient that talks to the FastAPI app with test DB."""

    async def override_get_db():
        yield db_session

    # Override both get_db functions (core.database and api.deps)
    app.dependency_overrides[get_db] = override_get_db
    from src.api.deps import get_db as api_deps_get_db
    app.dependency_overrides[api_deps_get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
@pytest.fixture
def admin_auth_headers() -> dict:
    """Return headers with a valid admin JWT Bearer token."""
    token = make_access_token(user_id=1, user_type="admin")
    return {"Authorization": f"Bearer {token}"}


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# WeChat client mock
# ---------------------------------------------------------------------------
class MockWechatClient:
    """Mock WeChat client with configurable behavior."""

    def __init__(self):
        self._valid_codes: dict[str, dict] = {}
        self._should_fail: bool = False
        self._fail_message: str = "WeChat service error"

    def set_valid_code(
        self, code: str, openid: str, session_key: str = "test_session_key", unionid: str | None = None
    ):
        self._valid_codes[code] = {
            "openid": openid,
            "session_key": session_key,
            "unionid": unionid,
        }

    def set_should_fail(self, fail: bool = True, message: str = "WeChat service error"):
        self._should_fail = fail
        self._fail_message = message

    async def jscode2session(self, code: str) -> dict:
        if self._should_fail:
            raise Exception(self._fail_message)
        if code not in self._valid_codes:
            raise Exception("invalid code")
        return self._valid_codes[code]

    async def get_phone_number(self, code: str) -> str:
        if self._should_fail:
            raise Exception(self._fail_message)
        if code == "valid_phone_code":
            return "138****1234"
        raise Exception("invalid phone code")


@pytest.fixture
def mock_wechat_client() -> MockWechatClient:
    return MockWechatClient()


# ---------------------------------------------------------------------------
# Seed helpers for auth tests
# ---------------------------------------------------------------------------
async def seed_user(
    db: AsyncSession,
    *,
    openid: str = "test_openid_123",
    unionid: str | None = "test_unionid_123",
    user_type: str = "promoter",
    name: str | None = "测试用户",
    phone: str | None = None,
    phone_masked: str | None = None,
    avatar_url: str | None = "https://example.com/avatar.png",
    wechat_bound: bool = True,
    phone_authorized: bool = False,
    activation_status: str = "active",
) -> int:
    """Insert a User row and return its id."""
    from src.models.user import ActivationStatus, User, UserType

    user = User(
        openid=openid,
        user_type=UserType(user_type),
        name=name,
        phone=phone,
        phone_masked=phone_masked,
        avatar_url=avatar_url,
        wechat_bound=wechat_bound,
        phone_authorized=phone_authorized,
        activation_status=ActivationStatus(activation_status),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user.id


async def seed_admin(
    db: AsyncSession,
    *,
    username: str = "admin",
    password_plain: str = "testpass123",
    status: str = "active",
) -> int:
    """Insert an AdminAccount row and return its id."""
    from src.models.user import AdminAccount, AdminStatus

    admin = AdminAccount(
        username=username,
        password_hash=get_password_hash(password_plain),
        status=AdminStatus(status),
    )
    db.add(admin)
    await db.flush()
    await db.refresh(admin)
    return admin.id


async def seed_role(db: AsyncSession, *, name: str = "admin", permissions: dict | None = None) -> int:
    """Insert a Role row and return its id."""
    from src.models.role import Role

    role = Role(
        name=name,
        permissions=permissions or {"permissions": ["qualification.review", "admin.accounts.read"]},
    )
    db.add(role)
    await db.flush()
    await db.refresh(role)
    return role.id


async def seed_user_token(
    db: AsyncSession,
    *,
    user_id: int,
    token_hash: str,
    token_type: str = "refresh",
    family: str | None = None,
    is_revoked: bool = False,
    expires_in_days: int = 30,
) -> int:
    """Insert a UserToken row and return its id."""
    from datetime import timedelta

    from src.models.session import TokenType, UserToken

    token = UserToken(
        user_id=user_id,
        token_type=TokenType(token_type),
        token_hash=token_hash,
        family=family,
        expires_at=datetime.now(timezone.utc) + timedelta(days=expires_in_days),
        is_revoked=is_revoked,
    )
    db.add(token)
    await db.flush()
    await db.refresh(token)
    return token.id


async def seed_article(
    db: AsyncSession,
    *,
    title: str = "Test Article",
    content: str = "<p>Hello world</p>",
    summary: str | None = "A test article",
    status: str = "draft",
    category: str | None = "政策解读",
    author_name: str | None = "运营部",
    cover_url: str | None = None,
    tags: list | None = None,
    version: int = 1,
    published_at: datetime | None = None,
) -> int:
    """Insert an article row and return its id."""
    from src.models.article import Article, ArticleStatus

    article = Article(
        title=title,
        summary=summary,
        content=content,
        category=category,
        status=ArticleStatus(status),
        author_name=author_name,
        cover_url=cover_url,
        tags=tags,
        version=version,
        published_at=published_at,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(article)
    await db.flush()
    await db.refresh(article)
    return article.id


# ---------------------------------------------------------------------------
# Seed helpers for hierarchy / promoter / qualification
# ---------------------------------------------------------------------------
async def seed_hierarchy_node(
    db: AsyncSession,
    *,
    name: str = "测试节点",
    node_type: str = "promoter",
    parent_id: int | None = None,
    level: int = 1,
) -> int:
    """Insert a HierarchyNode row and return its id."""
    from src.models.hierarchy import HierarchyNode, NodeType

    node = HierarchyNode(
        name=name,
        node_type=NodeType(node_type),
        parent_id=parent_id,
        level=level,
    )
    db.add(node)
    await db.flush()
    await db.refresh(node)
    return node.id


async def seed_promoter(
    db: AsyncSession,
    *,
    user_id: int,
    node_id: int,
    qualification_status: str | None = None,
) -> int:
    """Insert a Promoter row and return its id."""
    from src.models.hierarchy import Promoter

    promoter = Promoter(
        user_id=user_id,
        node_id=node_id,
        qualification_status=qualification_status,
    )
    db.add(promoter)
    await db.flush()
    await db.refresh(promoter)
    return promoter.id


async def seed_qualification(
    db: AsyncSession,
    *,
    promoter_id: int,
    qualification_type: str = "enterprise",
    status: str = "draft",
    file_id: str | None = None,
    file_name: str | None = None,
    file_type: str | None = None,
    file_size: int | None = None,
    version: int = 1,
    submitted_at: datetime | None = None,
    approved_at: datetime | None = None,
    rejected_reason: str | None = None,
) -> int:
    """Insert a Qualification row and return its id."""
    from src.models.qualification import QualStatus, Qualification, QualificationType

    qual = Qualification(
        promoter_id=promoter_id,
        qualification_type=QualificationType(qualification_type),
        status=QualStatus(status),
        file_id=file_id,
        file_name=file_name,
        file_type=file_type,
        file_size=file_size,
        version=version,
        submitted_at=submitted_at,
        approved_at=approved_at,
        rejected_reason=rejected_reason,
    )
    db.add(qual)
    await db.flush()
    await db.refresh(qual)
    return qual.id


async def seed_promotion_code(
    db: AsyncSession,
    *,
    promoter_id: int,
    ref_token: str = "test_ref_token_abc123",
    source_code: str = "BJTR",
    status: str = "available",
    scan_count: int = 0,
    lead_count: int = 0,
    bind_count: int = 0,
) -> int:
    """Insert a PromotionCode row and return its id."""
    from src.models.promotion import PromotionCode, PromotionCodeStatus

    code = PromotionCode(
        promoter_id=promoter_id,
        ref_token=ref_token,
        source_code=source_code,
        status=PromotionCodeStatus(status),
        scan_count=scan_count,
        lead_count=lead_count,
        bind_count=bind_count,
    )
    db.add(code)
    await db.flush()
    await db.refresh(code)
    return code.id


# ---------------------------------------------------------------------------
# Helper: token factory
# ---------------------------------------------------------------------------
def make_access_token(user_id: int = 1, user_type: str = "promoter", **extra) -> str:
    return create_access_token(
        data={"sub": str(user_id), "user_type": user_type, **extra},
    )


def make_refresh_token(user_id: int = 1, user_type: str = "promoter", family: str = "family_001", jti: str = "1", **extra) -> str:
    return create_refresh_token(
        data={"sub": str(user_id), "user_type": user_type, "family": family, "jti": jti, **extra},
    )


def make_expired_token(user_id: int = 1, user_type: str = "promoter") -> str:
    from datetime import timedelta

    return create_access_token(
        data={"sub": str(user_id), "user_type": user_type},
        expires_delta=timedelta(seconds=-1),
    )


# ---------------------------------------------------------------------------
# Response envelope assertion
# ---------------------------------------------------------------------------
def assert_response_envelope(data: dict):
    """Verify unified response envelope {code, message, data, requestId, serverTime}."""
    assert "code" in data
    assert "message" in data
    assert "data" in data
    assert "requestId" in data
    assert "serverTime" in data
    assert isinstance(data["requestId"], str)
    assert isinstance(data["serverTime"], str)


# ---------------------------------------------------------------------------
# Mock builders (for contract/integration tests with mocked DB)
# ---------------------------------------------------------------------------
from unittest.mock import MagicMock


def make_mock_user(
    user_id: int = 1,
    openid: str = "test_openid_123",
    user_type: str = "promoter",
    name: str | None = "测试用户",
    phone: str | None = None,
    phone_masked: str | None = None,
    avatar_url: str | None = "https://example.com/avatar.png",
    wechat_bound: bool = True,
    phone_authorized: bool = False,
    activation_status: str = "active",
) -> MagicMock:
    u = MagicMock()
    u.id = user_id
    u.openid = openid
    # Make user_type behave like a string enum: .value returns the string
    u.user_type = user_type
    u.name = name
    u.phone = phone
    u.phone_masked = phone_masked
    u.avatar_url = avatar_url
    u.wechat_bound = wechat_bound
    u.phone_authorized = phone_authorized
    u.activation_status = activation_status
    u.created_at = datetime.now(timezone.utc)
    return u


def make_mock_admin(
    admin_id: int = 1,
    username: str = "admin",
    password_plain: str = "testpass123",
    status: str = "active",
) -> MagicMock:
    a = MagicMock()
    a.id = admin_id
    a.username = username
    a.password_hash = get_password_hash(password_plain)
    a.status = status
    a.locked_until = None
    # Store the plain password so verify_password can be tested
    a._plain_password = password_plain
    return a


def make_mock_role(name: str = "admin", permissions: dict | None = None) -> MagicMock:
    r = MagicMock()
    r.id = 1
    r.name = name
    r.permissions = permissions or {"permissions": ["qualification.review", "admin.accounts.read"]}
    return r


def make_mock_token(
    token_id: int = 1,
    user_id: int = 1,
    token_type: str = "refresh",
    token_hash: str = "hash_abc",
    family: str = "family_001",
    is_revoked: bool = False,
) -> MagicMock:
    from datetime import timedelta

    t = MagicMock()
    t.id = token_id
    t.user_id = user_id
    t.token_type = token_type
    t.token_hash = token_hash
    t.family = family
    t.is_revoked = is_revoked
    t.expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    return t


def mock_scalar_result(first_value=None, all_values=None):
    """Build a mock SQLAlchemy Result proxy."""
    result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.first = MagicMock(return_value=first_value)
    if all_values is not None:
        scalars_mock.all = MagicMock(return_value=all_values)
    result.scalars.return_value = scalars_mock
    return result
