"""Create feedback management tables and migrate legacy feedback AuditLogs.

Revision ID: 015
Revises: 014
"""

from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _legacy_type(entity_type: str | None, detail: dict) -> str:
    value = str(detail.get("type") or entity_type or "").lower()
    if value in {"bug", "feedback_bug"}:
        return "bug"
    if value in {"feature", "feedback_feature", "suggestion", "feedback_suggestion"}:
        return "suggestion"
    return "other"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # The development server calls ``Base.metadata.create_all()`` on startup.
    # If it was started before Alembic was upgraded, its tables are already
    # present although Alembic still records revision 014.  Keep this migration
    # resumable so that it can safely finish such an interrupted deployment.
    if not inspector.has_table("feedbacks"):
        op.create_table(
            "feedbacks",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("feedback_no", sa.String(40), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("submitter_name_snapshot", sa.String(100), nullable=True),
            sa.Column("submitter_phone_masked_snapshot", sa.String(20), nullable=True),
            sa.Column("type", sa.String(20), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            # MySQL/MariaDB do not permit defaults on JSON columns.  The service
            # always supplies an empty list for feedback without images.
            sa.Column("image_files", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="submitted"),
            sa.Column("first_handler_id", sa.Integer(), sa.ForeignKey("admin_accounts.id", ondelete="SET NULL"), nullable=True),
            sa.Column("first_handled_at", sa.DateTime(), nullable=True),
            sa.Column("resolved_by_id", sa.Integer(), sa.ForeignKey("admin_accounts.id", ondelete="SET NULL"), nullable=True),
            sa.Column("resolved_at", sa.DateTime(), nullable=True),
            sa.Column("resolution", sa.Text(), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("idempotency_key", sa.String(128), nullable=True),
            sa.Column("submission_fingerprint", sa.String(64), nullable=True),
            sa.Column("source_audit_log_id", sa.Integer(), sa.ForeignKey("audit_logs.id", ondelete="SET NULL"), nullable=True),
            sa.Column("notification_status", sa.String(20), nullable=False, server_default="not_required"),
            sa.Column("notification_attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("notification_next_retry_at", sa.DateTime(), nullable=True),
            sa.Column("notification_last_error", sa.String(500), nullable=True),
            sa.Column("notification_sent_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("feedback_no", name="uq_feedbacks_feedback_no"),
            sa.UniqueConstraint("user_id", "idempotency_key", name="uq_feedbacks_user_idempotency"),
            sa.UniqueConstraint("source_audit_log_id", name="uq_feedbacks_source_audit_log"),
        )
    feedback_indexes = {item["name"] for item in sa.inspect(bind).get_indexes("feedbacks")}
    if "ix_feedbacks_status_created" not in feedback_indexes:
        op.create_index("ix_feedbacks_status_created", "feedbacks", ["status", "created_at", "id"])
    if "ix_feedbacks_type_created" not in feedback_indexes:
        op.create_index("ix_feedbacks_type_created", "feedbacks", ["type", "created_at", "id"])
    if "ix_feedbacks_user_created" not in feedback_indexes:
        op.create_index("ix_feedbacks_user_created", "feedbacks", ["user_id", "created_at", "id"])
    if "ix_feedbacks_submitter_name" not in feedback_indexes:
        op.create_index("ix_feedbacks_submitter_name", "feedbacks", ["submitter_name_snapshot"])

    if not inspector.has_table("feedback_actions"):
        op.create_table(
            "feedback_actions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("feedback_id", sa.Integer(), sa.ForeignKey("feedbacks.id", ondelete="CASCADE"), nullable=False),
            sa.Column("operator_id", sa.Integer(), sa.ForeignKey("admin_accounts.id", ondelete="SET NULL"), nullable=True),
            sa.Column("operator_name_snapshot", sa.String(100), nullable=False),
            sa.Column("action_type", sa.String(20), nullable=False),
            sa.Column("from_status", sa.String(20), nullable=False),
            sa.Column("to_status", sa.String(20), nullable=False),
            sa.Column("internal_note", sa.Text(), nullable=True),
            sa.Column("user_resolution", sa.Text(), nullable=True),
            sa.Column("version_before", sa.Integer(), nullable=False),
            sa.Column("version_after", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
    action_indexes = {item["name"] for item in sa.inspect(bind).get_indexes("feedback_actions")}
    if "ix_feedback_actions_feedback_created" not in action_indexes:
        op.create_index("ix_feedback_actions_feedback_created", "feedback_actions", ["feedback_id", "created_at", "id"])

    notification_columns = {item["name"] for item in sa.inspect(bind).get_columns("notifications")}
    if "feedback_id" not in notification_columns:
        op.add_column("notifications", sa.Column("feedback_id", sa.Integer(), nullable=True))
    notification_foreign_keys = {item.get("name") for item in sa.inspect(bind).get_foreign_keys("notifications")}
    if "fk_notifications_feedback_id" not in notification_foreign_keys:
        op.create_foreign_key(
            "fk_notifications_feedback_id",
            "notifications",
            "feedbacks",
            ["feedback_id"],
            ["id"],
            ondelete="SET NULL",
        )
    notification_unique_constraints = {
        item.get("name") for item in sa.inspect(bind).get_unique_constraints("notifications")
    }
    if "uq_notifications_feedback_id" not in notification_unique_constraints:
        op.create_unique_constraint("uq_notifications_feedback_id", "notifications", ["feedback_id"])

    audits = bind.execute(sa.text("SELECT id, user_id, entity_type, entity_id, detail, created_at FROM audit_logs WHERE action = 'feedback_submit'"))
    now = datetime.utcnow()
    for row in audits.mappings():
        detail = row["detail"] or {}
        if isinstance(detail, str):
            import json
            try:
                detail = json.loads(detail)
            except ValueError:
                detail = {}
        user = None
        if row["user_id"] is not None:
            user = bind.execute(sa.text("SELECT name, phone_masked FROM users WHERE id = :id"), {"id": row["user_id"]}).mappings().first()
        raw_files = detail.get("imageFiles") if isinstance(detail, dict) else []
        raw_files = raw_files if isinstance(raw_files, list) else []
        attachments = [{"objectKey": str(key), "contentType": None, "legacy": True} for key in raw_files if key]
        feedback_no = row["entity_id"] or f"LEGACY-{row['id']}"
        bind.execute(
            sa.text(
                "INSERT INTO feedbacks (feedback_no, user_id, submitter_name_snapshot, submitter_phone_masked_snapshot, type, content, image_files, status, version, source_audit_log_id, notification_status, notification_attempts, created_at, updated_at) "
                "VALUES (:feedback_no, :user_id, :name, :phone, :type, :content, :files, 'submitted', 1, :audit_id, 'not_required', 0, :created_at, :updated_at)"
            ),
            {
                "feedback_no": feedback_no,
                "user_id": row["user_id"] if user else None,
                "name": (user or {}).get("name") or ("历史用户" if row["user_id"] else None),
                "phone": (user or {}).get("phone_masked"),
                "type": _legacy_type(row["entity_type"], detail),
                "content": str(detail.get("content") or ""),
                "files": __import__("json").dumps(attachments, ensure_ascii=False),
                "audit_id": row["id"],
                "created_at": row["created_at"] or now,
                "updated_at": row["created_at"] or now,
            },
        )


def downgrade() -> None:
    op.drop_constraint("uq_notifications_feedback_id", "notifications", type_="unique")
    op.drop_constraint("fk_notifications_feedback_id", "notifications", type_="foreignkey")
    op.drop_column("notifications", "feedback_id")
    op.drop_index("ix_feedback_actions_feedback_created", table_name="feedback_actions")
    op.drop_table("feedback_actions")
    op.drop_index("ix_feedbacks_submitter_name", table_name="feedbacks")
    op.drop_index("ix_feedbacks_user_created", table_name="feedbacks")
    op.drop_index("ix_feedbacks_type_created", table_name="feedbacks")
    op.drop_index("ix_feedbacks_status_created", table_name="feedbacks")
    op.drop_table("feedbacks")
