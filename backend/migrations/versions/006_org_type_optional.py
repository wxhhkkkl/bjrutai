"""make organizations.org_type nullable (optional remark)

Revision ID: 006
Revises: 005
Create Date: 2026-08-03

org_type 从必填的组织类型标签改为可选备注：管理员可不填。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '006'
down_revision: Union[str, None] = '005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'organizations',
        'org_type',
        existing_type=sa.String(50),
        nullable=True,
    )


def downgrade() -> None:
    # 回填空串后再改回 NOT NULL（数据安全：避免历史空值导致失败）
    op.execute(sa.text("UPDATE organizations SET org_type = '' WHERE org_type IS NULL"))
    op.alter_column(
        'organizations',
        'org_type',
        existing_type=sa.String(50),
        nullable=False,
    )
