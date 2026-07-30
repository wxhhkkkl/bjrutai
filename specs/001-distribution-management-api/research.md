# Research Document: 北京儒泰分销管理后端与API

**Branch**: `001-distribution-management-api` | **Date**: 2026-07-30
**Purpose**: Phase 0 research — technology choices, patterns, and implementation strategies for all 15 research topics.

---

## 1. FastAPI Project Structure

### Decision

Organize the backend as a domain-module monolith with three internal layers: **API routers → services → models**, with shared cross-cutting concerns in a `core/` package. No repository pattern. Follow the planned structure from `plan.md`:

```
backend/src/
├── models/          # SQLAlchemy ORM models (one file per domain)
├── schemas/         # Pydantic request/response schemas
├── api/v1/          # FastAPI routers (one file per domain)
├── api/deps.py      # Shared dependency injection
├── services/        # Business logic (one file per domain)
├── integrations/    # External API clients (rutai, wechat)
├── core/            # config, security, database, exceptions
└── tasks/           # APScheduler scheduled tasks
```

### Rationale

- **Single database, single team**: No need for a repository pattern or microservice complexity. Direct SQLAlchemy usage in services is simpler and more performant.
- **Domain-based modules**: Each business domain (auth, qualifications, binding, contributions, etc.) has its own router, service, and model. This keeps related code together and avoids monolithic files.
- **No repository layer**: Per constitution principle V (Simplicity/YAGNI), repository pattern adds unnecessary abstraction when the database is not being swapped. Services use SQLAlchemy sessions directly.
- **FastAPI's built-in DI** (`Depends`) for auth, DB sessions, and permission checks — no need for a separate DI framework.

### Alternatives Considered

| Alternative | Why Rejected |
|---|---|
| Django + DRF | Heavier framework, sync-first ORM, async support is bolted on. FastAPI's native async and OpenAPI generation are better fits for this API-heavy project. |
| Layered architecture with repositories | Adds indirection without benefit. SQLAlchemy session is already a unit-of-work abstraction. |
| Separate microservices per domain | Overkill for a single-team project. Adds deployment complexity, distributed transaction headaches, and inter-service communication overhead. |

### Implementation Notes

- **Application factory pattern**: Use a `create_app()` function that wires up routers, middleware, and lifecycle handlers. Enables testing with different configs.
- **Router prefixing**: All v1 routers mount at `/api/v1/` in a single `api/v1/__init__.py` that includes all sub-routers.
- **Shared dependencies** in `api/deps.py`: `get_db()` for async session, `get_current_user()` for auth, `require_role()` for RBAC, `require_idempotency()` for idempotency key validation.
- **Exception hierarchy**: Custom exceptions in `core/exceptions.py` that map to the unified response format `{code, message, data, requestId, serverTime}`.
- **Configuration**: Pydantic `BaseSettings` in `core/config.py` loading from environment variables with `.env` file support. All secrets (DB password, JWT secret, WeChat app secret, COS keys) from env vars or secrets manager.

---

## 2. SQLAlchemy 2.0 Async Patterns

### Decision

Use SQLAlchemy 2.0 async with `async_sessionmaker`, `selectinload` for eager loading, and explicit transaction boundaries. MySQL 8.0 driver: `asyncmy` (pure Python async, best performance for MySQL).

### Rationale

- **SQLAlchemy 2.0** is the current stable async API with full type hints support. The 1.x `Query` API is deprecated.
- **asyncmy driver**: Faster than `aiomysql` for MySQL async, actively maintained, used by major projects.
- **No lazy loading in async**: SQLAlchemy async does not support lazy loading (it would require implicit IO). All relationship loading must be eager (`selectinload`, `joinedload`) or explicit queries.
- **Async session per request**: FastAPI dependency yields an async session that is automatically closed after the request.

### Alternatives Considered

| Alternative | Why Rejected |
|---|---|
| Tortoise ORM | Less mature ecosystem, fewer production references, limited migration tooling vs Alembic. |
| SQLAlchemy 1.4 sync with `run_in_executor` | Defeats the purpose of async FastAPI. Thread pool overhead for DB queries. |
| `aiomysql` driver | Slower than `asyncmy` in benchmarks; asyncmy has native C extensions. |

### Implementation Notes

```python
# core/database.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

engine = create_async_engine(
    settings.database_url,       # mysql+asyncmy://user:pass@host:port/db
    echo=settings.debug,
    pool_size=20,                # Per constitution: remote Tencent Cloud MySQL
    max_overflow=10,
    pool_recycle=3600,           # Recycle connections before cloud LB timeout
    pool_pre_ping=True,          # Verify connections before use (cloud proxy)
    connect_args={
        "ssl": {"ssl_ca": settings.db_ssl_ca_path}  # TLS to Tencent Cloud
    }
)

AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
```

```python
# api/deps.py
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
```

**Relationship loading gotcha**: When querying entities with relationships, always use `selectinload()` or `joinedload()`:

```python
# Correct - eager loading
stmt = select(User).options(selectinload(User.qualifications)).where(User.id == user_id)
result = await session.execute(stmt)
user = result.scalar_one()

# Wrong in async - will raise MissingGreenlet error
user = await session.get(User, user_id)
print(user.qualifications)  # BOOM
```

**Alembic configuration**: Use `alembic.ini` with `sqlalchemy.url` pointing to the same async database URL. Alembic migrations run synchronously (it uses a sync engine internally for DDL).

---

## 3. WeChat Mini-Program Login

### Decision

Implement server-side `wx.login` code exchange by calling `https://api.weixin.qq.com/sns/jscode2session`. Store the returned `openid` and `unionid` (if available) as the unique user identifier. Create a new account on first login, return existing account on subsequent logins.

### Rationale

- **Code exchange must happen server-side**: The `wx.login` code can only be exchanged for `openid` using the app secret, which must never be exposed to the client.
- **`openid` is the stable user identifier** within a single mini-program. If we later need cross-app identification (e.g., with the Harbin mini-program), we use `unionid` (requires binding to the same WeChat Open Platform account).
- **Dual token on first login**: After code exchange, issue a JWT access token (short-lived, 2h) and a refresh token (long-lived, 30d). The access token is used for API calls; the refresh token is used to rotate tokens without re-login.

### Alternatives Considered

| Alternative | Why Rejected |
|---|---|
| Client-side token generation | Insecure — exposes app secret. WeChat requires server-side code exchange. |
| WeChat Open Platform SDK | Not needed for basic `jscode2session` — the endpoint is a simple GET request. SDK adds unnecessary dependency weight. |
| Only access token (no refresh) | Poor UX — users would need to re-login via `wx.login` every 2h, which triggers a WeChat modal. |

### Implementation Notes

```python
# integrations/wechat_client.py
class WeChatClient:
    def __init__(self, app_id: str, app_secret: str, http_client: httpx.AsyncClient):
        self.app_id = app_id
        self.app_secret = app_secret
        self.http_client = http_client

    async def code_to_session(self, code: str) -> dict:
        """Exchange wx.login code for openid, session_key, unionid."""
        url = "https://api.weixin.qq.com/sns/jscode2session"
        params = {
            "appid": self.app_id,
            "secret": self.app_secret,
            "js_code": code,
            "grant_type": "authorization_code"
        }
        response = await self.http_client.get(url, params=params)
        data = response.json()
        if "errcode" in data and data["errcode"] != 0:
            raise WeChatAPIError(data["errcode"], data.get("errmsg", ""))
        return data  # {openid, session_key, unionid?}

    async def get_phone_number(self, code: str) -> str:
        """Exchange getPhoneNumber code for phone number."""
        # Requires access_token from https://api.weixin.qq.com/cgi-bin/token
        access_token = await self._get_access_token()
        url = "https://api.weixin.qq.com/wxa/business/getuserphonenumber"
        params = {"access_token": access_token}
        body = {"code": code}
        response = await self.http_client.post(url, params=params, json=body)
        data = response.json()
        if data.get("errcode") != 0:
            raise WeChatAPIError(data["errcode"], data["errmsg"])
        return data["phone_info"]["purePhoneNumber"]
```

