"""Add source_channel column to distributors table.

Revision ID: 014
Revises: 013
Create Date: 2026-08-08

FR-006: Mark personnel source channel (wechat_register / phone_register / admin_create)
so administrators can distinguish self-registered users from manually created ones.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '014'
down_revision: Union[str, None] = '013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'distributors',
        sa.Column(
            'source_channel',
            sa.String(32),
            nullable=False,
            server_default='admin_create',
            comment='人员来源渠道: wechat_register / phone_register / admin_create',
        ),
    )


def downgrade() -> None:
    op.drop_column('distributors', 'source_channel')
