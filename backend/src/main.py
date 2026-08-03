import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from .core.config import get_settings
from .core.error_handler import register_error_handlers
from .core.logging_middleware import LoggingMiddleware

logger = logging.getLogger(__name__)
settings = get_settings()


# ---------------------------------------------------------------------------
# Middleware – Idempotency
# ---------------------------------------------------------------------------
class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Minimal idempotency guard.

    For idempotent-safe methods (POST/PATCH/PUT) the client may supply an
    `Idempotency-Key` header.  This implementation stores successful
    responses keyed by that header, so that retried requests receive the
    original response instead of re-processing.

    Production note: replace the in-memory store with the database-backed
    IdempotencyKey model or a Redis cache.
    """

    def __init__(self, app):
        super().__init__(app)
        self._store: dict[str, dict] = {}

    async def dispatch(self, request: Request, call_next):
        idempotency_key = request.headers.get("Idempotency-Key")
        if idempotency_key is None or request.method not in ("POST", "PATCH", "PUT"):
            return await call_next(request)

        cached = self._store.get(idempotency_key)
        if cached is not None:
            from starlette.responses import Response

            return Response(
                content=cached["body"],
                status_code=cached["status_code"],
                headers=dict(cached["headers"]),
                media_type=cached.get("media_type"),
            )

        response = await call_next(request)

        if 200 <= response.status_code < 500:
            body = b""
            async for chunk in response.body_iterator:
                body += chunk

            self._store[idempotency_key] = {
                "body": body,
                "status_code": response.status_code,
                "headers": list(response.headers.items()),
                "media_type": response.media_type,
            }

            from starlette.responses import Response

            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        return response


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup — auto-create tables on first run (dev convenience)
    from .core.database import engine, Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed default admin account if none exists
    from .core.database import async_session
    from .core.security import get_password_hash
    from .models.user import AdminAccount, AdminStatus
    from sqlalchemy import select

    async with async_session() as seed_db:
        result = await seed_db.execute(select(AdminAccount).limit(1))
        if result.scalars().first() is None:
            admin = AdminAccount(
                username=settings.admin_default_username,
                password_hash=get_password_hash(settings.admin_default_password),
                status=AdminStatus.ACTIVE,
            )
            seed_db.add(admin)
            await seed_db.commit()
            logger.info(
                "Default admin account created: username=%s",
                settings.admin_default_username,
            )

        # T019: Seed system admin role and assign to default admin (idempotent)
        from .services.seed_service import seed_default_category, seed_system_admin_role
        await seed_system_admin_role(seed_db)
        await seed_default_category(seed_db)
        await seed_db.commit()

    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger

        scheduler = AsyncIOScheduler()
        scheduler.start()
        app.state.scheduler = scheduler

        # T116a: Bind user polling — every 60 seconds
        from .tasks.sync_tasks import (
            retry_failed_sync_job,
            sync_bind_users_job,
            sync_user_bills_job,
        )
        scheduler.add_job(
            sync_bind_users_job,
            trigger=IntervalTrigger(seconds=60),
            id="sync_bind_users",
            name="Poll Rutai getBindUser every 60s",
            coalesce=True,
            max_instances=1,
            replace_existing=True,
        )

        # T116b: User bill sync — every 5 minutes (after new bindings accumulate)
        scheduler.add_job(
            sync_user_bills_job,
            trigger=IntervalTrigger(minutes=5),
            id="sync_user_bills",
            name="Fetch bills for bound users",
            coalesce=True,
            max_instances=1,
            replace_existing=True,
        )

        # T116d: Retry failed sync — every 10 minutes
        scheduler.add_job(
            retry_failed_sync_job,
            trigger=IntervalTrigger(minutes=10),
            id="retry_failed_sync",
            name="Retry failed sync operations",
            coalesce=True,
            max_instances=1,
            replace_existing=True,
        )

        # T116e: Monthly settlement — 1st day of month at 00:05
        from .tasks.settlement_task import monthly_settlement_job
        scheduler.add_job(
            monthly_settlement_job,
            trigger=CronTrigger(day=1, hour=0, minute=5),
            id="monthly_settlement",
            name="Monthly contribution settlement",
            coalesce=True,
            max_instances=1,
            replace_existing=True,
        )

        # T116c: Qualification expiry check — daily at 09:00
        from .tasks.maintenance_tasks import qualification_expiry_check_job
        scheduler.add_job(
            qualification_expiry_check_job,
            trigger=CronTrigger(hour=9, minute=0),
            id="qualification_expiry_check",
            name="Check expiring qualifications daily",
            coalesce=True,
            max_instances=1,
            replace_existing=True,
        )

        # T191: Idempotency key cleanup — every hour
        from .tasks.maintenance_tasks import idempotency_cleanup_job
        scheduler.add_job(
            idempotency_cleanup_job,
            trigger=IntervalTrigger(hours=1),
            id="idempotency_cleanup",
            name="Clean expired idempotency keys",
            coalesce=True,
            max_instances=1,
            replace_existing=True,
        )
    except ImportError:
        app.state.scheduler = None

    yield

    # Shutdown
    scheduler = getattr(app.state, "scheduler", None)
    if scheduler is not None:
        scheduler.shutdown()

    from .core.database import engine

    await engine.dispose()


app = FastAPI(
    title="北京儒泰分销管理系统",
    description="Beijing Rutai Distribution Management System API",
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Middleware registration
# ---------------------------------------------------------------------------
from .core.rate_limiter import RateLimitMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(IdempotencyMiddleware)
app.add_middleware(LoggingMiddleware)

# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------
register_error_handlers(app)


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
from .api.v1.admin_accounts import admin_accounts_router, admin_roles_router
from .api.v1.admin_organizations import router as admin_organizations_router
from .api.v1.admin_org_qualifications import router as admin_org_qualifications_router
from .api.v1.admin_distributors import router as admin_distributors_router
from .api.v1.admin_customers import router as admin_customers_router
from .api.v1.org_performance import router as org_performance_router
from .api.v1.admin_categories import router as admin_categories_router
from .api.v1.admin_articles import router as admin_articles_router
from .api.v1.cos_upload import router as cos_upload_router
from .api.v1.admin_sync import router as admin_sync_router
from .api.v1.articles import router as articles_router
from .api.v1.auth import router as auth_router
from .api.v1.app import router as app_router
from .api.v1.binding import router as binding_router
from .api.v1.compliance import agreements_router, consents_router, me_consents_router
from .api.v1.contributions import router as contributions_router
from .api.v1.customers import followups_router, router as customers_router
from .api.v1.customer_analysis import router as customer_analysis_router
from .api.v1.feedbacks import feedback_files_router, router as feedbacks_router
from .api.v1.health import router as health_router
from .api.v1.notifications import router as notifications_router
from .api.v1.promotions import router as promotions_router
from .api.v1.reports import router as reports_router
from .api.v1.sharing_rules import router as sharing_rules_router
from .api.v1.team import router as team_router
from .api.v1.users import router as users_router
from .api.v1.workbench import router as workbench_router

# Core / existing routers
app.include_router(auth_router, prefix="/api/v1")
app.include_router(app_router, prefix="/api/v1")
app.include_router(articles_router, prefix="/api/v1")
app.include_router(admin_categories_router, prefix="/api/v1")
app.include_router(admin_articles_router, prefix="/api/v1")
app.include_router(cos_upload_router, prefix="/api/v1")
app.include_router(admin_sync_router, prefix="/api/v1")
app.include_router(admin_accounts_router, prefix="/api/v1")
app.include_router(admin_roles_router, prefix="/api/v1")
app.include_router(admin_organizations_router, prefix="/api/v1")
app.include_router(admin_org_qualifications_router, prefix="/api/v1")
app.include_router(admin_distributors_router, prefix="/api/v1")
app.include_router(admin_customers_router, prefix="/api/v1")
app.include_router(org_performance_router, prefix="/api/v1")
app.include_router(binding_router, prefix="/api/v1")
app.include_router(promotions_router, prefix="/api/v1")
app.include_router(sharing_rules_router, prefix="/api/v1")
app.include_router(contributions_router, prefix="/api/v1")
app.include_router(team_router, prefix="/api/v1")
app.include_router(reports_router, prefix="/api/v1")

# New Phase 13 routers
app.include_router(users_router, prefix="/api/v1")
app.include_router(customers_router, prefix="/api/v1")
app.include_router(followups_router, prefix="/api/v1")
app.include_router(workbench_router, prefix="/api/v1")
app.include_router(agreements_router, prefix="/api/v1")
app.include_router(consents_router, prefix="/api/v1")
app.include_router(me_consents_router, prefix="/api/v1")
app.include_router(feedbacks_router, prefix="/api/v1")
app.include_router(feedback_files_router, prefix="/api/v1")
app.include_router(notifications_router, prefix="/api/v1")
app.include_router(customer_analysis_router, prefix="/api/v1")
app.include_router(health_router, prefix="/api/v1")