**Session key storage**: The `session_key` returned by `jscode2session` must be stored server-side (in Redis or DB) and associated with the user. It is used to decrypt `wx.getUserInfo` and phone number data. Never expose `session_key` to the client.

**Account creation flow**:
1. Client calls `wx.login()` → gets `code`
2. Client POSTs `code` to `POST /api/v1/auth/wechat-login`
3. Server calls `jscode2session` → gets `openid`
4. Server looks up user by `openid`:
   - Exists: issue tokens, return session with `isNewUser: false`
   - Does not exist: create user row, issue tokens, return session with `isNewUser: true` and `phoneBindingRequired: true`

---

## 4. JWT Authentication (Dual-Token)

### Decision

Use PyJWT with HS256 symmetric signing for both access tokens and refresh tokens. Access tokens: 2-hour expiry, no persistence (stateless validation). Refresh tokens: 30-day expiry, persisted in database with family-based rotation and revocation support.

### Rationale

- **HS256 symmetric signing**: Single-service architecture — no need for RS256 asymmetric keys. Simpler key management.
- **Access token stateless**: No DB lookup needed for every API call. Token payload contains `sub` (user_id), `identity_type`, `role`, and standard `exp`/`iat`. FastAPI dependency validates signature and expiry in microseconds.
- **Refresh token persisted**: Stored in `refresh_tokens` table with fields: `id`, `user_id`, `token_hash`, `family_id`, `status` (active/revoked/replaced), `expires_at`, `created_at`. This enables:
  - **Token rotation**: Each refresh replaces the old refresh token with a new one (old token marked as `replaced`). If a revoked token is used (replay attack), the entire token family is revoked.
  - **Revocation**: On logout, all tokens in the family are marked `revoked`.

### Alternatives Considered

| Alternative | Why Rejected |
|---|---|
| OAuth2 with external provider (Auth0, Keycloak) | Adds operational dependency for a single-tenant internal system. Not justified. |
| Access token with 30-day expiry, no refresh | Security risk — if a token leaks, the attacker has 30 days of access. Short-lived access tokens limit the blast radius. |
| Refresh token stateless (signed, no DB) | Cannot revoke individual tokens. User logout becomes impossible without server-side state. |

### Implementation Notes

```python
# core/security.py
from datetime import datetime, timedelta, timezone
import jwt

ALGORITHM = "HS256"

def create_access_token(user_id: str, identity_type: str, roles: list[str], expires_delta: timedelta = None) -> str:
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(hours=2))
    payload = {
        "sub": user_id,
        "type": "access",
        "identity": identity_type,
        "roles": roles,
        "iat": datetime.now(timezone.utc),
        "exp": expire,
        "jti": generate_unique_id()  # Unique token ID for potential blacklist
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=ALGORITHM)

def create_refresh_token(user_id: str) -> tuple[str, str]:
    """Returns (refresh_token_string, token_family_id)"""
    token_id = generate_unique_id()
    token = secrets.token_urlsafe(64)  # Opaque string, not JWT
    family_id = generate_unique_id()
    return token, token_id, family_id
```

**Token refresh endpoint logic** (`POST /api/v1/auth/refresh`):
1. Client sends old access token (Authorization header) and refresh token (body).
2. Server looks up refresh token by hash in DB.
3. Check: token must be `active`, not expired, and user must not be disabled.
4. Mark old refresh token as `replaced`.
5. Issue new access token and new refresh token (same `family_id`).
6. **Replay detection**: If a `replaced` or `revoked` token is used, revoke the entire family and force re-login.

**Token rotation rationale for mini-programs**: Mini-program tokens are stored in `wx.getStorageSync`, which has a non-zero risk of leakage. Rotation limits the window of abuse.

**Admin backend JWT**: Admin accounts use the same JWT mechanism but with `identity_type: "admin"` and the relevant RBAC roles in the token payload. Login is via username/password (bcrypt-hashed) instead of WeChat code exchange.

---

## 5. RBAC Implementation

### Decision

Implement RBAC with three database tables (`admin_accounts`, `roles`, `account_roles` join table) plus a `permissions` table defining granular permission strings. Use FastAPI dependency injection to enforce role checks at the router level. Permissions are loaded into the JWT token at login time for stateless checks.

### Rationale

- **FastAPI DI is ideal for RBAC**: A dependency `require_role("admin")` or `require_permission("qualification:review")` can be injected into any route. It reads the user from the JWT token (or fetches from DB if full permission list is needed), checks the required permission, and raises 403 if not authorized.
- **Roles are collections of permissions**: `role` table (id, name, description, is_system) + `permission` table (id, code, description, resource) + `role_permissions` join. Example permission codes: `qualification:review`, `binding:unbind`, `sharing:configure`, `report:view`, `report:export`.
- **Permissions in JWT**: Include a compact list of permission codes in the JWT access token so that most route-level checks are stateless. For admin operations that need real-time permission updates, the dependency can fall back to a DB query.
- **Super admin bypass**: Super admin account implicitly has all permissions regardless of role assignments.

### Alternatives Considered

| Alternative | Why Rejected |
|---|---|
| Casbin | Adds complexity (policy files, enforcer model). Overkill for a system with ~10 roles and ~20 permission types. |
| Only role-check (no granular permissions) | Insufficient — the spec requires different permissions for admin vs finance vs operations, not just coarse role buckets. |
| ABAC (Attribute-Based Access Control) | Unnecessary complexity. No attribute-based rules beyond what roles provide. |

### Implementation Notes

```python
# models/rbac.py
class AdminAccount(Base):
    __tablename__ = "admin_accounts"
    id = Column(String(64), primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_super_admin = Column(Boolean, default=False)
    locked_until = Column(DateTime, nullable=True)
    failed_login_attempts = Column(Integer, default=0)
    roles = relationship("Role", secondary="account_roles", back_populates="accounts")

class Role(Base):
    __tablename__ = "roles"
    id = Column(String(64), primary_key=True)
    name = Column(String(50), unique=True, nullable=False)  # admin, finance, operations
    description = Column(String(200))
    is_system = Column(Boolean, default=False)  # Cannot delete system roles
    permissions = relationship("Permission", secondary="role_permissions", back_populates="roles")

class Permission(Base):
    __tablename__ = "permissions"
    id = Column(String(64), primary_key=True)
    code = Column(String(100), unique=True, nullable=False)  # "qualification:review"
    description = Column(String(200))
    resource = Column(String(100))  # "qualification", "binding", "report"
```

```python
# api/deps.py
class PermissionChecker:
    def __init__(self, required_permissions: list[str]):
        self.required_permissions = required_permissions

    async def __call__(self, current_user: dict = Depends(get_current_admin_user)):
        if current_user.get("is_super_admin"):
            return current_user
        user_permissions = set(current_user.get("permissions", []))
        if not user_permissions.issuperset(self.required_permissions):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user

# Usage in router:
@router.post("/qualifications/{id}/review")
async def review_qualification(
    id: str,
    review: QualificationReviewRequest,
    admin: dict = Depends(PermissionChecker(["qualification:review"])),
    db: AsyncSession = Depends(get_db)
):
    ...
```

**Preset roles from spec**:

| Role | Permissions |
|---|---|
| 超级管理员 (Super Admin) | All permissions (implicit) |
| 管理员 (Admin) | `qualification:review`, `hierarchy:manage`, `binding:unbind`, `binding:transfer`, `sharing:configure`, `report:view`, `accounts:manage` |
| 财务 (Finance) | `report:view`, `report:export`, `contribution:adjust` |
| 运营 (Operations) | `articles:manage`, `notifications:manage` |

---

## 6. Idempotency Key Pattern

### Decision

Implement idempotency key validation as FastAPI middleware that intercepts requests with the `Idempotency-Key` header on POST/PUT/PATCH methods. Store idempotency results in the existing MySQL database using the `idempotency_keys` table with a 24-hour TTL enforced by an hourly cleanup task. No Redis dependency required.

### Rationale

