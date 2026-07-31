from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

# ── Monkey-patch: aiomysql + PyMySQL >= 1.0 ping(reconnect) compatibility ──
# PyMySQL 1.x changed Connection.ping() to require ``reconnect`` argument.
# aiomysql 0.2.0 AsyncAdapt wraps this but doesn't pass the arg, causing:
#   TypeError: AsyncAdapt_aiomysql_connection.ping() missing 1 required
#   positional argument: 'reconnect'
# Fix: patch both aiomysql.Connection.ping (low-level) and
# AsyncAdapt_aiomysql_connection.ping (SQLAlchemy wrapper) to accept the kwarg.
import aiomysql  # type: ignore[import-untyped]
from sqlalchemy.dialects.mysql.aiomysql import AsyncAdapt_aiomysql_connection

# Patch 1: aiomysql's own Connection.ping — accept and discard ``reconnect``
_aiomysql_ping = aiomysql.Connection.ping


async def _patched_ping(self, reconnect: bool = True) -> None:  # noqa: FBT001
    """Discard the PyMySQL-1.x ``reconnect`` kwarg that aiomysql doesn't use."""
    return await _aiomysql_ping(self)


aiomysql.Connection.ping = _patched_ping  # type: ignore[method-assign]

# Patch 2: SQLAlchemy's AsyncAdapt wrapper — make ``reconnect`` optional
_async_ping = AsyncAdapt_aiomysql_connection.ping


def _patched_async_ping(self, reconnect: bool = True):
    return _async_ping(self, reconnect)


AsyncAdapt_aiomysql_connection.ping = _patched_async_ping  # type: ignore[method-assign]

from .config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    pool_size=20,
    max_overflow=10,
    pool_recycle=3600,
    pool_pre_ping=True,
    echo=False,
    # Tencent Cloud MySQL TLS configuration (T187):
    # When connecting to TencentDB for MySQL with SSL/TLS enabled, add:
    #   connect_args={
    #       "ssl": {
    #           "ssl_ca": "/path/to/tencentdb-ca-cert.pem",
    #           "check_hostname": True,
    #       }
    #   }
    # For aiomysql, pass ssl context via:
    #   connect_args={"ssl": {"ca": "/path/to/ca.pem", "check_hostname": True}}
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that provides an async database session."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
