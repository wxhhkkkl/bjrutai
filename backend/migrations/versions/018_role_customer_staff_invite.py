"""add personal identity, customer phone merge and staff invite codes

Revision ID: 018
Revises: 017
Create Date: 2026-09-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    # Existing production values use SQLAlchemy enum member names (uppercase).
    op.execute(sa.text(
        "ALTER TABLE users MODIFY user_type "
        "ENUM('PERSONAL','PROMOTER','DOCTOR','ADMIN','FINANCE','OPS','DISTRIBUTOR') NOT NULL"
    ))

    customer_columns = {item["name"] for item in sa.inspect(bind).get_columns("customers")}
    if "user_id" not in customer_columns:
        op.add_column("customers", sa.Column("user_id", sa.Integer(), nullable=True))
    if "phone_normalized" not in customer_columns:
        op.add_column("customers", sa.Column("phone_normalized", sa.String(20), nullable=True))

    customer_indexes = {item["name"] for item in sa.inspect(bind).get_indexes("customers")}
    if "ix_customers_user_id" not in customer_indexes:
        op.create_index("ix_customers_user_id", "customers", ["user_id"], unique=True)
    if "ix_customers_phone_normalized" not in customer_indexes:
        op.create_index(
            "ix_customers_phone_normalized", "customers", ["phone_normalized"], unique=False
        )

    customer_foreign_keys = sa.inspect(bind).get_foreign_keys("customers")
    has_user_foreign_key = any(
        item.get("referred_table") == "users"
        and item.get("constrained_columns") == ["user_id"]
        for item in customer_foreign_keys
    )
    if not has_user_foreign_key:
        op.create_foreign_key(
            "fk_customers_user", "customers", "users", ["user_id"], ["id"]
        )
    op.execute(sa.text(
        "UPDATE customers SET phone_normalized = REPLACE(REPLACE(REPLACE(phone, ' ', ''), '-', ''), '+86', '') "
        "WHERE phone IS NOT NULL AND phone NOT LIKE '%*%'"
    ))

    if not sa.inspect(bind).has_table("staff_invite_codes"):
        op.create_table(
            "staff_invite_codes",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("org_id", sa.Integer(), nullable=False),
            sa.Column("inviter_distributor_id", sa.Integer(), nullable=False),
            sa.Column("ref_token", sa.String(255), nullable=False),
            sa.Column(
                "status",
                sa.Enum("available", "disabled", "expired", name="staff_invite_code_status_enum"),
                nullable=False,
                server_default="available",
            ),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("joined_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
            sa.ForeignKeyConstraint(["inviter_distributor_id"], ["distributors.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("inviter_distributor_id", name="uq_staff_invite_inviter"),
            sa.UniqueConstraint("ref_token", name="uq_staff_invite_ref_token"),
        )

    staff_indexes = {item["name"] for item in sa.inspect(bind).get_indexes("staff_invite_codes")}
    if "ix_staff_invite_codes_org_id" not in staff_indexes:
        op.create_index("ix_staff_invite_codes_org_id", "staff_invite_codes", ["org_id"])
    if "ix_staff_invite_codes_inviter_distributor_id" not in staff_indexes:
        op.create_index(
            "ix_staff_invite_codes_inviter_distributor_id",
            "staff_invite_codes",
            ["inviter_distributor_id"],
        )
    if "ix_staff_invite_codes_ref_token" not in staff_indexes:
        op.create_index("ix_staff_invite_codes_ref_token", "staff_invite_codes", ["ref_token"])


def downgrade() -> None:
    op.drop_table("staff_invite_codes")
    op.drop_constraint("fk_customers_user", "customers", type_="foreignkey")
    op.drop_index("ix_customers_phone_normalized", table_name="customers")
    op.drop_index("ix_customers_user_id", table_name="customers")
    op.drop_column("customers", "phone_normalized")
    op.drop_column("customers", "user_id")
    op.execute(sa.text(
        "UPDATE users SET user_type = 'PROMOTER' WHERE user_type = 'PERSONAL'"
    ))
    op.execute(sa.text(
        "ALTER TABLE users MODIFY user_type "
        "ENUM('PROMOTER','DOCTOR','ADMIN','FINANCE','OPS','DISTRIBUTOR') NOT NULL"
    ))