- **Middleware over dependency**: Idempotency is a cross-cutting concern. Middleware ensures it's applied consistently to all write endpoints without requiring every developer to remember to add a dependency.
- **Database-backed (no Redis)**: Per constitution principle V (Simplicity/YAGNI), adding Redis solely for idempotency introduces unnecessary infrastructure complexity. The `idempotency_keys` table uses the same MySQL connection pool and adds negligible overhead for write-heavy endpoints (at most ~1ms additional latency per idempotent request). The tradeoff of avoiding an entire new service dependency is worth the marginal latency cost.
- **24-hour TTL**: Long enough to cover any reasonable retry window, short enough to prevent unbounded storage growth. An hourly cleanup task (`DELETE FROM idempotency_keys WHERE created_at < NOW() - INTERVAL 24 HOUR`) removes expired keys.
- **Stored response replay**: On a repeated idempotency key, return the original response (including response body) rather than just a conflict error. This makes retries completely transparent to the client.

### Alternatives Considered

| Alternative | Why Rejected |
|---|---|
| Redis-backed idempotency | Requires adding and maintaining a Redis instance. For the scale of this project (binding submissions, qualification uploads), the performance gain does not justify the operational complexity. |
| Per-endpoint dependency | Easy to forget. Middleware is a single enforcement point. |
| UUID-only validation (no stored response) | Returning 409 on duplicate key forces the client to handle retries differently from successful first attempts. Stored response replay is more robust. |

### Implementation Notes

```python
# middleware/idempotency.py
from fastapi import Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import json

IDEMPOTENCY_TTL_HOURS = 24

class IdempotencyMiddleware:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    async def __call__(self, request: Request, call_next):
        # Only apply to write methods
        if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return await call_next(request)

        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            if self._requires_idempotency(request.url.path):
                return Response(
                    content=json.dumps({"code": 400002, "message": "幂等键缺失"}),
                    status_code=400,
                    media_type="application/json"
                )
            return await call_next(request)

        user_id = self._get_user_id(request)
        cache_key = f"{user_id}:{idempotency_key}"

        # Check DB for existing idempotency record
        async with self.session_factory() as db:
            existing = await db.execute(
                select(IdempotencyKey).where(
                    IdempotencyKey.key == cache_key,
                    IdempotencyKey.created_at > func.now() - timedelta(hours=IDEMPOTENCY_TTL_HOURS)
                )
            )
            record = existing.scalar_one_or_none()
            if record:
                return Response(
                    content=record.response_body,
                    status_code=record.status_code,
                    headers=json.loads(record.response_headers),
                    media_type="application/json"
                )

        # First time: process the request
        response = await call_next(request)

        # Store only successful responses (2xx)
        if 200 <= response.status_code < 300:
            async with self.session_factory() as db:
                db.add(IdempotencyKey(
                    key=cache_key,
                    status_code=response.status_code,
                    response_body=response_body,
                    response_headers=json.dumps(dict(response.headers)),
                    created_at=func.now()
                ))
                await db.commit()

        return response
```

**Key scoping**: Idempotency keys must be scoped per user (prefix with `user_id`). This prevents one user's key from colliding with another's.

**Endpoints requiring idempotency** (from spec and API docs):
- `POST /api/v1/binding-requests` — binding submission
- `POST /api/v1/qualifications` — qualification submission
- `POST /api/v1/feedbacks` — feedback submission
- `POST /api/v1/qualification-files/upload-token` — upload token generation
- `POST /api/v1/promotion-code/refresh` — promotion code refresh

**Cleanup task**: An hourly APScheduler job deletes expired keys:
```sql
DELETE FROM idempotency_keys WHERE created_at < NOW() - INTERVAL 24 HOUR
```

---

## 7. Cursor-Based Pagination

### Decision

Use Base64-encoded JSON cursors with the pattern: `cursor = base64(json_encode({"id": row_id, "value": sort_value}))`. The API accepts `cursor` and `pageSize`, returns `items`, `nextCursor`, `hasMore`, and optionally `total`.

### Rationale

- **Spec requirement (FR-065)**: All list interfaces must use cursor pagination (`cursor/pageSize/nextCursor/hasMore`).
- **Stable under inserts**: Unlike offset pagination (LIMIT/OFFSET), cursor pagination does not skip or duplicate rows when items are inserted at the top of the list between page requests. This is critical for the getBindUser polling scenario where new data is constantly arriving.
- **Performance**: Cursor pagination uses `WHERE row_value > cursor_value ORDER BY row_value LIMIT page_size`, which is an index range scan. Offset pagination (`OFFSET N`) requires scanning and discarding N rows, which degrades linearly.
- **Total is optional**: Per the API spec, `total` should only be returned when the page genuinely needs it, to avoid expensive COUNT(*) queries on large datasets.

### Alternatives Considered

| Alternative | Why Rejected |
|---|---|
| Offset-based pagination (page/pageSize) | Instability under concurrent inserts; O(n) performance degradation with large offsets. |
| Relay-style cursors (GraphQL) | Unnecessary complexity. Base64 JSON is simpler and well-understood. |
| Keyset pagination without encoding | Exposes internal IDs. Encoded cursors are opaque to the client but decodable by the server. |

### Implementation Notes

```python
# schemas/pagination.py
import base64
import json
from pydantic import BaseModel
from typing import Generic, TypeVar, Optional

T = TypeVar("T")

class CursorParams(BaseModel):
    cursor: Optional[str] = None
    page_size: int = 20

class CursorPage(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: Optional[str] = None
    has_more: bool
    total: Optional[int] = None  # Only when requested/needed

def encode_cursor(field_value, row_id: str) -> str:
    """Encode sort value + row ID into opaque cursor."""
    payload = {"v": field_value, "id": row_id}
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()

def decode_cursor(cursor: str | None) -> tuple | None:
    """Decode cursor back to (field_value, row_id)."""
    if not cursor:
        return None
    payload = json.loads(base64.urlsafe_b64decode(cursor.encode()))
    return payload["v"], payload["id"]
```

**SQL pattern with SQLAlchemy**:

```python
async def paginate_cursor(
    session: AsyncSession,
    base_query: Select,
    sort_column,
    cursor: str | None,
    page_size: int,
    model_class,  # For the row ID
) -> CursorPage:
    # Decode cursor
    decoded = decode_cursor(cursor)
    if decoded:
        sort_value, row_id = decoded
        # WHERE (sort_col, id) > (cursor_value, cursor_id)
        base_query = base_query.where(
            or_(
                sort_column > sort_value,
                and_(sort_column == sort_value, model_class.id > row_id)
            )
        )

    # Fetch one extra to determine has_more
    base_query = base_query.order_by(sort_column.asc(), model_class.id.asc()).limit(page_size + 1)
    result = await session.execute(base_query)
    rows = result.scalars().all()

    has_more = len(rows) > page_size
    items = rows[:page_size]

    next_cursor = None
    if has_more and items:
        last = items[-1]
        next_cursor = encode_cursor(getattr(last, sort_column.key), last.id)

    return CursorPage(items=items, next_cursor=next_cursor, has_more=has_more)
```

**Composite cursor**: For lists that sort by multiple fields (e.g., `sort=recent` meaning `created_at DESC`), the cursor encodes all sort-relevant fields. The WHERE clause uses a row-value comparison tuple.

**Performance**: Ensure all sort columns are indexed. For common sort patterns:
- `created_at DESC` → index on `(created_at, id)`
- `name ASC` → index on `(name, id)`
- Multi-field sorts → composite index matching the sort order

---

## 8. Scheduled Tasks with APScheduler

### Decision

Integrate APScheduler 3.x with FastAPI using the `asyncio` scheduler backend. Start the scheduler in the FastAPI startup lifecycle event and shut it down in the shutdown event. Schedule tasks via `AsyncIOScheduler.add_job()` at startup.

### Rationale

- **FastAPI lifecycle integration**: FastAPI's `startup`/`shutdown` events are the natural place to start/stop background services. APScheduler's `AsyncIOScheduler` runs on the same asyncio event loop, so it doesn't interfere with request handling.
- **AsyncIOScheduler vs BackgroundScheduler**: `AsyncIOScheduler` runs jobs on the asyncio event loop, which is compatible with async SQLAlchemy sessions and async httpx calls. `BackgroundScheduler` uses threads, which would require separate sync DB connections.
- **APScheduler over Celery**: Celery requires a message broker (Redis/RabbitMQ) and separate worker processes. For the scheduled tasks in this project (two recurring jobs with 60s intervals), the operational overhead of Celery is not justified.

