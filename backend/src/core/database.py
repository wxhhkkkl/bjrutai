from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

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
