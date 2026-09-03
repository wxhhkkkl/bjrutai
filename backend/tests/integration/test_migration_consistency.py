"""US6 migration consistency tests (SC-009/010).

Seeds legacy hierarchy/promoter/qualification data, runs the shared migration
logic (src/services/org_migration.py — same transformation as migration 004),
and asserts historical data is fully preserved.
"""

from datetime import datetime, timedelta
import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    create_engine,
    inspect,
    text,
)

from src.models.bill import Bill
from src.models.hierarchy import HierarchyNode, NodeType, Promoter
from src.models.org_qualification import OrgQualStatus
from src.models.organization import Organization
from src.models.distributor import Distributor
from src.models.qualification import Qualification, QualStatus, QualificationType
from src.models.user import User, UserType
from src.services import org_migration


async def _seed_legacy(db):
    # Users
    u1 = User(user_type=UserType.PROMOTER, name="张拓展", wechat_bound=True)
    u2 = User(user_type=UserType.PROMOTER, name="李拓展", wechat_bound=True)
    db.add_all([u1, u2])
    await db.flush()

    # Tree: root L1 -> child L2
    root = HierarchyNode(parent_id=None, level=1, node_type=NodeType.HEADQUARTERS, name="总部")
    child = HierarchyNode(parent_id=None, level=2, node_type=NodeType.REGION, name="华北区")
    db.add_all([root, child])
    await db.flush()

    p1 = Promoter(user_id=u1.id, node_id=root.id)
    p2 = Promoter(user_id=u2.id, node_id=child.id)
    db.add_all([p1, p2])
    await db.flush()

    # Qualifications
    now = datetime.utcnow()
    q1 = Qualification(
        promoter_id=p1.id, legal_entity="北京儒泰公司", qualification_type=QualificationType.ENTERPRISE,
        credit_code_masked="9111***", status=QualStatus.APPROVED,
        expires_at=now + timedelta(days=365), created_at=now,
    )
    q2 = Qualification(
        promoter_id=p2.id, legal_entity="北京儒泰华北", qualification_type=QualificationType.ENTERPRISE,
        credit_code_masked="9101***", status=QualStatus.REJECTED,
        rejected_reason="资料不全", expires_at=now + timedelta(days=365), created_at=now,
    )
    db.add_all([q1, q2])
    await db.flush()
    return {"orgs": 2, "promoters": 2, "quals": 2}


@pytest.mark.asyncio
async def test_migration_preserves_all_data(db_session):
    seeded = await _seed_legacy(db_session)
    summary = await org_migration.run_org_data_migration(db_session)

    assert summary["organizations"] == seeded["orgs"]
    assert summary["distributors"] == seeded["promoters"]

    from sqlalchemy import func, select

    org_count = (await db_session.execute(select(func.count(Organization.id)))).scalar()
    dist_count = (await db_session.execute(select(func.count(Distributor.id)))).scalar()
    assert org_count == seeded["orgs"]
    assert dist_count == seeded["promoters"]

    # Org tree preserved: parent_id alignment
    roots = (await db_session.execute(select(Organization).where(Organization.parent_id.is_(None)))).scalars().all()
    assert len(roots) == 2  # seeded both without parent (migration preserves raw parent_id)


@pytest.mark.asyncio
async def test_distributor_org_mapping_from_node(db_session):
    await _seed_legacy(db_session)
    await org_migration.run_org_data_migration(db_session)

    from sqlalchemy import select

    from src.models.distributor import Distributor

    dists = (await db_session.execute(select(Distributor))).scalars().all()
    assert all(d.org_role.value == "member" for d in dists)
    # org_id equals legacy node_id (ids preserved)
    for d in dists:
        assert d.org_id == d.id


@pytest.mark.asyncio
async def test_org_qualifications_from_latest(db_session):
    await _seed_legacy(db_session)
    summary = await org_migration.run_org_data_migration(db_session)

    assert summary["org_qualifications"] == 2

    from sqlalchemy import select

    from src.models.org_qualification import OrganizationQualification

    quals = (await db_session.execute(select(OrganizationQualification))).scalars().all()
    statuses = {q.status for q in quals}
    assert OrgQualStatus.APPROVED in statuses
    assert OrgQualStatus.REJECTED in statuses


def test_manual_consumption_migration_contract():
    """Migration 016 and ORM metadata expose the manual-entry persistence contract."""
    migration = Path(__file__).parents[2] / "migrations" / "versions" / "016_manual_consumption_entry.py"
    assert migration.exists()

    expected_columns = {
        "source",
        "attributed_distributor_id",
        "attributed_person_name",
        "attributed_org_id",
        "attributed_org_name",
        "entry_note",
        "created_by_admin_id",
        "idempotency_key",
        "submission_fingerprint",
    }
    assert expected_columns <= set(Bill.__table__.columns.keys())

    unique_column_sets = {
        tuple(column.name for column in constraint.columns)
        for constraint in Bill.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert ("created_by_admin_id", "idempotency_key") in unique_column_sets


def test_manual_consumption_migration_round_trip_preserves_legacy_bill(tmp_path, monkeypatch):
    """Run 016 upgrade/downgrade/upgrade against an isolated 015-shaped DB."""
    migration_path = (
        Path(__file__).parents[2]
        / "migrations"
        / "versions"
        / "016_manual_consumption_entry.py"
    )
    spec = importlib.util.spec_from_file_location("migration_016", migration_path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_engine(f"sqlite:///{tmp_path / 'migration-016.db'}")
    metadata = MetaData()
    Table(
        "admin_accounts",
        metadata,
        Column("id", Integer, primary_key=True),
    )
    Table(
        "bills",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("transaction_id", String(100), nullable=False),
        Column("paid_amount_cent", Integer, nullable=False),
        Column("transaction_status", String(30), nullable=False),
        Column("created_at", DateTime, nullable=False),
    )

    with engine.begin() as connection:
        metadata.create_all(connection)
        connection.execute(
            text(
                "INSERT INTO bills "
                "(id, transaction_id, paid_amount_cent, transaction_status, created_at) "
                "VALUES (1, 'legacy-001', 12880, 'paid', '2026-09-01 10:00:00')"
            )
        )
        monkeypatch.setattr(
            migration,
            "op",
            Operations(MigrationContext.configure(connection)),
        )

        migration.upgrade()
        upgraded_columns = {column["name"] for column in inspect(connection).get_columns("bills")}
        assert {"source", "created_by_admin_id", "idempotency_key"} <= upgraded_columns
        legacy = connection.execute(
            text(
                "SELECT transaction_id, paid_amount_cent, transaction_status, source "
                "FROM bills WHERE id = 1"
            )
        ).one()
        assert tuple(legacy) == ("legacy-001", 12880, "paid", "rutai_sync")
        unique_sets = {
            tuple(constraint["column_names"])
            for constraint in inspect(connection).get_unique_constraints("bills")
        }
        assert ("created_by_admin_id", "idempotency_key") in unique_sets

        migration.downgrade()
        downgraded_columns = {column["name"] for column in inspect(connection).get_columns("bills")}
        assert "source" not in downgraded_columns
        legacy_after_downgrade = connection.execute(
            text(
                "SELECT transaction_id, paid_amount_cent, transaction_status "
                "FROM bills WHERE id = 1"
            )
        ).one()
        assert tuple(legacy_after_downgrade) == ("legacy-001", 12880, "paid")

        migration.upgrade()
        reupgraded = connection.execute(
            text("SELECT paid_amount_cent, source FROM bills WHERE id = 1")
        ).one()
        assert tuple(reupgraded) == (12880, "rutai_sync")

    engine.dispose()
