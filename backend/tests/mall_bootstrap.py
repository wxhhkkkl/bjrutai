"""Prepare the owned test schema from its immutable legacy-023 DDL fixture."""

import asyncio
import os
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.mall_fixtures import mysql_test_ssl, owned_mysql_url

BACKEND = Path(__file__).resolve().parents[1]


async def bootstrap():
    url = owned_mysql_url()
    engine = create_async_engine(url, connect_args={"ssl": mysql_test_ssl()})
    try:
        async with engine.begin() as connection:
            cipher = (
                await connection.execute(text("SHOW SESSION STATUS LIKE 'Ssl_cipher'"))
            ).first()
            if not cipher or not cipher[1]:
                raise ValueError("test bootstrap requires TLS")
            if not (await connection.scalar(text("SELECT VERSION()"))).startswith("8."):
                raise ValueError("MySQL 8 is required")
            count = await connection.scalar(
                text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE()")
            )
            if count:
                raise ValueError("test bootstrap requires an empty, runner-created database")
            # The runner verified the container label and copied its CA before
            # providing the URL; only this empty database is initialized.
            await connection.execute(
                text(
                    "CREATE TABLE mall_test_owner (id INT PRIMARY KEY, run_id CHAR(32) NOT NULL, "
                    "owner_token CHAR(64) NOT NULL) ENGINE=InnoDB"
                )
            )
            await connection.execute(
                text("INSERT INTO mall_test_owner VALUES (1, :run, :token)"),
                {
                    "run": os.environ["MALL_TEST_RUN_ID"],
                    "token": os.environ["MALL_TEST_OWNER_TOKEN"],
                },
            )
            ddl = (BACKEND / "tests/fixtures/mall_legacy_023.sql").read_text()
            for statement in ddl.split(";\n"):
                if statement.strip():
                    await connection.exec_driver_sql(statement.strip())
            # 001 assumes pre-existing tables. This fixture is the 023 baseline;
            # it does NOT claim that migrations 001-023 were replayed on empty DB.
            await connection.execute(
                text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)")
            )
            await connection.execute(text("INSERT INTO alembic_version VALUES ('023')"))
    finally:
        await engine.dispose()


def main():
    asyncio.run(bootstrap())
    url = owned_mysql_url()
    os.environ["DATABASE_URL"] = url
    from src.core.config import get_settings

    get_settings.cache_clear()
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))

    def tls_engine(*args, **kwargs):
        kwargs["connect_args"] = {"ssl": mysql_test_ssl()}
        return create_async_engine(*args, **kwargs)

    # Only this test process injects TLS into the existing Alembic env factory.
    # No application deployment or production configuration is modified.
    with patch("sqlalchemy.ext.asyncio.create_async_engine", tls_engine):
        command.upgrade(config, "head")


if __name__ == "__main__":
    main()
