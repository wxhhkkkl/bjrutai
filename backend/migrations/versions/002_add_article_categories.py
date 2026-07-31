"""add article_categories table + category_id FK

Revision ID: 002
Revises: 001
Create Date: 2026-07-31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'article_categories',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(50), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.add_column('articles', sa.Column('category_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_articles_category_id', 'articles', 'article_categories', ['category_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint('fk_articles_category_id', 'articles', type_='foreignkey')
    op.drop_column('articles', 'category_id')
    op.drop_table('article_categories')
