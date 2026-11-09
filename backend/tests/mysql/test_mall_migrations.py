"""Migration contract for the disposable MySQL 8 schema only.

The legacy-023 fixture deliberately contains no mall data. This verifies that
    the mall revisions add the schema without manufacturing frozen performance
evidence for historical settlement rows.
"""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import inspect, text

MALL_TABLES = {
    "mall_categories",
    "mall_products",
    "mall_skus",
    "mall_stock_movements",
    "mall_addresses",
    "mall_cart_items",
    "mall_orders",
    "mall_order_items",
    "mall_shipments",
    "mall_aftersales",
    "mall_aftersale_items",
    "mall_payments",
    "mall_refunds",
    "mall_invoice_requests",
    "mall_invoices",
    "mall_reconciliation_batches",
    "mall_reconciliation_differences",
    "mall_finance_export_requests",
    "mall_files",
    "mall_commands",
    "mall_gateway_events",
    "mall_jobs",
    "mall_settings",
    "mall_consumptions",
    "performance_period_versions",
    "performance_evidence",
    "performance_evidence_sources",
    "performance_adjustments",
    "performance_adjustment_applications",
}

BACKEND = Path(__file__).resolve().parents[2]


async def test_mall_revisions_create_constrained_schema_without_legacy_backfill(mall_mysql_engine):
    async with mall_mysql_engine.connect() as connection:

        def inspect_schema(sync_connection):
            inspector = inspect(sync_connection)
            return {
                "tables": set(inspector.get_table_names()),
                "order_columns": {
                    item["name"]: item for item in inspector.get_columns("mall_orders")
                },
                "shipment_columns": {
                    item["name"]: item for item in inspector.get_columns("mall_shipments")
                },
                "notification_columns": {
                    item["name"]: item for item in inspector.get_columns("notifications")
                },
                "notification_category": next(
                    item["type"]
                    for item in inspector.get_columns("notifications")
                    if item["name"] == "category"
                ),
                "notification_indexes": {
                    item["name"]: item for item in inspector.get_indexes("notifications")
                },
                "mall_job_columns": {
                    item["name"]: item for item in inspector.get_columns("mall_jobs")
                },
                "address_columns": {
                    item["name"]: item for item in inspector.get_columns("mall_addresses")
                },
                "settlement_columns": {
                    item["name"]: item for item in inspector.get_columns("performance_settlements")
                },
                "payment_uniques": {
                    tuple(item["column_names"])
                    for item in inspector.get_unique_constraints("mall_payments")
                },
                "refund_uniques": {
                    tuple(item["column_names"])
                    for item in inspector.get_unique_constraints("mall_refunds")
                },
                "evidence_uniques": {
                    tuple(item["column_names"])
                    for item in inspector.get_unique_constraints("performance_evidence")
                },
                "order_checks": {
                    item["name"] for item in inspector.get_check_constraints("mall_orders")
                },
                "file_checks": {
                    item["name"] for item in inspector.get_check_constraints("mall_files")
                },
            }

        schema = await connection.run_sync(inspect_schema)
        assert MALL_TABLES <= schema["tables"]
        assert schema["order_columns"]["active_payment_id"]["nullable"]
        assert schema["order_columns"]["current_invoice_request_id"]["nullable"]
        assert schema["order_columns"]["close_requested_at"]["nullable"]
        assert schema["order_columns"]["close_request_reason"]["nullable"]
        assert schema["shipment_columns"]["auto_receive_at"]["nullable"]
        assert schema["address_columns"]["region_names"]["nullable"]
        for column in ("computed_revision", "input_digest", "evidence_version"):
            assert schema["settlement_columns"][column]["nullable"]
        assert ("order_id", "active_slot") in schema["payment_uniques"]
        assert ("aftersale_id", "active_slot") in schema["refund_uniques"]
        assert ("settlement_id", "distributor_id", "rule_type") in schema["evidence_uniques"]
        assert {"ck_mall_order_total", "ck_mall_order_refund"} <= schema["order_checks"]
        assert "ck_mall_file_purpose" in schema["file_checks"]
        assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == "036"
        assert schema["notification_columns"]["event_key"]["nullable"]
        assert schema["notification_columns"]["event_key"]["type"].length == 191
        assert schema["notification_category"].enums[-1] == "MALL"
        assert schema["notification_indexes"]["uq_notifications_event_key"]["unique"]
        assert {
            "notification_payload",
            "responsibility_role",
            "responsibility_first_discovered_at",
            "responsibility_last_verified_at",
            "responsibility_evidence",
            "responsibility_next_step",
            "resolution_code",
            "resolution_summary",
            "resolved_by_type",
            "resolved_by_id",
            "resolved_at",
        } <= set(schema["mall_job_columns"])
        scenes = await connection.run_sync(
            lambda sync: next(
                column["type"].enums
                for column in inspect(sync).get_columns("consent_records")
                if column["name"] == "scene"
            )
        )
        assert set(scenes) == {
            "REGISTRATION",
            "BINDING",
            "PROMOTION",
            "FOLLOWUP",
            "MALL_ADDRESS",
            "MALL_CHECKOUT",
            "MALL_INVOICE",
        }
        assert await connection.scalar(text("SELECT COUNT(*) FROM performance_evidence")) == 0


def test_mall_revisions_can_downgrade_and_reupgrade_owned_empty_schema():
    """Exercise reversible DDL only against the runner-owned disposable DB."""
    program = r"""
import os
from pathlib import Path
from unittest.mock import patch
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import create_async_engine
from src.core.config import get_settings
from tests.mall_fixtures import mysql_test_ssl

backend = Path(os.environ["MALL_BACKEND_ROOT"])
os.environ["DATABASE_URL"] = os.environ["MALL_TEST_DATABASE_URL"]
get_settings.cache_clear()
config = Config(str(backend / "alembic.ini"))
config.set_main_option("script_location", str(backend / "migrations"))

def tls_engine(*args, **kwargs):
    kwargs["connect_args"] = {"ssl": mysql_test_ssl()}
    return create_async_engine(*args, **kwargs)

with patch("sqlalchemy.ext.asyncio.create_async_engine", tls_engine):
    command.downgrade(config, "023")
    command.upgrade(config, "head")
"""
    env = os.environ.copy()
    env["MALL_BACKEND_ROOT"] = str(BACKEND)
    env["DATABASE_URL"] = env["MALL_TEST_DATABASE_URL"]
    result = subprocess.run(
        [sys.executable, "-c", program],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr[-1000:]
