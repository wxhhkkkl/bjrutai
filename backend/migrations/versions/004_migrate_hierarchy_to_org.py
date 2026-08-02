"""migrate hierarchy_nodes/promoters/qualifications into org model

Revision ID: 004
Revises: 003
Create Date: 2026-08-02

WARNING: This is a one-time, destructive-ish data migration.  It preserves
all historical data but deprecates the legacy tables.  Back up the database
before running against production.  The transformation logic is mirrored in
``src/services/org_migration.py`` and validated by
``tests/integration/test_migration_consistency.py``.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. organizations from hierarchy_nodes (ids preserved) ───────────
    op.execute(sa.text("""
        INSERT INTO organizations (id, parent_id, name, org_type, level, sort_order, status, created_at, updated_at)
        SELECT id, parent_id, name, node_type, level, 0, 'active', NOW(), NOW()
        FROM hierarchy_nodes
    """))

    # ── 2. distributors from promoters (ids preserved, org_id = node_id) ─
    op.execute(sa.text("""
        INSERT INTO distributors (id, user_id, org_id, org_role, status, created_at, updated_at)
        SELECT id, user_id, node_id, 'member', 'active', NOW(), NOW()
        FROM promoters
    """))

    # ── 3. org_qualifications: latest qualification per org ─────────────
    op.execute(sa.text("""
        INSERT INTO org_qualifications
            (org_id, legal_entity_name, qualification_types, credit_code, file_urls,
             valid_from, valid_until, status, review_comment, created_at, updated_at)
        SELECT
            d.org_id,
            COALESCE(q.legal_entity, '迁移资质'),
            JSON_ARRAY(q.qualification_type),
            COALESCE(q.credit_code_masked, q.credit_code_encrypted, 'migrated'),
            IF(q.file_id IS NULL, JSON_ARRAY(), JSON_ARRAY(JSON_OBJECT('url', q.file_id, 'type', q.file_type, 'size', q.file_size))),
            NULL,
            COALESCE(q.expires_at, '2099-12-31 23:59:59'),
            CASE q.status
                WHEN 'approved' THEN 'approved'
                WHEN 'rejected' THEN 'rejected'
                ELSE 'reviewing'
            END,
            q.rejected_reason,
            q.created_at,
            q.updated_at
        FROM qualifications q
        JOIN promoters p ON p.id = q.promoter_id
        JOIN distributors d ON d.id = p.id
        WHERE q.created_at = (
            SELECT MAX(q2.created_at)
            FROM qualifications q2
            JOIN promoters p2 ON p2.id = q2.promoter_id
            JOIN distributors d2 ON d2.id = p2.id
            WHERE d2.org_id = d.org_id
        )
    """))

    # ── 4. Switch FKs from promoter_id to distributor_id ────────────────
    # IDs are preserved (distributor.id == promoter.id), so backfill is a copy.
    for table in ("customers", "promotion_codes", "contribution_records", "binding_requests"):
        op.add_column(table, sa.Column("distributor_id", sa.Integer(), nullable=True))
        op.execute(sa.text(f"UPDATE {table} SET distributor_id = promoter_id"))

        # Drop the legacy FK constraint (auto-named) if present
        result = conn.execute(sa.text("""
            SELECT CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = :t
              AND COLUMN_NAME = 'promoter_id'
              AND REFERENCED_TABLE_NAME = 'promoters'
        """), {"t": table})
        row = result.fetchone()
        if row:
            op.drop_constraint(row[0], table, type_="foreignkey")

        op.alter_column(table, "distributor_id", existing_type=sa.Integer(), nullable=False)
        op.drop_column(table, "promoter_id")
        op.create_foreign_key(
            f"fk_{table}_distributor", table, "distributors", ["distributor_id"], ["id"]
        )

    # ── 5. Update roles permissions: hierarchy -> org ───────────────────
    # Replace hierarchy.read/hierarchy.write keys with org.* (per-role Python
    # update — avoids MySQL JSON path-filter limitations).
    _role_rows = conn.execute(sa.text("SELECT id, permissions FROM roles")).fetchall()
    for _rid, _perms in _role_rows:
        if isinstance(_perms, dict) and isinstance(_perms.get("permissions"), list):
            _new_list = [
                "org.read" if p == "hierarchy.read"
                else "org.write" if p == "hierarchy.write"
                else p
                for p in _perms["permissions"]
            ]
            conn.execute(
                sa.text("UPDATE roles SET permissions = :p WHERE id = :id"),
                {"p": {"permissions": _new_list}, "id": _rid},
            )

    # ── 6. Deprecate legacy tables (data preserved) ─────────────────────
    op.rename_table("hierarchy_nodes", "_deprecated_hierarchy_nodes")
    op.rename_table("promoters", "_deprecated_promoters")
    op.rename_table("qualifications", "_deprecated_qualifications")


def downgrade() -> None:
    # Best-effort: restore names (data retained in deprecated tables).
    op.rename_table("_deprecated_qualifications", "qualifications")
    op.rename_table("_deprecated_promoters", "promoters")
    op.rename_table("_deprecated_hierarchy_nodes", "hierarchy_nodes")

    for table in ("customers", "promotion_codes", "contribution_records", "binding_requests"):
        op.add_column(table, sa.Column("promoter_id", sa.Integer(), nullable=True))
        op.execute(sa.text(f"UPDATE {table} SET promoter_id = distributor_id"))
        op.drop_constraint(f"fk_{table}_distributor", table, type_="foreignkey")
        op.drop_column(table, "distributor_id")

    op.execute(sa.text("DELETE FROM org_qualifications"))
    op.execute(sa.text("DELETE FROM distributors"))
    op.execute(sa.text("DELETE FROM organizations"))
