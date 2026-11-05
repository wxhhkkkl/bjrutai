"""Products, inline SKU options, categories and immutable stock events."""

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Computed,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base
from .mall_base import MALL_ID, MallRecord


class MallCategory(MallRecord, Base):
    __tablename__ = "mall_categories"
    __table_args__ = (
        UniqueConstraint("normalized_parent_id", "name", name="uq_mall_category_parent_name"),
        CheckConstraint("status IN ('enabled','disabled')", name="ck_mall_category_status"),
    )
    parent_id: Mapped[int | None] = mapped_column(
        MALL_ID, ForeignKey("mall_categories.id", ondelete="RESTRICT")
    )
    normalized_parent_id: Mapped[int] = mapped_column(MALL_ID, Computed("coalesce(parent_id, 0)"))
    name: Mapped[str] = mapped_column(String(64))
    sort: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="enabled")


class MallProduct(MallRecord, Base):
    __tablename__ = "mall_products"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','on_sale','off_sale','archived')", name="ck_mall_product_status"
        ),
        Index("ix_mall_product_status_sort", "status", "sort", "id"),
        Index("ix_mall_product_category_status", "category_id", "status", "sort", "id"),
    )
    category_id: Mapped[int | None] = mapped_column(
        MALL_ID, ForeignKey("mall_categories.id", ondelete="RESTRICT")
    )
    name: Mapped[str] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(String(128), default="")
    cover_file_id: Mapped[int | None] = mapped_column(
        MALL_ID,
        ForeignKey(
            "mall_files.id", name="fk_mall_product_cover", use_alter=True, ondelete="RESTRICT"
        ),
    )
    gallery_file_ids: Mapped[list] = mapped_column(JSON, default=list)
    description: Mapped[str] = mapped_column(Text, default="")
    instructions: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="draft")
    sort: Mapped[int] = mapped_column(Integer, default=0)


class MallSku(MallRecord, Base):
    __tablename__ = "mall_skus"
    __table_args__ = (
        CheckConstraint("sale_price_cent > 0", name="ck_mall_sku_price"),
        CheckConstraint(
            "available_qty >= 0 AND reserved_qty >= 0 AND warning_qty >= 0",
            name="ck_mall_sku_stock",
        ),
        CheckConstraint("status IN ('active','archived')", name="ck_mall_sku_status"),
        Index("ix_mall_sku_product_status", "product_id", "status"),
    )
    product_id: Mapped[int] = mapped_column(
        MALL_ID, ForeignKey("mall_products.id", ondelete="RESTRICT")
    )
    sku_code: Mapped[str] = mapped_column(String(64), unique=True)
    options: Mapped[dict] = mapped_column(JSON, default=dict)
    sale_price_cent: Mapped[int] = mapped_column(BigInteger)
    available_qty: Mapped[int] = mapped_column(Integer, default=0)
    reserved_qty: Mapped[int] = mapped_column(Integer, default=0)
    warning_qty: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="active")


class MallStockMovement(MallRecord, Base):
    __tablename__ = "mall_stock_movements"
    __table_args__ = (
        UniqueConstraint("sku_id", "event_key", name="uq_mall_stock_event"),
        Index("ix_mall_stock_sku_id", "sku_id", "id"),
    )
    sku_id: Mapped[int] = mapped_column(MALL_ID, ForeignKey("mall_skus.id", ondelete="RESTRICT"))
    event_key: Mapped[str] = mapped_column(String(128))
    order_item_id: Mapped[int | None] = mapped_column(
        MALL_ID, ForeignKey("mall_order_items.id", ondelete="RESTRICT")
    )
    aftersale_item_id: Mapped[int | None] = mapped_column(
        MALL_ID, ForeignKey("mall_aftersale_items.id", ondelete="RESTRICT")
    )
    kind: Mapped[str] = mapped_column(String(32))
    available_delta: Mapped[int] = mapped_column(Integer, default=0)
    reserved_delta: Mapped[int] = mapped_column(Integer, default=0)
    before: Mapped[dict] = mapped_column(JSON, default=dict)
    after: Mapped[dict] = mapped_column(JSON, default=dict)
    actor_type: Mapped[str] = mapped_column(String(16))
    actor_id: Mapped[int | None] = mapped_column(BigInteger)
    reason: Mapped[str] = mapped_column(String(500))
