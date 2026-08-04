"""create performance_rules / performance_rule_change_logs / commission_results

Revision ID: 009
Revises: 008
Create Date: 2026-08-03

绩效规则模块：按组织配置两种绩效提成方式（组织内/组织管理），阶梯 JSON，
月度提成结果落库。金额以分存储，ratio 为小数（存字符串保精度）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import JSON


revision: str = '009'
down_revision: Union[str, None] = '008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'performance_rules',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('org_id', sa.BigInteger(), nullable=False),
        sa.Column('rule_type', sa.Enum('intra_org', 'org_management', name='rule_type_enum_pr'), nullable=False),
        sa.Column('tiers', JSON(), nullable=False),
        sa.Column('status', sa.Enum('active', 'inactive', name='rule_status_enum_pr'), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_by', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('org_id', 'rule_type', name='uk_rule_org_type'),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    )
    op.create_table(
        'performance_rule_change_logs',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('rule_id', sa.BigInteger(), nullable=False),
        sa.Column('operation_type', sa.Enum('create', 'update', 'apply', name='change_op_enum_pr'), nullable=False),
        sa.Column('changed_by', sa.BigInteger(), nullable=False),  # 后台管理员 AdminAccount.id
        sa.Column('old_value', JSON(), nullable=True),
        sa.Column('new_value', JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['rule_id'], ['performance_rules.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_performance_rule_change_logs_rule_id', 'performance_rule_change_logs', ['rule_id'])
    op.create_table(
        'commission_results',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('period', sa.String(length=7), nullable=False),
        sa.Column('distributor_id', sa.BigInteger(), nullable=False),
        sa.Column('org_id', sa.BigInteger(), nullable=False),
        sa.Column('rule_type', sa.Enum('intra_org', 'org_management', name='rule_type_enum_pr'), nullable=False),
        sa.Column('base_cent', sa.BigInteger(), nullable=False),
        sa.Column('ratio', sa.String(length=20), nullable=False),
        sa.Column('commission_cent', sa.BigInteger(), nullable=False),
        sa.Column('computed_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('period', 'distributor_id', 'rule_type', name='uk_comm_period_dist_type'),
        sa.ForeignKeyConstraint(['distributor_id'], ['distributors.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_commission_results_period', 'commission_results', ['period'])
    op.create_index('ix_commission_results_org_id_period', 'commission_results', ['org_id', 'period'])


def downgrade() -> None:
    op.drop_table('commission_results')
    op.drop_index('ix_performance_rule_change_logs_rule_id', table_name='performance_rule_change_logs')
    op.drop_table('performance_rule_change_logs')
    op.drop_table('performance_rules')
