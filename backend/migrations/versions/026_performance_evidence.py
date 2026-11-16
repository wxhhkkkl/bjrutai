"""Add the mall consumption source and immutable performance evidence.

Revision ID: 026
Revises: mall025

Historical commission and settlement facts are extended only with nullable
compatibility metadata (plus ``origin_kind='normal'``).  This migration never
creates evidence rows for legacy periods, so old frozen records cannot be
misrepresented as a complete replayable snapshot.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "026"
down_revision = "mall025"
branch_labels = None
depends_on = None


def _mall_id():
    return mysql.BIGINT(unsigned=True)


def _time():
    return mysql.DATETIME(fsp=6)


def _record_columns():
    return [
        sa.Column("id", _mall_id(), primary_key=True, autoincrement=True),
        sa.Column("created_at", _time(), nullable=False),
        sa.Column("updated_at", _time(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    ]


def _fk(name, columns, target):
    return sa.ForeignKeyConstraint(columns, target, name=name, ondelete="RESTRICT")


def upgrade():
    op.create_table(
        "mall_consumptions",
        *_record_columns(),
        sa.Column("order_id", _mall_id(), nullable=False),
        sa.Column("buyer_user_id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("attributed_distributor_id", sa.Integer(), nullable=True),
        sa.Column("trade_org_id", sa.Integer(), nullable=True),
        sa.Column("name_snapshots", mysql.JSON(), nullable=False),
        sa.Column("paid_at", _time(), nullable=False),
        sa.Column("business_period", sa.String(7), nullable=False),
        sa.Column("original_goods_cent", sa.BigInteger(), nullable=False),
        sa.Column("successful_goods_refund_cent", sa.BigInteger(), nullable=False),
        sa.Column("performance_base_cent", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column("attribution_evidence", mysql.JSON(), nullable=False),
        _fk("fk_mall_consumption_order", ["order_id"], ["mall_orders.id"]),
        _fk("fk_mall_consumption_buyer", ["buyer_user_id"], ["users.id"]),
        _fk("fk_mall_consumption_customer", ["customer_id"], ["customers.id"]),
        _fk("fk_mall_consumption_distributor", ["attributed_distributor_id"], ["distributors.id"]),
        _fk("fk_mall_consumption_org", ["trade_org_id"], ["organizations.id"]),
        sa.UniqueConstraint("order_id", name="uq_mall_consumption_order"),
        sa.CheckConstraint(
            "original_goods_cent >= 0 AND successful_goods_refund_cent >= 0 "
            "AND successful_goods_refund_cent <= original_goods_cent "
            "AND performance_base_cent >= 0 AND performance_base_cent <= original_goods_cent",
            name="ck_mall_consumption_amount",
        ),
    )
    op.create_index(
        "ix_mall_consumption_person_period",
        "mall_consumptions",
        ["attributed_distributor_id", "business_period", "id"],
    )
    op.create_index(
        "ix_mall_consumption_customer_time", "mall_consumptions", ["customer_id", "paid_at", "id"]
    )
    op.create_index(
        "ix_mall_consumption_status_time", "mall_consumptions", ["status", "paid_at", "id"]
    )

    op.create_table(
        "performance_period_versions",
        sa.Column("period", sa.String(7), primary_key=True),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("recomputed_revision", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("freeze_fingerprint", sa.String(64), nullable=True),
        sa.Column("created_at", _time(), nullable=False),
        sa.Column("updated_at", _time(), nullable=False),
        sa.CheckConstraint("revision >= 0", name="ck_performance_period_revision"),
    )

    op.create_table(
        "performance_evidence",
        *_record_columns(),
        sa.Column("settlement_id", sa.Integer(), nullable=False),
        sa.Column("evidence_key", sa.String(64), nullable=False),
        sa.Column("result_id", sa.Integer(), nullable=True),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("distributor_id", sa.Integer(), nullable=False),
        sa.Column("rule_type", sa.String(32), nullable=False),
        sa.Column("org_id", sa.Integer(), nullable=False),
        sa.Column("frozen_members", mysql.JSON(), nullable=False),
        sa.Column("organization_path_snapshot", mysql.JSON(), nullable=False),
        sa.Column("rule_source", sa.String(32), nullable=False),
        sa.Column("rule_snapshot", mysql.JSON(), nullable=False),
        sa.Column("algorithm_version", sa.String(32), nullable=False),
        sa.Column("legacy_base_cent", sa.BigInteger(), nullable=False),
        sa.Column("mall_base_cent", sa.BigInteger(), nullable=False),
        sa.Column("original_base_cent", sa.BigInteger(), nullable=False),
        sa.Column("original_commission_cent", sa.BigInteger(), nullable=False),
        sa.Column("result_presence", sa.String(16), nullable=False),
        sa.Column("result_absence_reason", sa.String(64), nullable=True),
        sa.Column("input_digest", sa.String(64), nullable=False),
        sa.Column("frozen_at", _time(), nullable=True),
        sa.Column("evidence_status", sa.String(24), nullable=False),
        _fk(
            "fk_performance_evidence_settlement", ["settlement_id"], ["performance_settlements.id"]
        ),
        _fk("fk_performance_evidence_result", ["result_id"], ["commission_results.id"]),
        _fk("fk_performance_evidence_distributor", ["distributor_id"], ["distributors.id"]),
        _fk("fk_performance_evidence_org", ["org_id"], ["organizations.id"]),
        sa.UniqueConstraint("evidence_key", name="uq_performance_evidence_key"),
        sa.UniqueConstraint("result_id", name="uq_performance_evidence_result"),
        sa.UniqueConstraint(
            "settlement_id",
            "distributor_id",
            "rule_type",
            name="uq_performance_evidence_calculation",
        ),
        sa.CheckConstraint(
            "original_commission_cent >= 0 AND original_base_cent >= 0 "
            "AND legacy_base_cent >= 0 AND mall_base_cent >= 0",
            name="ck_performance_evidence_amount",
        ),
        sa.CheckConstraint(
            "result_presence IN ('present','not_generated')",
            name="ck_performance_evidence_presence",
        ),
    )
    op.create_index("ix_performance_evidence_period", "performance_evidence", ["period"])

    op.create_table(
        "performance_evidence_sources",
        *_record_columns(),
        sa.Column("evidence_id", _mall_id(), nullable=False),
        sa.Column("source_type", sa.String(8), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("source_version", sa.BigInteger(), nullable=False),
        sa.Column("attributed_distributor_id", sa.Integer(), nullable=True),
        sa.Column("calculation_org_id", sa.Integer(), nullable=True),
        sa.Column("occurred_at", _time(), nullable=False),
        sa.Column("business_period", sa.String(7), nullable=False),
        sa.Column("base_cent", sa.BigInteger(), nullable=False),
        sa.Column("source_snapshot", mysql.JSON(), nullable=False),
        _fk(
            "fk_performance_evidence_source_evidence", ["evidence_id"], ["performance_evidence.id"]
        ),
        _fk(
            "fk_performance_evidence_source_distributor",
            ["attributed_distributor_id"],
            ["distributors.id"],
        ),
        _fk("fk_performance_evidence_source_org", ["calculation_org_id"], ["organizations.id"]),
        sa.UniqueConstraint(
            "evidence_id", "source_type", "source_id", name="uq_performance_evidence_source"
        ),
        sa.CheckConstraint(
            "source_type IN ('bill','mall') AND base_cent >= 0",
            name="ck_performance_evidence_source",
        ),
    )
    op.create_index(
        "ix_performance_evidence_source_lookup",
        "performance_evidence_sources",
        ["source_type", "source_id", "evidence_id"],
    )

    op.create_table(
        "performance_adjustments",
        *_record_columns(),
        sa.Column("adjustment_no", sa.String(32), nullable=False),
        sa.Column("origin_period", sa.String(7), nullable=False),
        sa.Column("origin_result_id", sa.Integer(), nullable=True),
        sa.Column("evidence_id", _mall_id(), nullable=False),
        sa.Column("trigger_source_type", sa.String(16), nullable=False),
        sa.Column("trigger_source_id", sa.BigInteger(), nullable=False),
        sa.Column("trigger_version", sa.BigInteger(), nullable=False),
        sa.Column("beneficiary_id", sa.Integer(), nullable=False),
        sa.Column("rule_type", sa.String(32), nullable=False),
        sa.Column("original_commission_cent", sa.BigInteger(), nullable=False),
        sa.Column("replayed_commission_cent", sa.BigInteger(), nullable=False),
        sa.Column("prior_confirmed_adjustment_cent", sa.BigInteger(), nullable=False),
        sa.Column("delta_cent", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", _time(), nullable=True),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("remaining_cent", sa.BigInteger(), nullable=False),
        _fk(
            "fk_performance_adjustment_origin_result",
            ["origin_result_id"],
            ["commission_results.id"],
        ),
        _fk("fk_performance_adjustment_evidence", ["evidence_id"], ["performance_evidence.id"]),
        _fk("fk_performance_adjustment_beneficiary", ["beneficiary_id"], ["distributors.id"]),
        _fk("fk_performance_adjustment_reviewer", ["reviewed_by"], ["admin_accounts.id"]),
        sa.UniqueConstraint("adjustment_no", name="uq_performance_adjustment_no"),
        sa.UniqueConstraint(
            "evidence_id",
            "trigger_source_type",
            "trigger_source_id",
            "trigger_version",
            name="uq_performance_adjustment_event",
        ),
        sa.CheckConstraint(
            "status IN ('proposed','manual_required','reviewed','rejected')",
            name="ck_performance_adjustment_status",
        ),
        sa.CheckConstraint(
            "original_commission_cent >= 0 AND replayed_commission_cent >= 0",
            name="ck_performance_adjustment_original",
        ),
    )
    op.create_index(
        "ix_performance_adjustments_origin_period", "performance_adjustments", ["origin_period"]
    )

    op.create_table(
        "performance_adjustment_applications",
        *_record_columns(),
        sa.Column("adjustment_id", _mall_id(), nullable=False),
        sa.Column("target_period", sa.String(7), nullable=False),
        sa.Column("target_result_id", sa.Integer(), nullable=False),
        sa.Column("allocated_cent", sa.BigInteger(), nullable=False),
        sa.Column("settled_cent", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("allocation_key", sa.String(128), nullable=False),
        sa.Column("consumed_at", _time(), nullable=True),
        _fk(
            "fk_performance_application_adjustment",
            ["adjustment_id"],
            ["performance_adjustments.id"],
        ),
        _fk("fk_performance_application_result", ["target_result_id"], ["commission_results.id"]),
        sa.UniqueConstraint("allocation_key", name="uq_performance_application_key"),
        sa.CheckConstraint(
            "status IN ('allocated','consumed','cancelled')",
            name="ck_performance_application_status",
        ),
        sa.CheckConstraint(
            "abs(settled_cent) <= abs(allocated_cent) AND "
            "(settled_cent = 0 OR settled_cent * allocated_cent > 0)",
            name="ck_performance_application_amount",
        ),
    )
    op.create_index(
        "ix_performance_adjustment_applications_target_period",
        "performance_adjustment_applications",
        ["target_period"],
    )

    # Additive compatibility only: old data gets normal provenance and NULL
    # replay metadata; no rows are inserted into the new evidence tables.
    op.add_column(
        "commission_results",
        sa.Column("origin_kind", sa.String(32), nullable=False, server_default=sa.text("'normal'")),
    )
    op.add_column("commission_results", sa.Column("evidence_version", sa.String(64), nullable=True))
    op.add_column(
        "performance_settlements", sa.Column("computed_revision", sa.Integer(), nullable=True)
    )
    op.add_column(
        "performance_settlements", sa.Column("input_digest", sa.String(128), nullable=True)
    )
    op.add_column(
        "performance_settlements", sa.Column("evidence_version", sa.String(64), nullable=True)
    )


def downgrade():
    op.drop_column("performance_settlements", "evidence_version")
    op.drop_column("performance_settlements", "input_digest")
    op.drop_column("performance_settlements", "computed_revision")
    op.drop_column("commission_results", "evidence_version")
    op.drop_column("commission_results", "origin_kind")

    op.drop_table("performance_adjustment_applications")
    op.drop_table("performance_adjustments")
    op.drop_table("performance_evidence_sources")
    op.drop_table("performance_evidence")
    op.drop_table("performance_period_versions")
    op.drop_table("mall_consumptions")
