"""Record internet-hospital entry tap and QR long-press events."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "050"
down_revision = "049"
branch_labels = None
depends_on = None


def upgrade():
    event_id = (
        sa.BigInteger()
        .with_variant(mysql.BIGINT(unsigned=True), "mysql")
        .with_variant(sa.Integer(), "sqlite")
    )
    timestamp = sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")
    if "hospital_visit_events" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "hospital_visit_events",
        sa.Column("id", event_id, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("entry_source", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", timestamp, nullable=False),
        sa.Column("occurred_date", sa.String(length=10), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_hospital_visit_events_user_id", "hospital_visit_events", ["user_id"]
    )
    op.create_index(
        "ix_hospital_visit_events_event_type", "hospital_visit_events", ["event_type"]
    )
    op.create_index(
        "ix_hospital_visit_events_occurred_at",
        "hospital_visit_events",
        ["occurred_at"],
    )
    op.create_index(
        "ix_hospital_visit_events_occurred_date",
        "hospital_visit_events",
        ["occurred_date"],
    )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "hospital_visit_events" not in inspector.get_table_names():
        return
    if bind.scalar(sa.text("SELECT COUNT(*) FROM hospital_visit_events")):
        raise RuntimeError("Hospital visit events exist; refusing a lossy downgrade")
    op.drop_table("hospital_visit_events")