### Alternatives Considered

| Alternative | Why Rejected |
|---|---|
| Celery + Celery Beat | Operational complexity (broker, workers, beat scheduler). Only justified for heavy background job processing or distributed task queues. |
| `asyncio.create_task` with `asyncio.sleep` loop | No built-in error handling, job persistence, or cron scheduling. Reinventing the wheel. |
| systemd timers / cron | Not container-friendly. Would need separate cron containers. Harder to coordinate with the app lifecycle. |

### Implementation Notes

```python
# tasks/scheduler.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.ext.asyncio import AsyncSession

scheduler = AsyncIOScheduler()

def init_scheduler(session_factory):
    """Register all scheduled jobs. Called in FastAPI startup."""

    # Every 60 seconds: poll getBindUser
    scheduler.add_job(
        poll_bind_users,
        IntervalTrigger(seconds=60),
        args=[session_factory],
        id="poll_get_bind_user",
        name="Poll getBindUser for new Beijing-source users",
        replace_existing=True,
        coalesce=True,  # Skip if previous run is still going
        max_instances=1
    )

    # Every 60 seconds after getBindUser: process discovered users
    scheduler.add_job(
        sync_user_bills,
        IntervalTrigger(seconds=60),
        args=[session_factory],
        id="sync_user_bills",
        replace_existing=True,
        coalesce=True,
        max_instances=1
    )

    # Monthly settlement: 1st day of month at 00:05
    scheduler.add_job(
        monthly_settlement,
        CronTrigger(day=1, hour=0, minute=5),
        args=[session_factory],
        id="monthly_settlement",
        replace_existing=True,
        coalesce=True,
        max_instances=1
    )

    # Daily: check expiring qualifications (early morning)
    scheduler.add_job(
        check_expiring_qualifications,
        CronTrigger(hour=4, minute=0),
        args=[session_factory],
        id="check_expiring_qualifications",
        replace_existing=True
    )

    scheduler.start()
```

```python
# app startup (in create_app or main.py)
@app.on_event("startup")
async def startup():
    init_scheduler(AsyncSessionLocal)

@app.on_event("shutdown")
async def shutdown():
    scheduler.shutdown(wait=False)
```

**Coalescing (coalesce=True)**: Prevents job pile-up. If the previous 60s poll is still running when the next tick fires, the new execution is skipped. This is critical for the polling tasks, because a slow external API call should not cause overlapping executions.

**Error handling in jobs**: Each scheduled job function must have its own try/except. A single unhandled exception will cause APScheduler to stop running that job (unless `misfire_grace_time` is set).

```python
async def poll_bind_users(session_factory):
    try:
        async with session_factory() as session:
            # ... polling logic
            pass
    except Exception:
        logger.exception("poll_bind_users failed")
```

**Production consideration**: In a multi-worker deployment (multiple Docker containers), use APScheduler with a `SQLAlchemyJobStore` pointing to MySQL so that only one worker instance acquires each job. Alternatively, use a simpler approach: run a single scheduler container that only executes background tasks (not API requests).

---

## 9. External API Integration with httpx

### Decision

Use `httpx.AsyncClient` with a singleton pattern per external service (one client instance for Harbin Rutai API, one for WeChat API). Implement retry with exponential backoff, circuit breaker pattern (manual), timeout enforcement, and HMAC-SHA256 signing for the Harbin Rutai server-to-server calls.

### Rationale

- **httpx is the de facto async HTTP client for Python**: First-class async support, connection pooling, HTTP/2, timeouts. Maintained by the same team as `requests`.
- **Singleton client per service**: Reuses connection pools. The client is created at app startup and passed to service/integration classes via dependency injection.
- **Exponential backoff retry**: For transient failures (network errors, 5xx responses), retry with doubling delays: 1s, 2s, 4s, 8s (max 3 retries for bindBjUser per spec FR-017).
- **Circuit breaker**: Manual implementation — track consecutive failure count per external service. After 5 consecutive failures (matching FR-033), stop calling the service and alert the admin. Reset after a successful call.
- **HMAC-SHA256 signing**: Required by the API docs for Harbin Rutai interface calls. Follow the pattern: sign `method + path + timestamp + nonce + body_hash` with a shared secret.

### Alternatives Considered

| Alternative | Why Rejected |
|---|---|
| `aiohttp` | Less ergonomic API, no connection pooling as good as httpx. Community preference is shifting to httpx. |
| `tenacity` for retry (full library) | Overkill. A simple async retry decorator with exponential backoff is ~20 lines. |
| `pybreaker` for circuit breaker | Adds dependency. The failure-tracking pattern we need is simple: a counter per service with threshold. |

### Implementation Notes

```python
# integrations/rutai_client.py
import httpx
import hmac
import hashlib
import time
import secrets

class RutaiClient:
    def __init__(self, base_url: str, api_key: str, api_secret: str):
        self.base_url = base_url
        self.api_key = api_key
        self.api_secret = api_secret
        self.consecutive_failures = 0
        self.circuit_open = False
        self.client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(30.0, connect=10.0),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            headers={"Content-Type": "application/json"}
        )

    def _generate_signature(self, method: str, path: str, timestamp: str, nonce: str, body: str) -> str:
        """HMAC-SHA256 signature for server-to-server auth."""
        message = f"{method}\n{path}\n{timestamp}\n{nonce}\n{body}"
        return hmac.new(
            self.api_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()

    def _build_auth_headers(self, method: str, path: str, body: str | None = None) -> dict:
        timestamp = str(int(time.time()))
        nonce = secrets.token_hex(16)
        body_str = body if body else ""
        signature = self._generate_signature(method, path, timestamp, nonce, body_str)
        return {
            "X-Api-Key": self.api_key,
            "X-Timestamp": timestamp,
            "X-Nonce": nonce,
            "X-Signature": signature
        }

    async def _request_with_retry(self, method: str, path: str, json_body: dict | None = None, params: dict | None = None, max_retries: int = 3) -> dict:
        if self.circuit_open:
            raise CircuitBreakerOpenError("Harbin Rutai API circuit is open")

        body_str = json.dumps(json_body) if json_body else None
        headers = self._build_auth_headers(method, path, body_str)

        last_exception = None
        for attempt in range(max_retries + 1):
            try:
                response = await self.client.request(method, path, json=json_body, params=params, headers=headers)
                response.raise_for_status()
                self.consecutive_failures = 0
                return response.json()
            except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
                last_exception = e
                self.consecutive_failures += 1
                if self.consecutive_failures >= 5:
                    self.circuit_open = True
                    logger.critical("Harbin Rutai API circuit OPEN after 5 consecutive failures")
                if attempt < max_retries:
                    wait = 2 ** attempt  # 1s, 2s, 4s
                    await asyncio.sleep(wait)
            except Exception:
                # Network errors, DNS failures also count
                self.consecutive_failures += 1
                if attempt < max_retries:
                    await asyncio.sleep(2 ** attempt)

        raise RutaiAPIError(f"Request failed after {max_retries} retries: {last_exception}")
```

**Timeout configuration**:
- Connection timeout: 10 seconds (time to establish TCP/TLS)
- Read timeout: 30 seconds (time to receive response)
- Total timeout: 30 seconds

These values are generous enough for cloud API calls but prevent indefinite hanging. The `getBindUser` polling must complete within the 60-second window.

**Retry policy by endpoint** (per spec):
- `bindBjUser`: max 3 retries, 10-minute intervals (handled at the service layer, not httpx retry)
- `getBindUser`: 5 consecutive failures triggers admin alert
- `getUserBill`: 5 consecutive failures for same user triggers manual review flag
- Retry only on: 5xx, network errors, timeouts. Never retry on 4xx (client errors).

