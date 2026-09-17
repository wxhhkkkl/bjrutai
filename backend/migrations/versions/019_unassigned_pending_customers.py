"""allow unassigned pending customers from personal registration

Revision ID: 019
Revises: 018
Create Date: 2026-09-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("customers", "distributor_id", existing_type=sa.Integer(), nullable=True)
    # Backfill only personal accounts that have a phone but no existing customer
    # record.  Existing customer-by-phone records are linked by runtime login.
    op.execute(sa.text(
        "INSERT INTO customers "
        "(user_id, distributor_id, name, phone, phone_normalized, phone_masked, "
        "binding_status, version, created_at, updated_at) "
        "SELECT u.id, NULL, u.name, u.phone, "
        "REPLACE(REPLACE(REPLACE(u.phone, ' ', ''), '-', ''), '+86', ''), "
        "CONCAT(LEFT(u.phone, 3), '****', RIGHT(u.phone, 4)), "
        "'PENDING', 1, UTC_TIMESTAMP(), UTC_TIMESTAMP() "
        "FROM users u "
        "LEFT JOIN distributors d ON d.user_id = u.id "
        "LEFT JOIN customers by_user ON by_user.user_id = u.id "
        "LEFT JOIN customers by_phone ON by_phone.phone_normalized = "
        "REPLACE(REPLACE(REPLACE(u.phone, ' ', ''), '-', ''), '+86', '') "
        "WHERE u.user_type = 'PERSONAL' AND u.phone IS NOT NULL AND u.phone <> '' "
        "AND d.id IS NULL AND by_user.id IS NULL AND by_phone.id IS NULL"
    ))


def downgrade() -> None:
    bind = op.get_bind()
    unassigned_count = bind.execute(
        sa.text("SELECT COUNT(*) FROM customers WHERE distributor_id IS NULL")
    ).scalar() or 0
    if unassigned_count:
        raise RuntimeError("存在无归属待绑定客户，不能降级此迁移")
    op.alter_column("customers", "distributor_id", existing_type=sa.Integer(), nullable=False)
