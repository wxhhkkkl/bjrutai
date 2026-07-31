"""add is_system to roles

Revision ID: 001
Revises: None
Create Date: 2026-07-31

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'roles',
        sa.Column('is_system', sa.Boolean(), nullable=False, server_default=sa.text('0')),
    )


def downgrade() -> None:
    op.drop_column('roles', 'is_system')