**WeChat API client**: Follow the same pattern but use WeChat-specific auth (access_token from `https://api.weixin.qq.com/cgi-bin/token`, cached with ~7000s TTL, refreshed 5 minutes before expiry).

```python
# integrations/wechat_client.py
class WeChatClient:
    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self._access_token: str | None = None
        self._token_expires_at: float = 0
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(15.0))

    async def _get_access_token(self) -> str:
        if self._access_token and time.time() < self._token_expires_at - 300:
            return self._access_token
        url = "https://api.weixin.qq.com/cgi-bin/token"
        params = {"grant_type": "client_credential", "appid": self.app_id, "secret": self.app_secret}
        resp = await self.client.get(url, params=params)
        data = resp.json()
        self._access_token = data["access_token"]
        self._token_expires_at = time.time() + data["expires_in"]
        return self._access_token
```

---

## 10. File Upload with Pre-Signed URLs (Tencent Cloud COS)

### Decision

Use server-generated pre-signed upload URLs for Tencent Cloud COS. The flow is: client requests upload token → server generates STSCredentials or pre-signed URL → client uploads directly to COS → client receives `fileId` (COS object key) → client passes `fileId` in subsequent API calls → server processes by reading from COS using SDK.

### Rationale

- **Client-to-COS direct upload**: Files (qualifications, avatars, feedback screenshots) never pass through the backend server. This saves bandwidth and server memory, and works within the 10MB file size limit from the spec.
- **Pre-signed URLs over STS**: For simple upload scenarios, pre-signed URLs are simpler than STS temporary credentials. The server generates a time-limited upload URL (e.g., 10-minute expiry) with the object key and required headers.
- **`fileId` pattern**: After upload, the client only stores and transmits a `fileId` (the COS object key). The server can generate pre-signed download URLs when the client needs to preview the file.
- **Tencent Cloud COS SDK**: `cos-python-sdk-v5` provides `CosS3Client` for generating pre-signed URLs and managing objects.

### Alternatives Considered

| Alternative | Why Rejected |
|---|---|
| Server-proxied upload (multipart through backend) | Wastes backend bandwidth; blocks async workers; harder to handle 10MB files. |
| STS temporary credentials | More secure for multi-file scenarios but more complex. Pre-signed URLs are sufficient for single-file uploads per request. |
| Direct COS SDK on client | Exposes COS credentials to the client. Never do this. |
| Alibaba Cloud OSS / AWS S3 | Spec specifies Tencent Cloud COS. |

### Implementation Notes

```python
# services/file_service.py
from qcloud_cos import CosConfig, CosS3Client
import uuid, time

class FileService:
    ALLOWED_TYPES = {
        "qualification": ["image/jpeg", "image/png", "application/pdf"],
        "avatar": ["image/jpeg", "image/png"],
        "feedback": ["image/jpeg", "image/png"]
    }
    MAX_SIZES = {
        "qualification": 10 * 1024 * 1024,  # 10MB
        "avatar": 2 * 1024 * 1024,          # 2MB
        "feedback": 5 * 1024 * 1024         # 5MB
    }

    def __init__(self, cos_client: CosS3Client, bucket: str):
        self.cos_client = cos_client
        self.bucket = bucket

    async def generate_upload_token(
        self, file_type: str, file_name: str, content_type: str, file_size: int, sha256: str | None = None
    ) -> dict:
        # Validate type and size
        if content_type not in self.ALLOWED_TYPES[file_type]:
            raise InvalidFileTypeError(f"不支持的文件类型: {content_type}")
        if file_size > self.MAX_SIZES[file_type]:
            raise FileTooLargeError(f"文件大小超过限制")

        # Generate unique object key
        ext = file_name.rsplit(".", 1)[-1] if "." in file_name else "bin"
        date_prefix = time.strftime("%Y/%m/%d")
        object_key = f"{file_type}/{date_prefix}/{uuid.uuid4().hex}.{ext}"

        # Generate pre-signed upload URL (10-minute expiry)
        upload_url = self.cos_client.get_presigned_url(
            Method="PUT",
            Bucket=self.bucket,
            Key=object_key,
            Expired=600  # 10 minutes
        )

        return {
            "fileId": object_key,
            "uploadUrl": upload_url,
            "headers": {
                "Content-Type": content_type,
                "Content-Length": str(file_size)
            },
            "expiresAt": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        }

    def generate_preview_url(self, object_key: str, expires: int = 600) -> str:
        """Generate a time-limited download/preview URL."""
        return self.cos_client.get_presigned_url(
            Method="GET",
            Bucket=self.bucket,
            Key=object_key,
            Expired=expires
        )
```

**File type limitations from spec (FR-006)**:
- Qualification files: JPG, PNG, PDF, max 10MB
- Avatar files: JPEG, PNG (from API docs)
- Feedback screenshots: images, max 3 files, up to 5MB each

**Upload flow per API docs**:
1. `POST /api/v1/qualification-files/upload-token` → returns `{fileId, uploadUrl, headers, expiresAt}`
2. Client `PUT`s the file to `uploadUrl` with the returned headers
3. Client uses `fileId` in `POST /api/v1/qualifications`

**COS bucket structure**:
```
{bucket}/
├── qualification/2026/07/30/{uuid}.pdf
├── avatar/2026/07/30/{uuid}.jpg
└── feedback/2026/07/30/{uuid}.png
```

Date-prefixed keys enable easy lifecycle management (e.g., archive old files, set bucket policies by prefix).

---

## 11. Data Masking

### Decision

Implement data masking at the serialization layer (Pydantic model serializers / response schema validators). Phone numbers mask middle 4 digits (`138****1028`). ID cards mask middle 10 digits (`110101********1234`). Never store plaintext values in API response logs. Sensitive full values are only returned when explicitly requested with a separate "view plaintext" endpoint that logs an audit record.

### Rationale

- **Spec requirement (FR-061)**: All list and detail endpoints must return masked data by default for phone numbers and ID cards.
- **Pydantic serializer level**: Masking in the response schema ensures it's applied consistently to every endpoint that returns these fields. No service-level masking logic scattered across endpoints.
- **Audit-gated plaintext access**: When an admin needs to view unmasked data (e.g., for customer verification), a separate endpoint or parameter triggers an audit log entry. This satisfies FR-063.
- **Never in logs**: Configure logging to never include phone, ID card, or access token in log output. Use a logging filter that redacts known sensitive field names.

### Alternatives Considered

| Alternative | Why Rejected |
|---|---|
| Database-level masking (MySQL views) | Couples masking logic to the database. Harder to maintain. Can't handle conditional masking (e.g., show plaintext to admins). |
| Service-layer masking | Duplicated logic across every service method that returns user/customer data. |
| Frontend masking | Insecure — plaintext data is still transmitted over the network. |

### Implementation Notes

```python
# schemas/masking.py
import re

def mask_phone(phone: str | None) -> str | None:
    """Mask middle 4 digits: 138****1028"""
    if not phone:
        return None
    if len(phone) == 11:
        return phone[:3] + "****" + phone[7:]
    return phone  # Non-standard format, return as-is (should not happen)

def mask_id_card(id_card: str | None) -> str | None:
    """Mask middle digits: 110101********1234"""
    if not id_card:
        return None
    if len(id_card) == 18:
        return id_card[:4] + "**********" + id_card[14:]
    if len(id_card) == 15:
        return id_card[:4] + "*******" + id_card[11:]
    return id_card  # Non-standard

def mask_rutai_user_id(uid: str | None) -> str | None:
    """Mask identifier: RT****4826"""
    if not uid:
        return None
    if len(uid) > 4:
        return uid[:2] + "****" + uid[-4:]
    return "****"
```

```python
# schemas/customer.py (Pydantic v2)
from pydantic import BaseModel, field_serializer

class CustomerSummaryResponse(BaseModel):
    customer_id: str
    name: str
    phone_masked: str
    avatar_url: str | None = None
    # ... other fields

    model_config = {"from_attributes": True}

    @field_serializer("phone_masked")
    def _mask_phone(cls, v):
        return mask_phone(v)
```

