"""cascade org children (history/qualifications) on org delete

Revision ID: 007
Revises: 006
Create Date: 2026-08-03

删除组织时，org_history/org_qualifications 的 org_id 外键改为 ON DELETE CASCADE，
否则历史记录引用导致任何组织都无法删除（IntegrityError 1451）。
"""
from typing import Sequence, Union

from alembic import op


revision: str = '007'
down_revision: Union[str, None] = '006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table, fk in (("org_history", "fk_oh_org"), ("org_qualifications", "fk_oq_org")):
        op.drop_constraint(fk, table, type_="foreignkey")
        op.create_foreign_key(fk, table, "organizations", ["org_id"], ["id"], ondelete="CASCADE")


def downgrade() -> None:
    for table, fk in (("org_history", "fk_oh_org"), ("org_qualifications", "fk_oq_org")):
        op.drop_constraint(fk, table, type_="foreignkey")
        op.create_foreign_key(fk, table, "organizations", ["org_id"], ["id"])
