"""An actual downgrade must preserve already-recorded close intent facts."""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import null, text, update

from src.models.mall_trade import MallAddress, MallOrder, MallShipment
from src.schemas.mall_checkout import OrderCancel
from src.services.mall_order_action_service import cancel_order
from tests.mysql.test_mall_reliability_payments import enable, local_order


async def test_028_refuses_lossy_downgrade_with_a_real_close_fact(mall_mysql_sessions, monkeypatch):
    enable(monkeypatch)
    actor, identity, version = await local_order(mall_mysql_sessions)
    # The MySQL suite shares one disposable schema across cases. Clear data
    # from later migration 030 so its independent downgrade guard does not
    # stop this test before 028 is reached.
    async with mall_mysql_sessions() as db:
        await db.execute(update(MallAddress).values(region_names=null()))
        await db.execute(update(MallShipment).values(auto_receive_at=null()))
        await db.execute(text("DELETE FROM notifications WHERE category = 'MALL'"))
        await db.execute(text("UPDATE notifications SET event_key = NULL"))
        await db.execute(
            text(
                "DELETE FROM mall_jobs WHERE kind IN "
                "('mall_notification_deliver','mall_funds_unknown_responsibility')"
            )
        )
        await db.execute(text("UPDATE mall_jobs SET notification_payload = NULL"))
        await db.execute(
            text(
                "UPDATE mall_jobs SET responsibility_role = NULL, "
                "responsibility_first_discovered_at = NULL, "
                "responsibility_last_verified_at = NULL, responsibility_evidence = NULL, "
                "responsibility_next_step = NULL, resolution_code = NULL, "
                "resolution_summary = NULL, resolved_by_type = NULL, resolved_by_id = NULL, "
                "resolved_at = NULL"
            )
        )
        await db.execute(text("UPDATE mall_payments SET unknown_since = NULL"))
        await db.execute(text("UPDATE mall_refunds SET unknown_since = NULL"))
        await db.execute(text("DELETE FROM mall_finance_export_requests"))
        await db.execute(
            text("UPDATE mall_invoice_requests SET consent_record_id = NULL")
        )
        await db.execute(text("DELETE FROM consent_records WHERE scene = 'MALL_INVOICE'"))
        assert await db.scalar(
            text("SELECT COUNT(*) FROM mall_addresses WHERE region_names IS NOT NULL")
        ) == 0
        assert await db.scalar(
            text("SELECT COUNT(*) FROM mall_shipments WHERE auto_receive_at IS NOT NULL")
        ) == 0
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
        command.downgrade(config, "027")
    except RuntimeError as exc:
        if "Order close intent facts exist; refusing a lossy downgrade" not in str(exc):
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
        and "Order close intent facts exist; refusing a lossy downgrade" in result.stderr
    ), result.stderr[-1000:]
    async with mall_mysql_sessions() as db:
        assert await db.scalar(text("SELECT version_num FROM alembic_version")) == "037"
        order = await db.get(MallOrder, identity)
        assert order.close_requested_at and order.close_request_reason == "迁移测试取消"
