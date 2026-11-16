"""Storage invariants for the mall; no channel or personal data is involved."""

import importlib
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import CheckConstraint, UniqueConstraint, insert
from sqlalchemy.dialects import mysql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateTable

MODULES = (
    "mall_catalog",
    "mall_trade",
    "mall_finance",
    "mall_operations",
    "mall_consumption",
    "performance_evidence",
    "performance_adjustment",
)
FEATURE = Path(__file__).resolve().parents[3] / "specs/022-independent-mall"


@pytest.fixture
def mall_tables():
    for module in MODULES:
        importlib.import_module("src.models." + module)
    from src.core.database import Base

    names = {
        name
        for group in json.loads((FEATURE / "tasks-map.json").read_text())["tables"].values()
        for name in group
    }
    return {name: Base.metadata.tables[name] for name in names}


def unique_sets(table):
    return {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def test_all_29_entities_are_mapped_with_exact_mysql_foreign_key_types(mall_tables):
    assert len(mall_tables) == 29
    dialect = mysql.dialect()
    for name, table in mall_tables.items():
        ddl = str(CreateTable(table).compile(dialect=dialect))
        assert "CREATE TABLE" in ddl
        if name != "performance_period_versions":
            assert "BIGINT UNSIGNED" in str(table.c.id.type.compile(dialect=dialect))
        for fk in table.foreign_keys:
            assert fk.parent.type.compile(dialect=dialect) == fk.column.type.compile(
                dialect=dialect
            )
            assert fk.ondelete != "CASCADE", (name, fk.parent.name)
        assert {"created_at", "updated_at"}.issubset(table.c.keys())


@pytest.mark.parametrize(
    "table,columns",
    [
        ("mall_payments", ("order_id", "active_slot")),
        ("mall_refunds", ("aftersale_id", "active_slot")),
        ("mall_aftersale_items", ("order_item_id", "active_slot")),
        ("mall_invoice_requests", ("order_id", "active_slot")),
        ("mall_stock_movements", ("sku_id", "event_key")),
        ("mall_commands", ("actor_type", "actor_id", "action", "key")),
        ("performance_evidence", ("settlement_id", "distributor_id", "rule_type")),
        (
            "performance_adjustments",
            ("evidence_id", "trigger_source_type", "trigger_source_id", "trigger_version"),
        ),
    ],
)
def test_activity_and_event_uniqueness_is_enforced_by_database(mall_tables, table, columns):
    assert columns in unique_sets(mall_tables[table])
    if "active_slot" in columns:
        assert mall_tables[table].c.active_slot.nullable


def test_missing_original_result_has_a_stable_evidence_identity(mall_tables):
    evidence = mall_tables["performance_evidence"]
    adjustments = mall_tables["performance_adjustments"]
    assert evidence.c.result_id.nullable and adjustments.c.origin_result_id.nullable
    assert not adjustments.c.evidence_id.nullable
    assert ("evidence_key",) in unique_sets(evidence)
    assert "result_presence" in evidence.c and "result_absence_reason" in evidence.c


def test_money_stock_and_quantity_have_database_checks(mall_tables):
    for name in ["mall_skus", "mall_orders", "mall_order_items", "mall_refunds", "mall_cart_items"]:
        assert any(isinstance(c, CheckConstraint) for c in mall_tables[name].constraints), name
    assert mall_tables["mall_consumptions"].c.customer_id.nullable
    assert mall_tables["mall_consumptions"].c.attributed_distributor_id.nullable
    assert "bill_id" not in mall_tables["mall_orders"].c


async def test_negative_available_stock_is_rejected(mall_tables, db_session):
    table = mall_tables["mall_skus"]
    with pytest.raises(IntegrityError, match="CHECK constraint failed"):
        await db_session.execute(
            insert(table).values(
                id=1,
                product_id=1,
                sku_code="negative-test",
                sale_price_cent=100,
                available_qty=-1,
                reserved_qty=0,
            )
        )
    await db_session.rollback()


async def test_refund_cannot_exceed_received_amount(mall_tables, db_session):
    with pytest.raises(IntegrityError, match="CHECK constraint failed"):
        await db_session.execute(
            insert(mall_tables["mall_orders"]).values(
                id=1,
                order_no="too-much-refund",
                buyer_user_id=1,
                goods_amount_cent=100,
                freight_amount_cent=0,
                payable_amount_cent=100,
                paid_amount_cent=100,
                refunded_goods_cent=101,
                expires_at=datetime(2026, 11, 4),
            )
        )
    await db_session.rollback()


def test_private_objects_have_no_persistent_public_url(mall_tables):
    assert "object_key" in mall_tables["mall_files"].c
    assert not {"public_url", "signed_url", "file_url"}.intersection(
        mall_tables["mall_files"].c.keys()
    )
    assert not {"phone", "request_body", "response_body"}.intersection(
        mall_tables["mall_commands"].c.keys()
    )


def test_models_are_registered_by_normal_application_import(tmp_path):
    backend = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json,src.models; print(json.dumps(sorted(src.models.Base.metadata.tables)))",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
        env={
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": str(backend),
            "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        },
    )
    names = {
        name
        for group in json.loads((FEATURE / "tasks-map.json").read_text())["tables"].values()
        for name in group
    }
    assert names.issubset(json.loads(result.stdout))


def test_legacy_result_extensions_are_nullable_and_preserve_normal_value():
    from src.models.commission_result import CommissionResult
    from src.models.performance_settlement import PerformanceSettlement

    for field in ["computed_revision", "input_digest", "evidence_version"]:
        assert PerformanceSettlement.__table__.c[field].nullable
    assert CommissionResult.__table__.c.origin_kind.default.arg == "normal"
    assert CommissionResult.__table__.c.evidence_version.nullable
    assert str(CommissionResult.__table__.c.commission_cent.type) == "INTEGER"