**Plaintext access pattern**:
```python
@router.get("/customers/{id}/sensitive-data")
async def get_customer_sensitive_data(
    id: str,
    reason: str,  # Required query param: reason for viewing plaintext
    admin: dict = Depends(PermissionChecker(["customer:view_sensitive"])),
    db: AsyncSession = Depends(get_db),
    audit_service: AuditService = Depends(get_audit_service)
):
    customer = await customer_service.get_by_id(db, id)
    # Log audit record
    await audit_service.log(
        action="view_sensitive_data",
        resource_type="customer",
        resource_id=id,
        operator_id=admin["sub"],
        detail={"reason": reason}
    )
    return {"phone": customer.phone, "id_card": customer.id_card}
```

**Logging filter**: Add a filter to the Python logging configuration that redacts sensitive fields:

```python
import re, logging

class SensitiveDataFilter(logging.Filter):
    PATTERNS = [
        (re.compile(r'(phone["\']?\s*[:=]\s*["\'])(\d{11})(["\'])'), r'\1***REDACTED***\3'),
        (re.compile(r'(idCard["\']?\s*[:=]\s*["\'])(\d{15,18})(["\'])'), r'\1***REDACTED***\3'),
        (re.compile(r'(accessToken["\']?\s*[:=]\s*["\'])([^"\']+)(["\'])'), r'\1***REDACTED***\3'),
    ]

    def filter(self, record):
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            for pattern, replacement in self.PATTERNS:
                record.msg = pattern.sub(replacement, record.msg)
        return True
```

---

## 12. Audit Logging

### Decision

Audit logs are written to a dedicated `audit_logs` table (separate from business tables) using MySQL table partitioning by year. All audit records are append-only (no UPDATE, no DELETE). The audit table schema is minimal and generic to accommodate all audit event types. Service-level `AuditService` provides a uniform `log(action, resource_type, resource_id, operator_id, detail)` interface.

### Rationale

- **Spec requirement (FR-063a)**: All audit logs must be permanently retained, never physically deleted. Partitioning by year enables efficient querying of recent data while keeping historical partitions manageable.
- **Append-only**: No updates or deletes on audit_logs. Database-level permissions should enforce this (REVOKE UPDATE, DELETE on audit_logs from the application user).
- **Generic schema**: A single audit_logs table with a JSON `detail` column for event-specific data avoids creating domain-specific audit tables. JSON is appropriate here because audit detail is write-once, read-rarely, and varies significantly by event type.
- **Separate from business tables**: Audit logging should not slow down business queries. Keeping audit logs in their own table avoids polluting business table statistics and allows independent indexing strategies.

### Alternatives Considered

| Alternative | Why Rejected |
|---|---|
| Domain-specific audit tables (e.g., `binding_audit_logs`, `qualification_audit_logs`) | Proliferation of similar tables. Harder to query across audit types. |
| Log file based audit (e.g., ELK stack) | Adds operational complexity. Not required for this project's scale. MySQL is sufficient. |
| Change Data Capture (CDC) with Debezium | Overkill. We want semantic audit records (who did what and why), not raw row-level changes. |
| No partitioning | Performance degradation as the table grows to millions of rows over years of permanent retention. |

### Implementation Notes

```python
# models/audit_log.py
from sqlalchemy import Column, String, Text, DateTime, JSON, Integer, Index

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(64), primary_key=True)
    action = Column(String(100), nullable=False, index=True)  # "qualification.review", "binding.unbind"
    resource_type = Column(String(50), nullable=False)  # "qualification", "binding", "customer"
    resource_id = Column(String(64), nullable=False, index=True)
    operator_id = Column(String(64), nullable=False, index=True)  # Who performed the action
    operator_name = Column(String(50))  # Denormalized for query convenience
    detail = Column(JSON, nullable=False)  # Event-specific payload
    ip_address = Column(String(45))  # IPv4 or IPv6
    user_agent = Column(String(500))
    created_at = Column(DateTime, nullable=False, index=True)

    __table_args__ = (
        Index("idx_audit_resource", "resource_type", "resource_id"),
        Index("idx_audit_created", "created_at"),
        {"mysql_partition_by": "RANGE (YEAR(created_at))"}
    )
```

**Partition management**: Create partitions programmatically in Alembic migrations or a startup task:

```sql
-- Partition template (run yearly)
ALTER TABLE audit_logs PARTITION BY RANGE (YEAR(created_at)) (
    PARTITION p2026 VALUES LESS THAN (2027),
    PARTITION p2027 VALUES LESS THAN (2028),
    PARTITION p2028 VALUES LESS THAN (2029),
    PARTITION p_future VALUES LESS THAN MAXVALUE
);
```

A scheduled yearly task (or manual operation) creates the next year's partition before the current year ends.

**AuditService**:

```python
# services/audit_service.py
class AuditService:
    async def log(
        self,
        session: AsyncSession,
        action: str,
        resource_type: str,
        resource_id: str,
        operator_id: str,
        detail: dict,
        ip_address: str | None = None,
        user_agent: str | None = None
    ) -> None:
        log_entry = AuditLog(
            id=generate_unique_id(),
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            operator_id=operator_id,
            detail=detail,
            ip_address=ip_address,
            user_agent=user_agent,
            created_at=datetime.now(timezone.utc)
        )
        session.add(log_entry)
        # Note: audit log is committed as part of the caller's transaction.
        # If the business operation fails and rolls back, so does the audit log.
```

**Audit event types** (from spec FR-063a):
- `binding.bind` / `binding.unbind` / `binding.transfer`: Customer binding operations
- `qualification.submit` / `qualification.approve` / `qualification.reject`: Qualification review
- `sharing_rule.create` / `sharing_rule.update` / `sharing_rule.disable`: Sharing rule changes
- `contribution.adjust`: Manual contribution adjustments (FR-039)
- `customer.view_sensitive`: Viewing unmasked customer data
- `customer.edit_sensitive`: Editing sensitive customer fields
- `account.login_failed` / `account.login` / `account.locked`: Login security events (FR-005b)
- `sync.error` / `sync.recovered`: Data sync errors and recovery

**Writing audit logs**: Audit logs should be written within the same transaction as the business operation. If the business operation rollback, the audit log rolls back too — this ensures no audit log exists for a failed operation.

---

## 13. Vue 3 + Vite Admin Project Setup

### Decision

Set up the admin frontend as a standalone Vite + Vue 3 project in the `admin/` directory. Use Element Plus for UI components, Pinia for state management, Vue Router for routing with auth guards, and Axios for HTTP requests with interceptor-based JWT refresh.

### Rationale

- **Vue 3 Composition API**: Per constitution. Better TypeScript support, better code organization, and the ecosystem standard.
- **Vite**: Significantly faster dev server and build times than Webpack. Native ESM support, HMR out of the box.
- **Element Plus**: Mature Vue 3 component library with Chinese-friendly defaults (i18n, form validation patterns). Well-suited for admin dashboards with tables, forms, and data display.
- **Pinia over Vuex**: Official Vue 3 state management. Simpler API, full TypeScript inference, no mutations/actions ceremony.
- **Axios interceptors for JWT refresh**: Centralized token management. The response interceptor detects 401 errors, attempts silent refresh using the refresh token, and retries the original request. Avoids every component having to handle token expiry.

### Alternatives Considered

| Alternative | Why Rejected |
|---|---|
| Nuxt 3 | SSR/SSG is unnecessary for an admin SPA behind login. Adds framework complexity without benefit. |
| Ant Design Vue | Less Chinese-ecosystem adoption than Element Plus. Element Plus has better documentation for the target developer community. |
| Vuex | Legacy. Pinia is the official recommendation for Vue 3. |
| Fetch API (no Axios) | No built-in interceptor pattern for token refresh. Axios interceptors are well-understood and robust. |

### Implementation Notes

**Project structure**:

