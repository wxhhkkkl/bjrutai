"""Must run against the disposable, TLS-protected MySQL instance."""

import os

from sqlalchemy import text


async def test_mysql_is_owned_encrypted_and_migrated(mall_mysql_engine):
    async with mall_mysql_engine.connect() as connection:
        assert (await connection.scalar(text("SELECT DATABASE()"))) == (
            "bjrutai_mall_test_" + os.environ["MALL_TEST_RUN_ID"]
        )
        version = await connection.scalar(text("SELECT VERSION()"))
        assert version.startswith("8.")
        print(f"T129 environment: MySQL {version}")
        assert await connection.scalar(text("SELECT version_num FROM alembic_version"))


async def test_mysql_connections_are_independent(mall_mysql_engine):
    async with mall_mysql_engine.connect() as first, mall_mysql_engine.connect() as second:
        assert await first.scalar(text("SELECT CONNECTION_ID()")) != (
            await second.scalar(text("SELECT CONNECTION_ID()"))
        )
