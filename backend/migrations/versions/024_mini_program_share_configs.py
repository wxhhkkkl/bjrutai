"""Add editable Mini Program share-card configurations.

Revision ID: 024
Revises: 023
"""

import json
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def _roles_table():
    return sa.table(
        "roles",
        sa.column("id", sa.Integer()),
        sa.column("permissions", sa.JSON()),
        sa.column("is_system", sa.Boolean()),
    )


def _share_config_table():
    return sa.table(
        "mini_program_share_configs",
        sa.column("page_key", sa.String(length=40)),
        sa.column("page_name", sa.String(length=80)),
        sa.column("friend_title", sa.String(length=100)),
        sa.column("friend_image_url", sa.String(length=2048)),
        sa.column("timeline_title", sa.String(length=100)),
        sa.column("timeline_image_url", sa.String(length=2048)),
        sa.column("landing_path", sa.String(length=512)),
        sa.column("version", sa.Integer()),
        sa.column("updated_at", sa.DateTime()),
    )


def _grant_system_admin_permissions(bind):
    roles = _roles_table()
    rows = bind.execute(
        sa.select(roles.c.id, roles.c.permissions).where(roles.c.is_system.is_(True))
    ).mappings()
    for row in rows:
        permissions = row["permissions"] or {}
        if isinstance(permissions, str):
            permissions = json.loads(permissions)
        if not isinstance(permissions, dict):
            continue
        permission_keys = list(permissions.get("permissions") or [])
        changed = False
        for key in ("mini_program_shares.read", "mini_program_shares.write"):
            if key not in permission_keys:
                permission_keys.append(key)
                changed = True
        if changed:
            permissions["permissions"] = permission_keys
            bind.execute(
                roles.update().where(roles.c.id == row["id"]).values(permissions=permissions)
            )


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "mini_program_share_configs" not in inspector.get_table_names():
        op.create_table(
            "mini_program_share_configs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("page_key", sa.String(length=40), nullable=False),
            sa.Column("page_name", sa.String(length=80), nullable=False),
            sa.Column("friend_title", sa.String(length=100), nullable=False),
            sa.Column("friend_image_url", sa.String(length=2048), nullable=False),
            sa.Column("timeline_title", sa.String(length=100), nullable=True),
            sa.Column("timeline_image_url", sa.String(length=2048), nullable=True),
            sa.Column("landing_path", sa.String(length=512), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("page_key", name="uq_mini_share_page_key"),
        )
    else:
        actual_columns = {
            column["name"] for column in sa.inspect(bind).get_columns("mini_program_share_configs")
        }
        required_columns = {
            "id", "page_key", "page_name", "friend_title", "friend_image_url",
            "timeline_title", "timeline_image_url", "landing_path", "version", "updated_at",
        }
        if not required_columns.issubset(actual_columns):
            raise RuntimeError(
                "Existing mini_program_share_configs table does not match migration 024"
            )

    table = _share_config_table()
    existing_keys = set(bind.execute(sa.select(table.c.page_key)).scalars().all())
    defaults = [
        {
            "page_key": "home",
            "page_name": "首页",
            "friend_title": "儒泰医联｜让健康知识，走进日常",
            "friend_image_url": "/assets/images/home-share-friend-v1.jpg",
            "timeline_title": "儒泰医联｜让健康知识，走进日常",
            "timeline_image_url": "/assets/images/home-share-timeline-v1.jpg",
            "landing_path": "/pages/home/index",
            "version": 1,
            "updated_at": datetime.utcnow(),
        },
        {
            "page_key": "promotion-code",
            "page_name": "客户绑定码",
            "friend_title": "儒泰医联｜您的专属健康服务入口",
            "friend_image_url": "/assets/images/promotion-share-friend-v1.jpg",
            "timeline_title": None,
            "timeline_image_url": None,
            "landing_path": "/pages/patient-binding/index?refToken={refToken}",
            "version": 1,
            "updated_at": datetime.utcnow(),
        },
    ]
    missing = [item for item in defaults if item["page_key"] not in existing_keys]
    if missing:
        op.bulk_insert(table, missing)

    _grant_system_admin_permissions(bind)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "roles" in inspector.get_table_names():
        roles = _roles_table()
        rows = bind.execute(
            sa.select(roles.c.id, roles.c.permissions).where(roles.c.is_system.is_(True))
        ).mappings()
        for row in rows:
            permissions = row["permissions"] or {}
            if isinstance(permissions, str):
                permissions = json.loads(permissions)
            if not isinstance(permissions, dict):
                continue
            current = list(permissions.get("permissions") or [])
            filtered = [
                key for key in current
                if key not in ("mini_program_shares.read", "mini_program_shares.write")
            ]
            if filtered != current:
                permissions["permissions"] = filtered
                bind.execute(
                    roles.update().where(roles.c.id == row["id"]).values(permissions=permissions)
                )
    if "mini_program_share_configs" in inspector.get_table_names():
        op.drop_table("mini_program_share_configs")
