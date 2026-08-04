"""demote duplicate org admins (one admin per org)

Revision ID: 010
Revises: 009
Create Date: 2026-08-03

绩效规则 FR-008：每组织至多一名组织管理员。存量数据中若某组织存在多个
org_role='admin' 的分销员，保留 id 最小的一名，其余降为 'member'。
"""
from typing import Sequence, Union

from alembic import op


revision: str = '010'
down_revision: Union[str, None] = '009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE distributors d
        JOIN (
            SELECT org_id, MIN(id) AS keep_id
            FROM distributors
            WHERE org_role = 'admin'
            GROUP BY org_id
            HAVING COUNT(*) > 1
        ) k ON d.org_id = k.org_id
        SET d.org_role = 'member'
        WHERE d.org_role = 'admin' AND d.id != k.keep_id
        """
    )


def downgrade() -> None:
    # 降级不恢复：无法确定原管理员身份，数据不可逆。
    pass
