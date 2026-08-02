"""add organizations / distributors / org_qualifications tables + users.password_hash

Revision ID: 003
Revises: 002
Create Date: 2026-08-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'organizations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('parent_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(128), nullable=False),
        sa.Column('org_type', sa.String(50), nullable=False),
        sa.Column('level', sa.Integer(), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', sa.Enum('active', 'disabled', name='org_status_enum'), nullable=False, server_default='active'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_organizations_parent_id', 'organizations', ['parent_id'])
    op.create_index('ix_organizations_level', 'organizations', ['level'])
    op.create_index('ix_organizations_org_type', 'organizations', ['org_type'])
    op.create_foreign_key('fk_org_parent', 'organizations', 'organizations', ['parent_id'], ['id'])

    op.create_table(
        'distributors',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('org_id', sa.Integer(), nullable=False),
        sa.Column('org_role', sa.Enum('member', 'admin', name='org_role_enum'), nullable=False, server_default='member'),
        sa.Column('status', sa.Enum('active', 'disabled', name='distributor_status_enum'), nullable=False, server_default='active'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_distributors_org_id', 'distributors', ['org_id'])
    op.create_index('ix_distributors_org_id_org_role', 'distributors', ['org_id', 'org_role'])
    op.create_unique_constraint('uq_distributors_user_id', 'distributors', ['user_id'])
    op.create_foreign_key('fk_dst_user', 'distributors', 'users', ['user_id'], ['id'])
    op.create_foreign_key('fk_dst_org', 'distributors', 'organizations', ['org_id'], ['id'])

    op.create_table(
        'org_qualifications',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('org_id', sa.Integer(), nullable=False),
        sa.Column('legal_entity_name', sa.String(256), nullable=False),
        sa.Column('qualification_types', sa.JSON(), nullable=False),
        sa.Column('credit_code', sa.String(64), nullable=False),
        sa.Column('file_urls', sa.JSON(), nullable=False),
        sa.Column('valid_from', sa.DateTime(), nullable=True),
        sa.Column('valid_until', sa.DateTime(), nullable=False),
        sa.Column('status', sa.Enum('reviewing', 'approved', 'rejected', name='org_qual_status_enum'), nullable=False, server_default='reviewing'),
        sa.Column('review_comment', sa.Text(), nullable=True),
        sa.Column('reviewed_by', sa.Integer(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_org_qualifications_org_id', 'org_qualifications', ['org_id'])
    op.create_index('ix_org_qualifications_status', 'org_qualifications', ['status'])
    op.create_index('ix_org_qualifications_valid_until', 'org_qualifications', ['valid_until'])
    op.create_foreign_key('fk_oq_org', 'org_qualifications', 'organizations', ['org_id'], ['id'])
    op.create_foreign_key('fk_oq_reviewer', 'org_qualifications', 'admin_accounts', ['reviewed_by'], ['id'])

    op.add_column('users', sa.Column('password_hash', sa.String(255), nullable=True))

    # Extend user_type enum to include 'distributor'
    op.execute(sa.text(
        "ALTER TABLE users MODIFY user_type ENUM('PROMOTER','DOCTOR','ADMIN','FINANCE','OPS','DISTRIBUTOR') NOT NULL"
    ))

    op.create_table(
        'org_history',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('org_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.Enum('created', 'updated', 'moved', 'deleted', name='org_history_action_enum'), nullable=False),
        sa.Column('operator_id', sa.Integer(), nullable=True),
        sa.Column('detail', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_org_history_org_id', 'org_history', ['org_id'])
    op.create_foreign_key('fk_oh_org', 'org_history', 'organizations', ['org_id'], ['id'])
    op.create_foreign_key('fk_oh_operator', 'org_history', 'admin_accounts', ['operator_id'], ['id'])


def downgrade() -> None:
    op.drop_table('org_history')
    op.drop_column('users', 'password_hash')
    op.drop_table('org_qualifications')
    op.drop_table('distributors')
    op.drop_table('organizations')
