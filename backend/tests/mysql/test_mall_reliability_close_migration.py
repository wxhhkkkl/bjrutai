"""An actual downgrade must preserve already-recorded close intent facts."""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import text

from src.models.mall_trade import MallOrder
from src.schemas.mall_checkout import OrderCancel
from src.services.mall_order_action_service import cancel_order
from tests.mysql.test_mall_reliability_payments import enable, local_order


async def test_lossy_downgrade_is_refused_with_a_real_close_fact(mall_mysql_sessions, monkeypatch):
    enable(monkeypatch)
    actor, identity, version = await local_order(mall_mysql_sessions)
    # The MySQL suite shares one disposable schema across cases. Downgrades
    # below 042 are structurally refused by 042's unconditional guard; clear
    # data that 044's and 046's guards would refuse to discard on the way so
    # the refusal under test is the 042 guard.
    async with mall_mysql_sessions() as db:
        await db.execute(
            text(
                "UPDATE mall_products "
                "SET supports_return = 1, return_instructions = ''"
            )
        )
        await db.execute(
            text(
                "DELETE FROM mall_invoices WHERE seller_identity IS NULL "
                "OR invoice_no IS NULL OR issued_at IS NULL"
            )
        )
        await db.commit()
    async with mall_mysql_sessions() as db:
        await cancel_order(
            db,
            actor,
            identity,
            OrderCancel(expectedVersion=version, reason="迁移测试取消"),
            key="mysql-close-migration-intent-001",
        )
        await db.commit()
    backend = Path(__file__).resolve().parents[2]
    program = r"""
import os
from unittest.mock import patch
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import create_async_engine
from src.core.config import get_settings
from tests.mall_fixtures import mysql_test_ssl
os.environ["DATABASE_URL"] = os.environ["MALL_TEST_DATABASE_URL"]
get_settings.cache_clear()
def tls_engine(*args, **kwargs):
    kwargs["connect_args"] = {"ssl": mysql_test_ssl()}
    return create_async_engine(*args, **kwargs)
with patch("sqlalchemy.ext.asyncio.create_async_engine", tls_engine):
    config = Config("alembic.ini")
    try:
        command.downgrade(config, "041")
    except RuntimeError as exc:
        if "Downgrade would discard product types" not in str(exc):
            raise
        # Restore the shared disposable schema after exercising the refusal.
        command.upgrade(config, "head")
        raise
"""
    result = subprocess.run(
        [sys.executable, "-c", program],
        cwd=backend,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert (
        result.returncode != 0
        and "Downgrade would discard product types" in result.stderr
    ), result.stderr[-1000:]
    async with mall_mysql_sessions() as db:
        assert await db.scalar(text("SELECT version_num FROM alembic_version")) == "049"
        order = await db.get(MallOrder, identity)
        assert order.close_requested_at and order.close_request_reason == "迁移测试取消"
