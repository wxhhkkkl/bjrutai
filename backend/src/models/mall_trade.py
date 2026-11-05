"""Buyer intent, historical orders, one package and quantity-based aftersales."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base
from .mall_base import MALL_ID, UTC_TIME, MallRecord


class MallAddress(MallRecord, Base):
    __tablename__ = "mall_addresses"
    __table_args__ = (Index("ix_mall_address_owner", "user_id", "archived_at", "id"),)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="RESTRICT"))
    recipient_name: Mapped[str] = mapped_column(String(50))
    phone: Mapped[str] = mapped_column(String(20))
    phone_masked: Mapped[str] = mapped_column(String(20))
    province_code: Mapped[str] = mapped_column(String(12))
    city_code: Mapped[str] = mapped_column(String(12))
    district_code: Mapped[str] = mapped_column(String(12))
    address_line: Mapped[str] = mapped_column(String(200))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    archived_at: Mapped[datetime | None] = mapped_column(UTC_TIME)
    consent_record_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("consent_records.id", ondelete="RESTRICT")
    )


class MallCartItem(MallRecord, Base):
    __tablename__ = "mall_cart_items"
    __table_args__ = (
        UniqueConstraint("user_id", "sku_id", name="uq_mall_cart_owner_sku"),
        CheckConstraint("quantity > 0", name="ck_mall_cart_quantity"),
    )
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="RESTRICT"))
    sku_id: Mapped[int] = mapped_column(MALL_ID, ForeignKey("mall_skus.id", ondelete="RESTRICT"))
    quantity: Mapped[int] = mapped_column(Integer)


class MallOrder(MallRecord, Base):
    __tablename__ = "mall_orders"
    __table_args__ = (
        CheckConstraint(
            "goods_amount_cent >= 0 AND freight_amount_cent >= 0 "
            "AND payable_amount_cent = goods_amount_cent + freight_amount_cent",
            name="ck_mall_order_total",
        ),
        CheckConstraint(
            "paid_amount_cent >= 0 AND paid_amount_cent <= payable_amount_cent "
            "AND refunded_goods_cent >= 0 AND refunded_freight_cent >= 0 "
            "AND refund_reserved_cent >= 0 AND refunded_goods_cent + "
            "refunded_freight_cent + refund_reserved_cent <= paid_amount_cent",
            name="ck_mall_order_refund",
        ),
        CheckConstraint(
            "refunded_goods_cent <= goods_amount_cent "
            "AND refunded_freight_cent <= freight_amount_cent",
            name="ck_mall_order_refund_parts",
        ),
        CheckConstraint("currency = 'CNY'", name="ck_mall_order_currency"),
        CheckConstraint(
            "status IN ('pending_payment','pending_shipment','pending_receipt',"
            "'completed','closed')",
            name="ck_mall_order_status",
        ),
        Index("ix_mall_order_owner", "buyer_user_id", "created_at", "id"),
        Index("ix_mall_order_status", "status", "created_at", "id"),
        Index("ix_mall_order_period", "business_period", "paid_at", "id"),
    )
    order_no: Mapped[str] = mapped_column(String(32), unique=True)
    buyer_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(24), default="pending_payment")
    currency: Mapped[str] = mapped_column(String(3), default="CNY")
    goods_amount_cent: Mapped[int] = mapped_column(BigInteger)
    freight_amount_cent: Mapped[int] = mapped_column(BigInteger, default=0)
    payable_amount_cent: Mapped[int] = mapped_column(BigInteger)
    paid_amount_cent: Mapped[int] = mapped_column(BigInteger, default=0)
    refunded_goods_cent: Mapped[int] = mapped_column(BigInteger, default=0)
    refunded_freight_cent: Mapped[int] = mapped_column(BigInteger, default=0)
    refund_reserved_cent: Mapped[int] = mapped_column(BigInteger, default=0)
    address_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    policy_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    buyer_note: Mapped[str] = mapped_column(String(200), default="")
    internal_note: Mapped[str] = mapped_column(String(200), default="")
    expires_at: Mapped[datetime] = mapped_column(UTC_TIME)
    paid_at: Mapped[datetime | None] = mapped_column(UTC_TIME)
    business_period: Mapped[str | None] = mapped_column(String(7))
    shipped_at: Mapped[datetime | None] = mapped_column(UTC_TIME)
    received_at: Mapped[datetime | None] = mapped_column(UTC_TIME)
    closed_at: Mapped[datetime | None] = mapped_column(UTC_TIME)
    close_reason: Mapped[str | None] = mapped_column(String(200))
    active_payment_id: Mapped[int | None] = mapped_column(
        MALL_ID,
        ForeignKey(
            "mall_payments.id", name="fk_mall_order_payment", use_alter=True, ondelete="RESTRICT"
        ),
    )
    current_invoice_request_id: Mapped[int | None] = mapped_column(
        MALL_ID,
        ForeignKey(
            "mall_invoice_requests.id",
            name="fk_mall_order_invoice_request",
            use_alter=True,
            ondelete="RESTRICT",
        ),
    )
    consent_record_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("consent_records.id", ondelete="RESTRICT")
    )


class MallOrderItem(MallRecord, Base):
    __tablename__ = "mall_order_items"
    __table_args__ = (
        UniqueConstraint("order_id", "sku_id", name="uq_mall_order_sku"),
        CheckConstraint(
            "quantity > 0 AND unit_price_cent > 0 "
            "AND line_amount_cent = unit_price_cent * quantity",
            name="ck_mall_order_line",
        ),
        CheckConstraint(
            "returned_quantity >= 0 AND returned_quantity <= quantity "
            "AND refunded_quantity >= 0 AND aftersale_reserved_quantity >= 0 "
            "AND refunded_quantity + aftersale_reserved_quantity <= quantity",
            name="ck_mall_order_line_quantities",
        ),
        CheckConstraint(
            "refunded_goods_cent >= 0 AND refunded_goods_cent <= line_amount_cent",
            name="ck_mall_order_line_refund",
        ),
    )
    order_id: Mapped[int] = mapped_column(
        MALL_ID, ForeignKey("mall_orders.id", ondelete="RESTRICT")
    )
    sku_id: Mapped[int] = mapped_column(MALL_ID, ForeignKey("mall_skus.id", ondelete="RESTRICT"))
    product_id: Mapped[int] = mapped_column(
        MALL_ID, ForeignKey("mall_products.id", ondelete="RESTRICT")
    )
    product_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    unit_price_cent: Mapped[int] = mapped_column(BigInteger)
    quantity: Mapped[int] = mapped_column(Integer)
    line_amount_cent: Mapped[int] = mapped_column(BigInteger)
    reservation_status: Mapped[str] = mapped_column(String(16), default="reserved")
    returned_quantity: Mapped[int] = mapped_column(Integer, default=0)
    refunded_quantity: Mapped[int] = mapped_column(Integer, default=0)
    aftersale_reserved_quantity: Mapped[int] = mapped_column(Integer, default=0)
    refunded_goods_cent: Mapped[int] = mapped_column(BigInteger, default=0)


class MallShipment(MallRecord, Base):
    __tablename__ = "mall_shipments"
    order_id: Mapped[int] = mapped_column(
        MALL_ID, ForeignKey("mall_orders.id", ondelete="RESTRICT"), unique=True
    )
    courier_code: Mapped[str] = mapped_column(String(32))
    tracking_no: Mapped[str] = mapped_column(String(64))
    shipped_at: Mapped[datetime] = mapped_column(UTC_TIME)
    shipped_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("admin_accounts.id", ondelete="RESTRICT")
    )
    platform_sync_status: Mapped[str] = mapped_column(String(16), default="pending")
    platform_last_error: Mapped[str | None] = mapped_column(String(64))
    platform_synced_at: Mapped[datetime | None] = mapped_column(UTC_TIME)
    platform_confirmation_status: Mapped[str] = mapped_column(String(24), default="unknown")
    platform_confirmed_at: Mapped[datetime | None] = mapped_column(UTC_TIME)
    logistics_provider: Mapped[str] = mapped_column(String(32), default="kuaidi100")
    logistics_status: Mapped[str] = mapped_column(String(24), default="pending")
    provider_state: Mapped[str | None] = mapped_column(String(32))
    tracking_identity_hash: Mapped[str] = mapped_column(String(64), index=True)
    tracking_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    logistics_fetched_at: Mapped[datetime | None] = mapped_column(UTC_TIME)
    logistics_next_query_at: Mapped[datetime | None] = mapped_column(UTC_TIME)
    logistics_last_error_code: Mapped[str | None] = mapped_column(String(64))


class MallAftersale(MallRecord, Base):
    __tablename__ = "mall_aftersales"
    __table_args__ = (
        CheckConstraint(
            "goods_refund_cent >= 0 AND freight_refund_cent >= 0 AND reserved_refund_cent >= 0",
            name="ck_mall_aftersale_amount",
        ),
        CheckConstraint(
            "method IN ('refund_only','return_refund')", name="ck_mall_aftersale_method"
        ),
        Index("ix_mall_aftersale_order_status", "order_id", "status"),
    )
    aftersale_no: Mapped[str] = mapped_column(String(32), unique=True)
    order_id: Mapped[int] = mapped_column(
        MALL_ID, ForeignKey("mall_orders.id", ondelete="RESTRICT")
    )
    buyer_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="RESTRICT"))
    method: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(24), default="submitted")
    reason: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(String(1000), default="")
    proof_file_ids: Mapped[list] = mapped_column(JSON, default=list)
    goods_refund_cent: Mapped[int] = mapped_column(BigInteger, default=0)
    freight_refund_cent: Mapped[int] = mapped_column(BigInteger, default=0)
    reserved_refund_cent: Mapped[int] = mapped_column(BigInteger, default=0)
    audit_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("admin_accounts.id", ondelete="RESTRICT")
    )
    audit_reason: Mapped[str | None] = mapped_column(String(500))
    return_address_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    return_company: Mapped[str | None] = mapped_column(String(32))
    return_tracking_no: Mapped[str | None] = mapped_column(String(64))
    return_sent_at: Mapped[datetime | None] = mapped_column(UTC_TIME)
    received_at: Mapped[datetime | None] = mapped_column(UTC_TIME)
    receipt_result: Mapped[str | None] = mapped_column(String(32))


class MallAftersaleItem(MallRecord, Base):
    __tablename__ = "mall_aftersale_items"
    __table_args__ = (
        UniqueConstraint("aftersale_id", "order_item_id", name="uq_mall_aftersale_line"),
        UniqueConstraint("order_item_id", "active_slot", name="uq_mall_aftersale_active_line"),
        CheckConstraint(
            "quantity > 0 AND stock_return_quantity >= 0 "
            "AND stock_return_quantity <= quantity AND goods_refund_cent >= 0",
            name="ck_mall_aftersale_line_amount",
        ),
        CheckConstraint(
            "active_slot IS NULL OR active_slot = 1", name="ck_mall_aftersale_active_slot"
        ),
    )
    aftersale_id: Mapped[int] = mapped_column(
        MALL_ID, ForeignKey("mall_aftersales.id", ondelete="RESTRICT")
    )
    order_item_id: Mapped[int] = mapped_column(
        MALL_ID, ForeignKey("mall_order_items.id", ondelete="RESTRICT")
    )
    quantity: Mapped[int] = mapped_column(Integer)
    goods_refund_cent: Mapped[int] = mapped_column(BigInteger)
    stock_return_quantity: Mapped[int] = mapped_column(Integer, default=0)
    active_slot: Mapped[int | None] = mapped_column(Integer, default=1)
    inspection_reason: Mapped[str | None] = mapped_column(String(500))
