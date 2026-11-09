"""Widen durable WeChat callback resource storage.

Revision ID: 037
Revises: 036
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "037"
down_revision = "036"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name in {"mysql", "mariadb"}:
        op.alter_column(
            "mall_gateway_events",
            "payload_ciphertext",
            existing_type=sa.LargeBinary(),
            type_=mysql.MEDIUMBLOB(),
            existing_nullable=True,
        )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name in {"mysql", "mariadb"}:
        too_large = bind.scalar(
            sa.text(
                "SELECT COUNT(*) FROM mall_gateway_events "
                "WHERE OCTET_LENGTH(payload_ciphertext) > 65535"
            )
        )
        if too_large:
            raise RuntimeError(
                "Callback resources exceed BLOB capacity; preserve MEDIUMBLOB to prevent data loss"
            )
        op.alter_column(
            "mall_gateway_events",
            "payload_ciphertext",
            existing_type=mysql.MEDIUMBLOB(),
            type_=sa.LargeBinary(),
            existing_nullable=True,
        )
