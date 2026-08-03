"""drop binding_change_logs FKs that still reference the deprecated promoters table

Revision ID: 005
Revises: 004
Create Date: 2026-08-03

``binding_change_logs.previous_promoter_id`` / ``new_promoter_id`` store
Distributor IDs for audit purposes (bind/unbind/transfer history), but their
FK constraints still reference the deprecated ``_deprecated_promoters`` table.
For rows migrated by 004 the IDs coincide (``distributors.id == promoters.id``),
so they hold. For distributors created after the migration the new IDs do not
exist in ``_deprecated_promoters``, so writing a change log violates the FK.

Fix: drop the constraints. The columns remain plain-integer audit references.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _drop_fks(conn, table: str, col: str, referenced_tables: tuple[str, ...]) -> None:
    for ref_table in referenced_tables:
        result = conn.execute(sa.text(
            """
            SELECT CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = :t
              AND COLUMN_NAME = :c
              AND REFERENCED_TABLE_NAME = :ref
            """
        ), {"t": table, "c": col, "ref": ref_table})
        row = result.fetchone()
        if row:
            op.drop_constraint(row[0], table, type_="foreignkey")
            return


def upgrade() -> None:
    conn = op.get_bind()
    # Match either name — 004 renames promoters -> _deprecated_promoters, so the
    # FK may reference either depending on when it was created.
    for col in ("previous_promoter_id", "new_promoter_id"):
        _drop_fks(conn, "binding_change_logs", col, ("_deprecated_promoters", "promoters"))


def downgrade() -> None:
    # Best-effort no-op: re-adding FKs to the deprecated promoters table would
    # reintroduce the constraint bug this migration fixes. The columns store
    # distributor IDs; keeping them unconstrained is the intended end state.
    pass
