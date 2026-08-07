"""reports: add source/period/status for settlement reports (月度核算报表记录)

Revision ID: 013
Revises: 012
Create Date: 2026-08-07

「核算成功后自动生成核算报表记录」需要 reports 表能区分来源与审核状态：
- source: 'reconciliation'（手工对账报表，既有默认）/ 'performance_settlement'（自动核算报表）
- period: 核算报表来源月份 'YYYY-MM'（对账报表为 NULL）
- status: 核算报表审核状态 pending/reviewed/rejected（对账报表为 NULL）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '013'
down_revision: Union[str, None] = '012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('reports', sa.Column('source', sa.String(length=32), nullable=False,
                                       server_default='reconciliation'))
    op.add_column('reports', sa.Column('period', sa.String(length=7), nullable=True))
    op.add_column('reports', sa.Column('status', sa.String(length=16), nullable=True))
    op.create_index('ix_reports_period', 'reports', ['period'])


def downgrade() -> None:
    op.drop_index('ix_reports_period', table_name='reports')
    op.drop_column('reports', 'status')
    op.drop_column('reports', 'period')
    op.drop_column('reports', 'source')
