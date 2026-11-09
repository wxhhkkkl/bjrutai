"""Add idempotent mall notices and detailed responsibility task evidence.

Revision ID: 036
Revises: 035
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None


_RESPONSIBILITY_COLUMNS = (
    ("notification_payload", sa.JSON()),
    ("responsibility_role", sa.String(32)),
    ("responsibility_first_discovered_at", sa.DateTime()),
    ("responsibility_last_verified_at", sa.DateTime()),
    ("responsibility_evidence", sa.JSON()),
    ("responsibility_next_step", sa.String(500)),
    ("resolution_code", sa.String(64)),
    ("resolution_summary", sa.String(500)),
    ("resolved_by_type", sa.String(16)),
    ("resolved_by_id", sa.BigInteger()),
    ("resolved_at", sa.DateTime()),
)


def _datetime_type(bind):
    if bind.dialect.name in {"mysql", "mariadb"}:
        return sa.DateTime().with_variant(mysql.DATETIME(fsp=6), bind.dialect.name)
    return sa.DateTime()


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    notification_columns = {item["name"] for item in inspector.get_columns("notifications")}
    job_columns = {item["name"] for item in inspector.get_columns("mall_jobs")}

    if "event_key" not in notification_columns:
        op.add_column("notifications", sa.Column("event_key", sa.String(191), nullable=True))
    notification_indexes = {item["name"] for item in inspector.get_indexes("notifications")}
    if "uq_notifications_event_key" not in notification_indexes:
        op.create_index(
            "uq_notifications_event_key", "notifications", ["event_key"], unique=True
        )

    timestamp_columns = {
        "responsibility_first_discovered_at",
        "responsibility_last_verified_at",
        "resolved_at",
    }
    for name, column_type in _RESPONSIBILITY_COLUMNS:
        if name in timestamp_columns:
            column_type = _datetime_type(bind)
        if name not in job_columns:
            op.add_column("mall_jobs", sa.Column(name, column_type, nullable=True))

    # SQLAlchemy stores Enum member names in this MySQL ENUM column. SQLite
    # uses VARCHAR and needs no type alteration.
    if bind.dialect.name in {"mysql", "mariadb"}:
        op.execute(
            "ALTER TABLE notifications MODIFY COLUMN category "
            "ENUM('SYSTEM','BINDING','PROMOTION','BILL','FOLLOWUP','QUALIFICATION','MALL') NOT NULL"
        )


def downgrade():
    bind = op.get_bind()
    if bind.scalar(sa.text("SELECT COUNT(*) FROM notifications WHERE category = 'MALL'")):
        raise RuntimeError("Mall notification history exists; refusing to remove its category")
    job_columns = {item["name"] for item in sa.inspect(bind).get_columns("mall_jobs")}
    evidence_columns = {
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
    } & job_columns
    if evidence_columns:
        names = ", ".join(sorted(evidence_columns))
        values = " OR ".join(f"{name} IS NOT NULL" for name in sorted(evidence_columns))
        if bind.scalar(sa.text(f"SELECT COUNT(*) FROM mall_jobs WHERE {values}")):
            raise RuntimeError(
                f"Mall responsibility task history exists in {names}; "
                "refusing a lossy downgrade"
            )

    if "uq_notifications_event_key" in {
        item["name"] for item in sa.inspect(bind).get_indexes("notifications")
    }:
        op.drop_index("uq_notifications_event_key", table_name="notifications")
    notification_columns = {item["name"] for item in sa.inspect(bind).get_columns("notifications")}
    if "event_key" in notification_columns:
        op.drop_column("notifications", "event_key")
    for name, _ in reversed(_RESPONSIBILITY_COLUMNS):
        if name in {item["name"] for item in sa.inspect(bind).get_columns("mall_jobs")}:
            op.drop_column("mall_jobs", name)

    if bind.dialect.name in {"mysql", "mariadb"}:
        op.execute(
            "ALTER TABLE notifications MODIFY COLUMN category "
            "ENUM('SYSTEM','BINDING','PROMOTION','BILL','FOLLOWUP','QUALIFICATION') NOT NULL"
        )
