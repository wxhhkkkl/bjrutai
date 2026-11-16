"""Create the independent mall catalog, intent and order core.

Revision ID: mall024
Revises: 025

This revision intentionally leaves references to later finance/file/aftersale
tables as nullable scalar columns.  Revision 025 creates those tables and then
adds the cross-batch foreign keys in a deterministic order.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "mall024"
down_revision = "025"
branch_labels = None
depends_on = None


def _mall_id():
    return mysql.BIGINT(unsigned=True)


def _time():
    return mysql.DATETIME(fsp=6)


def _record_columns():
    return [
        sa.Column("id", _mall_id(), primary_key=True, autoincrement=True),
        sa.Column("created_at", _time(), nullable=False),
        sa.Column("updated_at", _time(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    ]


def _fk(name, columns, target):
    return sa.ForeignKeyConstraint(columns, target, name=name, ondelete="RESTRICT")


def upgrade():
    op.create_table(
        "mall_categories",
        *_record_columns(),
        sa.Column("parent_id", _mall_id(), nullable=True),
        sa.Column(
            "normalized_parent_id",
            _mall_id(),
            sa.Computed("coalesce(parent_id, 0)"),
            nullable=False,
        ),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("sort", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        _fk("fk_mall_category_parent", ["parent_id"], ["mall_categories.id"]),
        sa.UniqueConstraint("normalized_parent_id", "name", name="uq_mall_category_parent_name"),
        sa.CheckConstraint("status IN ('enabled','disabled')", name="ck_mall_category_status"),
    )
    op.create_table(
        "mall_products",
        *_record_columns(),
        sa.Column("category_id", _mall_id(), nullable=True),
        # 025 adds the FK after mall_files exists.
        sa.Column("cover_file_id", _mall_id(), nullable=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("summary", sa.String(128), nullable=False),
        sa.Column("gallery_file_ids", mysql.JSON(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("sort", sa.Integer(), nullable=False),
        _fk("fk_mall_product_category", ["category_id"], ["mall_categories.id"]),
        sa.CheckConstraint(
            "status IN ('draft','on_sale','off_sale','archived')",
            name="ck_mall_product_status",
        ),
    )
    op.create_index("ix_mall_product_status_sort", "mall_products", ["status", "sort", "id"])
    op.create_index(
        "ix_mall_product_category_status",
        "mall_products",
        ["category_id", "status", "sort", "id"],
    )

    op.create_table(
        "mall_skus",
        *_record_columns(),
        sa.Column("product_id", _mall_id(), nullable=False),
        sa.Column("sku_code", sa.String(64), nullable=False),
        sa.Column("options", mysql.JSON(), nullable=False),
        sa.Column("sale_price_cent", sa.BigInteger(), nullable=False),
        sa.Column("available_qty", sa.Integer(), nullable=False),
        sa.Column("reserved_qty", sa.Integer(), nullable=False),
        sa.Column("warning_qty", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        _fk("fk_mall_sku_product", ["product_id"], ["mall_products.id"]),
        sa.UniqueConstraint("sku_code", name="uq_mall_sku_code"),
        sa.CheckConstraint("sale_price_cent > 0", name="ck_mall_sku_price"),
        sa.CheckConstraint(
            "available_qty >= 0 AND reserved_qty >= 0 AND warning_qty >= 0",
            name="ck_mall_sku_stock",
        ),
        sa.CheckConstraint("status IN ('active','archived')", name="ck_mall_sku_status"),
    )
    op.create_index("ix_mall_sku_product_status", "mall_skus", ["product_id", "status"])

    op.create_table(
        "mall_addresses",
        *_record_columns(),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("recipient_name", sa.String(50), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("phone_masked", sa.String(20), nullable=False),
        sa.Column("province_code", sa.String(12), nullable=False),
        sa.Column("city_code", sa.String(12), nullable=False),
        sa.Column("district_code", sa.String(12), nullable=False),
        sa.Column("address_line", sa.String(200), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("archived_at", _time(), nullable=True),
        sa.Column("consent_record_id", sa.Integer(), nullable=True),
        _fk("fk_mall_address_user", ["user_id"], ["users.id"]),
        _fk("fk_mall_address_consent", ["consent_record_id"], ["consent_records.id"]),
    )
    op.create_index("ix_mall_address_owner", "mall_addresses", ["user_id", "archived_at", "id"])

    op.create_table(
        "mall_cart_items",
        *_record_columns(),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("sku_id", _mall_id(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        _fk("fk_mall_cart_user", ["user_id"], ["users.id"]),
        _fk("fk_mall_cart_sku", ["sku_id"], ["mall_skus.id"]),
        sa.UniqueConstraint("user_id", "sku_id", name="uq_mall_cart_owner_sku"),
        sa.CheckConstraint("quantity > 0", name="ck_mall_cart_quantity"),
    )

    op.create_table(
        "mall_orders",
        *_record_columns(),
        sa.Column("order_no", sa.String(32), nullable=False),
        sa.Column("buyer_user_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("goods_amount_cent", sa.BigInteger(), nullable=False),
        sa.Column("freight_amount_cent", sa.BigInteger(), nullable=False),
        sa.Column("payable_amount_cent", sa.BigInteger(), nullable=False),
        sa.Column("paid_amount_cent", sa.BigInteger(), nullable=False),
        sa.Column("refunded_goods_cent", sa.BigInteger(), nullable=False),
        sa.Column("refunded_freight_cent", sa.BigInteger(), nullable=False),
        sa.Column("refund_reserved_cent", sa.BigInteger(), nullable=False),
        sa.Column("address_snapshot", mysql.JSON(), nullable=False),
        sa.Column("policy_snapshot", mysql.JSON(), nullable=False),
        sa.Column("buyer_note", sa.String(200), nullable=False),
        sa.Column("internal_note", sa.String(200), nullable=False),
        sa.Column("expires_at", _time(), nullable=False),
        sa.Column("paid_at", _time(), nullable=True),
        sa.Column("business_period", sa.String(7), nullable=True),
        sa.Column("shipped_at", _time(), nullable=True),
        sa.Column("received_at", _time(), nullable=True),
        sa.Column("closed_at", _time(), nullable=True),
        sa.Column("close_reason", sa.String(200), nullable=True),
        # 025 creates both targets and adds their FKs.
        sa.Column("active_payment_id", _mall_id(), nullable=True),
        sa.Column("current_invoice_request_id", _mall_id(), nullable=True),
        sa.Column("consent_record_id", sa.Integer(), nullable=True),
        _fk("fk_mall_order_buyer", ["buyer_user_id"], ["users.id"]),
        _fk("fk_mall_order_consent", ["consent_record_id"], ["consent_records.id"]),
        sa.UniqueConstraint("order_no", name="uq_mall_order_no"),
        sa.CheckConstraint(
            "goods_amount_cent >= 0 AND freight_amount_cent >= 0 "
            "AND payable_amount_cent = goods_amount_cent + freight_amount_cent",
            name="ck_mall_order_total",
        ),
        sa.CheckConstraint(
            "paid_amount_cent >= 0 AND paid_amount_cent <= payable_amount_cent "
            "AND refunded_goods_cent >= 0 AND refunded_freight_cent >= 0 "
            "AND refund_reserved_cent >= 0 AND refunded_goods_cent + "
            "refunded_freight_cent + refund_reserved_cent <= paid_amount_cent",
            name="ck_mall_order_refund",
        ),
        sa.CheckConstraint(
            "refunded_goods_cent <= goods_amount_cent "
            "AND refunded_freight_cent <= freight_amount_cent",
            name="ck_mall_order_refund_parts",
        ),
        sa.CheckConstraint("currency = 'CNY'", name="ck_mall_order_currency"),
        sa.CheckConstraint(
            "status IN ('pending_payment','pending_shipment','pending_receipt',"
            "'completed','closed')",
            name="ck_mall_order_status",
        ),
    )
    op.create_index("ix_mall_order_owner", "mall_orders", ["buyer_user_id", "created_at", "id"])
    op.create_index("ix_mall_order_status", "mall_orders", ["status", "created_at", "id"])
    op.create_index("ix_mall_order_period", "mall_orders", ["business_period", "paid_at", "id"])

    op.create_table(
        "mall_order_items",
        *_record_columns(),
        sa.Column("order_id", _mall_id(), nullable=False),
        sa.Column("sku_id", _mall_id(), nullable=False),
        sa.Column("product_id", _mall_id(), nullable=False),
        sa.Column("product_snapshot", mysql.JSON(), nullable=False),
        sa.Column("unit_price_cent", sa.BigInteger(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("line_amount_cent", sa.BigInteger(), nullable=False),
        sa.Column("reservation_status", sa.String(16), nullable=False),
        sa.Column("returned_quantity", sa.Integer(), nullable=False),
        sa.Column("refunded_quantity", sa.Integer(), nullable=False),
        sa.Column("aftersale_reserved_quantity", sa.Integer(), nullable=False),
        sa.Column("refunded_goods_cent", sa.BigInteger(), nullable=False),
        _fk("fk_mall_order_item_order", ["order_id"], ["mall_orders.id"]),
        _fk("fk_mall_order_item_sku", ["sku_id"], ["mall_skus.id"]),
        _fk("fk_mall_order_item_product", ["product_id"], ["mall_products.id"]),
        sa.UniqueConstraint("order_id", "sku_id", name="uq_mall_order_sku"),
        sa.CheckConstraint(
            "quantity > 0 AND unit_price_cent > 0 "
            "AND line_amount_cent = unit_price_cent * quantity",
            name="ck_mall_order_line",
        ),
        sa.CheckConstraint(
            "returned_quantity >= 0 AND returned_quantity <= quantity AND refunded_quantity >= 0 "
            "AND aftersale_reserved_quantity >= 0 AND refunded_quantity + "
            "aftersale_reserved_quantity <= quantity",
            name="ck_mall_order_line_quantities",
        ),
        sa.CheckConstraint(
            "refunded_goods_cent >= 0 AND refunded_goods_cent <= line_amount_cent",
            name="ck_mall_order_line_refund",
        ),
    )

    op.create_table(
        "mall_stock_movements",
        *_record_columns(),
        sa.Column("sku_id", _mall_id(), nullable=False),
        sa.Column("event_key", sa.String(128), nullable=False),
        sa.Column("order_item_id", _mall_id(), nullable=True),
        # 025 creates mall_aftersale_items and adds this FK.
        sa.Column("aftersale_item_id", _mall_id(), nullable=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("available_delta", sa.Integer(), nullable=False),
        sa.Column("reserved_delta", sa.Integer(), nullable=False),
        sa.Column("before", mysql.JSON(), nullable=False),
        sa.Column("after", mysql.JSON(), nullable=False),
        sa.Column("actor_type", sa.String(16), nullable=False),
        sa.Column("actor_id", sa.BigInteger(), nullable=True),
        sa.Column("reason", sa.String(500), nullable=False),
        _fk("fk_mall_stock_sku", ["sku_id"], ["mall_skus.id"]),
        _fk("fk_mall_stock_order_item", ["order_item_id"], ["mall_order_items.id"]),
        sa.UniqueConstraint("sku_id", "event_key", name="uq_mall_stock_event"),
    )
    op.create_index("ix_mall_stock_sku_id", "mall_stock_movements", ["sku_id", "id"])

    op.create_table(
        "mall_settings",
        sa.Column("id", _mall_id(), primary_key=True, autoincrement=False),
        sa.Column("created_at", _time(), nullable=False),
        sa.Column("updated_at", _time(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("purchase_enabled", sa.Boolean(), nullable=False),
        sa.Column("freight_mode", sa.String(16), nullable=False),
        sa.Column("freight_cent", sa.BigInteger(), nullable=False),
        sa.Column("blocked_regions", mysql.JSON(), nullable=False),
        sa.Column("payment_minutes", sa.Integer(), nullable=False),
        sa.Column("auto_receive_days", sa.Integer(), nullable=False),
        sa.Column("aftersale_days", sa.Integer(), nullable=False),
        sa.Column("dispatch_address_snapshot", mysql.JSON(), nullable=False),
        sa.Column("return_address_snapshot", mysql.JSON(), nullable=False),
        sa.Column("contact", sa.String(500), nullable=False),
        sa.Column("return_instructions", sa.Text(), nullable=False),
        sa.Column("policy_versions", mysql.JSON(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_mall_settings_singleton"),
        sa.CheckConstraint(
            "freight_cent >= 0 AND payment_minutes > 0 "
            "AND auto_receive_days > 0 AND aftersale_days > 0",
            name="ck_mall_settings_values",
        ),
        sa.CheckConstraint("freight_mode IN ('free','fixed')", name="ck_mall_settings_freight"),
    )


def downgrade():
    op.drop_table("mall_settings")
    op.drop_table("mall_stock_movements")
    op.drop_table("mall_order_items")
    op.drop_table("mall_orders")
    op.drop_table("mall_cart_items")
    op.drop_table("mall_addresses")
    op.drop_table("mall_skus")
    op.drop_table("mall_products")
    op.drop_table("mall_categories")
