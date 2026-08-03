"""create customer_change_logs table

Revision ID: 008
Revises: 007
Create Date: 2026-08-03

客户管理模块新增推广员变更记录表（FR-012）。customer_id 外键 ON DELETE CASCADE，
客户删除时变更记录一并删除。operator_id 为后台管理员 user id。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '008'
down_revision: Union[str, None] = '007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'customer_change_logs',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('customer_id', sa.BigInteger(), nullable=False),
        sa.Column('operation_type', sa.Enum('created', 'transfer', name='change_operation_type_enum'), nullable=False),
        sa.Column('previous_distributor_id', sa.BigInteger(), nullable=True),
        sa.Column('new_distributor_id', sa.BigInteger(), nullable=True),
        sa.Column('operator_id', sa.BigInteger(), nullable=False),
        sa.Column('reason', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['operator_id'], ['users.id']),
    )
    op.create_index('ix_customer_change_logs_customer_id', 'customer_change_logs', ['customer_id'])


def downgrade() -> None:
    op.drop_index('ix_customer_change_logs_customer_id', table_name='customer_change_logs')
    op.drop_table('customer_change_logs')