```
admin/
├── src/
│   ├── api/                # Axios instance + per-module API functions
│   │   ├── index.js        # Axios instance with interceptors
│   │   ├── auth.js         # Login, refresh, logout API calls
│   │   ├── qualifications.js
│   │   ├── binding.js
│   │   └── ...
│   ├── components/         # Shared UI components
│   ├── pages/              # Page components per module
│   ├── stores/             # Pinia stores
│   │   ├── auth.js         # User state, tokens, login/logout actions
│   │   └── notification.js # Notification polling
│   ├── router/
│   │   └── index.js        # Route definitions with meta.auth, meta.roles
│   ├── utils/
│   │   └── request.js      # Axios wrapper helpers
│   ├── App.vue
│   └── main.js
├── index.html
├── vite.config.js
├── package.json
└── tests/
```

**Axios interceptor for JWT refresh**:

```javascript
// api/index.js
import axios from 'axios';
import { useAuthStore } from '@/stores/auth';
import router from '@/router';

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' }
});

// Request interceptor: attach access token
apiClient.interceptors.request.use(config => {
  const authStore = useAuthStore();
  if (authStore.accessToken) {
    config.headers.Authorization = `Bearer ${authStore.accessToken}`;
  }
  return config;
});

// Response interceptor: handle 401 and token refresh
let isRefreshing = false;
let failedQueue = [];

const processQueue = (error, token = null) => {
  failedQueue.forEach(prom => {
    if (error) prom.reject(error);
    else prom.resolve(token);
  });
  failedQueue = [];
};

apiClient.interceptors.response.use(
  response => response,
  async error => {
    const originalRequest = error.config;

    if (error.response?.status === 401 && !originalRequest._retry) {
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        }).then(token => {
          originalRequest.headers.Authorization = `Bearer ${token}`;
          return apiClient(originalRequest);
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      const authStore = useAuthStore();
      try {
        const newToken = await authStore.refreshToken();
        processQueue(null, newToken);
        originalRequest.headers.Authorization = `Bearer ${newToken}`;
        return apiClient(originalRequest);
      } catch (refreshError) {
        processQueue(refreshError, null);
        authStore.logout();
        router.push('/login');
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

export default apiClient;
```

**Router with auth guards**:

```javascript
// router/index.js
import { createRouter, createWebHistory } from 'vue-router';
import { useAuthStore } from '@/stores/auth';

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/pages/login/index.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/',
    component: () => import('@/pages/layout/index.vue'),
    meta: { requiresAuth: true },
    children: [
      { path: '', name: 'Dashboard', component: () => import('@/pages/dashboard/index.vue') },
      { path: 'hierarchy', name: 'Hierarchy', component: () => import('@/pages/hierarchy/index.vue'), meta: { permissions: ['hierarchy:manage'] } },
      { path: 'qualifications', name: 'Qualifications', component: () => import('@/pages/qualifications/index.vue'), meta: { permissions: ['qualification:review'] } },
      // ... other routes
    ]
  }
];

const router = createRouter({
  history: createWebHistory(),
  routes
});

router.beforeEach((to, from, next) => {
  const authStore = useAuthStore();
  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    next({ name: 'Login', query: { redirect: to.fullPath } });
  } else if (to.meta.permissions) {
    const hasPermission = to.meta.permissions.every(p => authStore.permissions.includes(p));
    if (!hasPermission) next({ name: 'Dashboard' });
    else next();
  } else {
    next();
  }
});

export default router;
```

**Pinia auth store**:

```javascript
// stores/auth.js
import { defineStore } from 'pinia';
import { loginApi, refreshApi, logoutApi } from '@/api/auth';

export const useAuthStore = defineStore('auth', {
  state: () => ({
    accessToken: localStorage.getItem('accessToken') || null,
    refreshToken: localStorage.getItem('refreshToken') || null,
    user: JSON.parse(localStorage.getItem('user') || 'null'),
    permissions: JSON.parse(localStorage.getItem('permissions') || '[]')
  }),
  getters: {
    isAuthenticated: state => !!state.accessToken,
    hasPermission: state => perm => state.permissions.includes(perm)
  },
  actions: {
    async login(username, password) { /* ... */ },
    async refreshToken() {
      const data = await refreshApi(this.refreshToken);
      this.accessToken = data.accessToken;
      this.refreshToken = data.refreshToken;
      localStorage.setItem('accessToken', data.accessToken);
      localStorage.setItem('refreshToken', data.refreshToken);
      return data.accessToken;
    },
    async logout() { /* ... */ }
  }
});
```

**Vite config**: Ensure the dev server proxies API requests to the backend:

```javascript
// vite.config.js
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  },
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) }
  }
});
```

---

## 14. Monthly Settlement Batch

### Decision

The monthly settlement cron job runs at 00:05 on the 1st of each month via APScheduler (`CronTrigger(day=1, hour=0, minute=5)`). It processes all `pending` contribution records from the previous month in batches of 500, updating their status to `settled` within a single transaction per batch. The job is idempotent (can be re-run safely) and records a `settlement_log` entry with batch metadata.

### Rationale

- **Off-peak execution**: Running at 00:05 (5 minutes after midnight on the 1st) avoids the high-traffic period and gives a 5-minute buffer for any end-of-month processing.
- **Batch processing**: Processing all records in a single transaction would lock the contribution table and risk transaction timeout. Batching (500 records per transaction) limits lock duration and allows partial progress.
- **Idempotent**: The settlement query filters by `status = 'pending' AND occurred_at BETWEEN {first_of_last_month} AND {last_of_last_month}`. Re-running the job will find no records (all are already `settled`).
- **5-minute margin**: The 5-minute delay ensures that any last-second bill syncs (from the 60s polling cycle) that occurred at 23:59:59 are included.

### Alternatives Considered

| Alternative | Why Rejected |
|---|---|
| Real-time settlement (mark settled immediately) | Spec requires batch settlement on the 1st of each month. Also, real-time settlement complicates adjustments — pending state allows corrections. |
| Single transaction for all records | Risk: large volume could cause a multi-minute transaction that blocks reads. Batch approach is safer. |
| External scheduler (cron, Kubernetes CronJob) | Requires separate deployment configuration. APScheduler within the app is simpler and sufficient. |

### Implementation Notes

```python
# tasks/settlement_task.py
import logging
from datetime import datetime, timedelta, timezone
from dateutil.relativedelta import relativedelta
from sqlalchemy import update, select
from sqlalchemy.ext.asyncio import AsyncSession

BATCH_SIZE = 500

async def monthly_settlement(session_factory):
    """Settle all pending contributions from the previous month."""
    logger = logging.getLogger("settlement")

    now = datetime.now(timezone.utc)
    first_of_current_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    first_of_last_month = first_of_current_month - relativedelta(months=1)
    last_of_last_month = first_of_current_month - timedelta(seconds=1)

    settlement_batch_id = generate_unique_id()
    total_settled = 0
    batch_number = 0

    async with session_factory() as session:
        # Create settlement log entry
        log = SettlementLog(
            id=settlement_batch_id,
            period_start=first_of_last_month,
            period_end=last_of_last_month,
            status="processing",
            started_at=now
        )
        session.add(log)
        await session.commit()

    while True:
        async with session_factory() as session:
            # Select pending contributions for last month (batch)
            stmt = (
                select(ContributionRecord)
                .where(
                    ContributionRecord.status == "pending",
                    ContributionRecord.occurred_at >= first_of_last_month,
                    ContributionRecord.occurred_at <= last_of_last_month
                )
                .limit(BATCH_SIZE)
                .with_for_update(skip_locked=True)  # Lock rows, skip already-locked
            )
            result = await session.execute(stmt)
            records = result.scalars().all()

            if not records:
                break

            # Update to settled
            ids = [r.id for r in records]
            update_stmt = (
                update(ContributionRecord)
                .where(ContributionRecord.id.in_(ids))
                .values(
                    status="settled",
                    settled_at=now,
                    settlement_batch_id=settlement_batch_id
                )
            )
            await session.execute(update_stmt)

            batch_number += 1
            total_settled += len(ids)
            await session.commit()

            logger.info(f"Settlement batch {batch_number}: settled {len(ids)} records")

    # Finalize settlement log
    async with session_factory() as session:
        log = await session.get(SettlementLog, settlement_batch_id)
        log.status = "completed"
        log.total_settled = total_settled
        log.batches = batch_number
        log.completed_at = datetime.now(timezone.utc)
        await session.commit()

    logger.info(f"Monthly settlement completed: {total_settled} records in {batch_number} batches")
```

