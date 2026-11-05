"""Real InnoDB fixtures; no fallback to SQLite or an application database."""

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.mall_fixtures import mysql_test_ssl, owned_mysql_url, verify_mysql_owner


@pytest_asyncio.fixture
async def mall_mysql_engine():
    url = owned_mysql_url()  # Fail before creating an engine or connecting.
    engine = create_async_engine(url, connect_args={"ssl": mysql_test_ssl()}, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            await verify_mysql_owner(connection)
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def mall_mysql_sessions(mall_mysql_engine):
    """Separate sessions for concurrency tests; only the runner owns teardown."""
    yield async_sessionmaker(mall_mysql_engine, expire_on_commit=False)