**Idempotency guarantee**: `with_for_update(skip_locked=True)` ensures each batch locks and processes distinct rows. Since the query filters by `status = 'pending'`, re-running the job will find zero rows (all are already `settled`). If the job crashes mid-way, restarting will skip already-settled records and only process remaining `pending` ones.

**Contribution freeze during settlement**: While settlement is running, the `pending` contribution records being processed are locked row-by-row. This means:
- Reads of `settled` records are not blocked.
- Reads of `pending` records being settled will see them as `pending` until the batch commits.
- This is acceptable since settlement runs at 00:05 when traffic is minimal.

**Settlement log table**:

```python
class SettlementLog(Base):
    __tablename__ = "settlement_logs"
    id = Column(String(64), primary_key=True)
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    status = Column(String(20), nullable=False)  # processing, completed, failed
    total_settled = Column(Integer, default=0)
    batches = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
```

---

## 15. Database Connection Pooling (Remote Tencent Cloud MySQL)

### Decision

Configure SQLAlchemy async engine with `pool_size=20`, `max_overflow=10`, `pool_recycle=3600`, and `pool_pre_ping=True`. Use SSL/TLS for all connections to Tencent Cloud MySQL. The application connects using a dedicated database user with minimal required privileges.

### Rationale

- **Pool sizing**: `pool_size=20` (base connections) + `max_overflow=10` (peak connections) = max 30 connections. This is appropriate for a single-server deployment with estimated 500 concurrent users. Each FastAPI request holds a connection for ~10-50ms, so 20 connections can handle hundreds of concurrent requests through multiplexing.
- **`pool_recycle=3600`**: Tencent Cloud MySQL, like many cloud databases, has an idle connection timeout (typically 28800s for MySQL, but cloud proxies/LBs may enforce shorter timeouts). Recycling connections every hour ensures no stale connections that would fail on the next query.
- **`pool_pre_ping=True`**: Before using a connection from the pool, SQLAlchemy sends a `SELECT 1` to verify it's alive. This adds ~1ms overhead per checkout but prevents "MySQL server has gone away" errors after network blips or load balancer timeouts.
- **TLS/SSL**: Remote database connections must be encrypted. Tencent Cloud MySQL provides SSL certificates. Configure via `connect_args={"ssl": {"ssl_ca": "/path/to/ca.pem"}}`.

### Alternatives Considered

| Alternative | Why Rejected |
|---|---|
| Larger pool (50-100 connections) | MySQL connection overhead is low, but too many idle connections waste database memory. 30 max is sufficient. |
| No pool recycling | Cloud load balancers silently drop idle TCP connections. Without recycling, apps see "connection reset" errors. |
| Connection per request (no pooling) | Extreme overhead. Connection establishment (TCP + TLS + MySQL handshake) is ~50-100ms per request. |
| ProxySQL / connection pooler middleware | Adds operational complexity. SQLAlchemy's built-in pooling is sufficient for this scale. |

### Implementation Notes

```python
# core/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Database
    db_host: str = "localhost"
    db_port: int = 3306
    db_user: str = "app_user"
    db_password: str = ""
    db_name: str = "bjrutai"
    db_ssl_ca_path: str = "/etc/ssl/tencentcloud/ca.pem"

    @property
    def database_url(self) -> str:
        return (
            f"mysql+asyncmy://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
            f"?charset=utf8mb4"
        )

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
```

```python
# core/database.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_size=20,
    max_overflow=10,
    pool_recycle=3600,         # Recycle connections hourly
    pool_pre_ping=True,        # Verify connections before use
    pool_timeout=30,           # Wait up to 30s for a connection from pool
    connect_args={
        "ssl": {
            "ssl_ca": settings.db_ssl_ca_path
        },
        "charset": "utf8mb4",
        "server_settings": {
            "sql_mode": "TRADITIONAL"  # Strict SQL mode
        }
    }
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False  # Prevent DetachedInstanceError in async
)
```

**Database user privileges**: Create a dedicated MySQL user `app_user` with minimal privileges:

```sql
-- For application user (runtime)
CREATE USER 'app_user'@'%' IDENTIFIED BY 'strong_password' REQUIRE SSL;
GRANT SELECT, INSERT, UPDATE, DELETE ON bjrutai.* TO 'app_user'@'%';

-- For migration user (Alembic)
CREATE USER 'migration_user'@'%' IDENTIFIED BY 'migration_password' REQUIRE SSL;
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, DROP, INDEX ON bjrutai.* TO 'migration_user'@'%';

-- Revoke DELETE on audit_logs (permanent retention)
REVOKE DELETE ON bjrutai.audit_logs FROM 'app_user'@'%';
REVOKE UPDATE ON bjrutai.audit_logs FROM 'app_user'@'%';
```

**MySQL configuration checklist for Tencent Cloud**:
1. Enable SSL on the Tencent Cloud MySQL instance.
2. Download the CA certificate and mount it in the Docker container at `/etc/ssl/tencentcloud/ca.pem`.
3. Set `character-set-server=utf8mb4` and `collation-server=utf8mb4_unicode_ci` (required for Chinese text).
4. Enable `innodb_file_per_table=ON` (default) for predictable tablespace management.
5. Set `max_connections` to accommodate the application pool: `pool_size + max_overflow + 10 buffer = 30 + 10 = 40` minimum. Tencent Cloud default is typically much higher.
6. Enable `slow_query_log` and set `long_query_time=1` for monitoring.

**Docker deployment notes**:

```dockerfile
# backend/Dockerfile (excerpt)
FROM python:3.11-slim

# Install system dependencies for asyncmy
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/
COPY alembic.ini .
COPY migrations/ ./migrations/

# Copy SSL CA certificate for Tencent Cloud MySQL
COPY certs/ca.pem /etc/ssl/tencentcloud/ca.pem

EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Health check endpoint**: Include a `/health` endpoint that verifies database connectivity:

```python
@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "database": str(e)}
        )
```

---

## Summary of Key Decisions

| # | Topic | Decision |
|---|---|---|
| 1 | Project structure | Domain-module monolith: `models/` → `services/` → `api/v1/` + `core/` |
| 2 | Async DB driver | `asyncmy` with SQLAlchemy 2.0 async, `selectinload` for relationships |
| 3 | WeChat login | Server-side `jscode2session` exchange, `openid` as user identity |
| 4 | JWT auth | HS256 access token (2h, stateless) + opaque refresh token (30d, DB-persisted, family rotation) |
| 5 | RBAC | Roles + Permissions in DB, `PermissionChecker` FastAPI dependency, permissions in JWT |
| 6 | Idempotency | Middleware checking `Idempotency-Key` header, DB-backed with 24h TTL + hourly cleanup |
| 7 | Pagination | Base64-encoded JSON cursor, `(sort_col, id)` composite, `total` optional |
| 8 | Scheduled tasks | APScheduler `AsyncIOScheduler` with `IntervalTrigger` (60s) and `CronTrigger` (monthly 00:05) |
| 9 | External API (httpx) | Singleton `AsyncClient` per service, exponential backoff retry, HMAC-SHA256 signing, circuit breaker |
| 10 | File upload | Tencent COS pre-signed URL (PUT), `fileId` pattern, 10-min upload window |
| 11 | Data masking | Pydantic `@field_serializer` for phone (`138****1028`) and ID card (`110101********1234`), plaintext with audit |
| 12 | Audit logging | Single `audit_logs` table, JSON detail column, yearly partitioning, append-only, no DELETE |
| 13 | Vue admin | Vite + Vue 3 + Element Plus + Pinia, Axios interceptor for JWT refresh, router auth guards |
| 14 | Monthly settlement | APScheduler `CronTrigger`, batch of 500 records per transaction, `with_for_update(skip_locked=True)`, idempotent |
| 15 | DB pooling | `pool_size=20`, `max_overflow=10`, `pool_recycle=3600`, `pool_pre_ping=True`, SSL/TLS to Tencent Cloud |
