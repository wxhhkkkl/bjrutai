"""Channel identities, invoice facts and evidence-backed reconciliation."""

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base
from .mall_base import MALL_ID, UTC_TIME, MallRecord


class MallPayment(MallRecord, Base):
    __tablename__ = "mall_payments"
    __table_args__ = (
        Index("ix_mall_payment_unknown", "status", "unknown_since"),
        UniqueConstraint("order_id", "active_slot", name="uq_mall_payment_active"),
        CheckConstraint("amount_cent > 0 AND currency = 'CNY'", name="ck_mall_payment_amount"),
        CheckConstraint("active_slot IS NULL OR active_slot = 1", name="ck_mall_payment_slot"),
        CheckConstraint(
            "status IN ('creating','pending','unknown','succeeded','closed','failed')",
            name="ck_mall_payment_status",
        ),
    )
    order_id: Mapped[int] = mapped_column(
        MALL_ID, ForeignKey("mall_orders.id", ondelete="RESTRICT")
    )
    out_trade_no: Mapped[str] = mapped_column(String(32), unique=True)
    channel_transaction_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="creating")
    active_slot: Mapped[int | None] = mapped_column(Integer, default=1)
    amount_cent: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="CNY")
    appid_snapshot: Mapped[str] = mapped_column(String(64))
    mchid_snapshot: Mapped[str] = mapped_column(String(64))
    prepay_ciphertext: Mapped[str | None] = mapped_column(String(2048))
    expires_at: Mapped[datetime] = mapped_column(UTC_TIME)
    confirmed_at: Mapped[datetime | None] = mapped_column(UTC_TIME)
    last_query_at: Mapped[datetime | None] = mapped_column(UTC_TIME)
    unknown_since: Mapped[datetime | None] = mapped_column(UTC_TIME)
    last_error_code: Mapped[str | None] = mapped_column(String(64))


class MallRefund(MallRecord, Base):
    __tablename__ = "mall_refunds"
    __table_args__ = (
        UniqueConstraint("aftersale_id", "active_slot", name="uq_mall_refund_active"),
        CheckConstraint(
            "goods_refund_cent >= 0 AND freight_refund_cent >= 0 "
            "AND total_cent = goods_refund_cent + freight_refund_cent "
            "AND total_cent > 0 AND total_cent <= original_amount_cent",
            name="ck_mall_refund_amount",
        ),
        CheckConstraint("active_slot IS NULL OR active_slot = 1", name="ck_mall_refund_slot"),
        CheckConstraint(
            "status IN ('prepared','processing','unknown','succeeded','closed',"
            "'abnormal','rejected_unaccepted')",
            name="ck_mall_refund_status",
        ),
        Index("ix_mall_refund_query", "status", "last_query_at"),
        Index("ix_mall_refund_unknown", "status", "unknown_since"),
    )
    aftersale_id: Mapped[int] = mapped_column(
        MALL_ID, ForeignKey("mall_aftersales.id", ondelete="RESTRICT")
    )
    payment_id: Mapped[int] = mapped_column(
        MALL_ID, ForeignKey("mall_payments.id", ondelete="RESTRICT")
    )
    order_id: Mapped[int] = mapped_column(
        MALL_ID, ForeignKey("mall_orders.id", ondelete="RESTRICT")
    )
    out_refund_no: Mapped[str] = mapped_column(String(64), unique=True)
    channel_refund_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    predecessor_refund_id: Mapped[int | None] = mapped_column(
        MALL_ID, ForeignKey("mall_refunds.id", ondelete="RESTRICT")
    )
    active_slot: Mapped[int | None] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(24), default="prepared")
    goods_refund_cent: Mapped[int] = mapped_column(BigInteger, default=0)
    freight_refund_cent: Mapped[int] = mapped_column(BigInteger, default=0)
    total_cent: Mapped[int] = mapped_column(BigInteger)
    original_amount_cent: Mapped[int] = mapped_column(BigInteger)
    requested_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("admin_accounts.id", ondelete="RESTRICT")
    )
    submitted_at: Mapped[datetime | None] = mapped_column(UTC_TIME)
    confirmed_at: Mapped[datetime | None] = mapped_column(UTC_TIME)
    last_query_at: Mapped[datetime | None] = mapped_column(UTC_TIME)
    unknown_since: Mapped[datetime | None] = mapped_column(UTC_TIME)
    last_error_code: Mapped[str | None] = mapped_column(String(64))


class MallFinanceExportRequest(MallRecord, Base):
    __tablename__ = "mall_finance_export_requests"
    __table_args__ = (
        UniqueConstraint("command_id", name="uq_mall_finance_export_command"),
        UniqueConstraint("file_id", name="uq_mall_finance_export_file"),
        CheckConstraint("kind IN ('payments','refunds')", name="ck_mall_finance_export_kind"),
        CheckConstraint("format IN ('csv','xlsx')", name="ck_mall_finance_export_format"),
        CheckConstraint(
            "status IN ('queued','processing','ready','failed')",
            name="ck_mall_finance_export_status",
        ),
        CheckConstraint("from_at < to_at", name="ck_mall_finance_export_range"),
        CheckConstraint("row_count IS NULL OR row_count >= 0", name="ck_mall_finance_export_rows"),
        Index("ix_mall_finance_export_status", "status", "created_at", "id"),
    )
    kind: Mapped[str] = mapped_column(String(16))
    from_at: Mapped[datetime] = mapped_column(UTC_TIME)
    to_at: Mapped[datetime] = mapped_column(UTC_TIME)
    status_filter: Mapped[str | None] = mapped_column(String(24))
    format: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(16), default="queued")
    requested_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("admin_accounts.id", ondelete="RESTRICT")
    )
    command_id: Mapped[int] = mapped_column(
        MALL_ID, ForeignKey("mall_commands.id", ondelete="RESTRICT")
    )
    file_id: Mapped[int] = mapped_column(
        MALL_ID, ForeignKey("mall_files.id", ondelete="RESTRICT")
    )
    row_count: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(64))
    completed_at: Mapped[datetime | None] = mapped_column(UTC_TIME)


class MallInvoiceRequest(MallRecord, Base):
    __tablename__ = "mall_invoice_requests"
    __table_args__ = (
        UniqueConstraint("order_id", "active_slot", name="uq_mall_invoice_request_active"),
        CheckConstraint(
            "active_slot IS NULL OR active_slot = 1", name="ck_mall_invoice_request_slot"
        ),
        CheckConstraint(
            "requested_goods_cent >= 0 AND requested_freight_cent >= 0",
            name="ck_mall_invoice_request_amount",
        ),
        CheckConstraint("buyer_type IN ('personal','company')", name="ck_mall_invoice_buyer"),
    )
    request_no: Mapped[str] = mapped_column(String(32), unique=True)
    order_id: Mapped[int] = mapped_column(
        MALL_ID, ForeignKey("mall_orders.id", ondelete="RESTRICT")
    )
    consent_record_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("consent_records.id", ondelete="RESTRICT")
    )
    buyer_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="RESTRICT"))
    buyer_type: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(200))
    tax_no: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(254))
    invoice_type: Mapped[str] = mapped_column(String(32), default="digital_normal")
    requested_goods_cent: Mapped[int] = mapped_column(BigInteger, default=0)
    requested_freight_cent: Mapped[int] = mapped_column(BigInteger, default=0)
    source_order_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="submitted")
    info_request_reason: Mapped[str | None] = mapped_column(String(500))
    active_slot: Mapped[int | None] = mapped_column(Integer, default=1)
    claimed_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("admin_accounts.id", ondelete="RESTRICT")
    )
    claimed_at: Mapped[datetime | None] = mapped_column(UTC_TIME)


class MallInvoice(MallRecord, Base):
    __tablename__ = "mall_invoices"
    __table_args__ = (
        UniqueConstraint("seller_identity", "invoice_no", name="uq_mall_invoice_identity"),
        CheckConstraint("total_cent > 0", name="ck_mall_invoice_amount"),
        CheckConstraint(
            "kind IN ('blue','red') AND (kind <> 'red' OR original_invoice_id IS NOT NULL)",
            name="ck_mall_invoice_kind",
        ),
    )
    request_id: Mapped[int] = mapped_column(
        MALL_ID, ForeignKey("mall_invoice_requests.id", ondelete="RESTRICT")
    )
    order_id: Mapped[int] = mapped_column(
        MALL_ID, ForeignKey("mall_orders.id", ondelete="RESTRICT")
    )
    kind: Mapped[str] = mapped_column(String(8))
    seller_identity: Mapped[str | None] = mapped_column(String(64), nullable=True)
    invoice_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    issued_at: Mapped[datetime | None] = mapped_column(UTC_TIME, nullable=True)
    total_cent: Mapped[int] = mapped_column(BigInteger)
    seller_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    file_id: Mapped[int] = mapped_column(
        MALL_ID,
        ForeignKey(
            "mall_files.id", name="fk_mall_invoice_file", use_alter=True, ondelete="RESTRICT"
        ),
    )
    status: Mapped[str] = mapped_column(String(24), default="valid")
    original_invoice_id: Mapped[int | None] = mapped_column(
        MALL_ID, ForeignKey("mall_invoices.id", ondelete="RESTRICT")
    )
    replacement_for_id: Mapped[int | None] = mapped_column(
        MALL_ID, ForeignKey("mall_invoices.id", ondelete="RESTRICT")
    )
    issued_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("admin_accounts.id", ondelete="RESTRICT")
    )
    recorded_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("admin_accounts.id", ondelete="RESTRICT")
    )


class MallReconciliationBatch(MallRecord, Base):
    __tablename__ = "mall_reconciliation_batches"
    __table_args__ = (
        UniqueConstraint(
            "business_date",
            "channel",
            "seller_identity",
            "statement_sha256",
            name="uq_mall_reconciliation_evidence",
        ),
        CheckConstraint(
            "expected_paid_cent >= 0 AND expected_refund_cent >= 0 "
            "AND local_paid_cent >= 0 AND local_refund_cent >= 0",
            name="ck_mall_reconciliation_amount",
        ),
    )
    business_date: Mapped[date] = mapped_column(Date)
    channel: Mapped[str] = mapped_column(String(32), default="wechat")
    seller_identity: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="draft")
    statement_file_id: Mapped[int] = mapped_column(
        MALL_ID, ForeignKey("mall_files.id", ondelete="RESTRICT")
    )
    statement_sha256: Mapped[str] = mapped_column(String(64))
    expected_paid_cent: Mapped[int] = mapped_column(BigInteger, default=0)
    expected_refund_cent: Mapped[int] = mapped_column(BigInteger, default=0)
    local_paid_cent: Mapped[int] = mapped_column(BigInteger, default=0)
    local_refund_cent: Mapped[int] = mapped_column(BigInteger, default=0)
    evidence_note: Mapped[str] = mapped_column(String(1000), default="")
    created_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("admin_accounts.id", ondelete="RESTRICT")
    )
    reviewed_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("admin_accounts.id", ondelete="RESTRICT")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(UTC_TIME)


class MallReconciliationDifference(MallRecord, Base):
    __tablename__ = "mall_reconciliation_differences"
    batch_id: Mapped[int] = mapped_column(
        MALL_ID, ForeignKey("mall_reconciliation_batches.id", ondelete="RESTRICT")
    )
    order_id: Mapped[int | None] = mapped_column(
        MALL_ID, ForeignKey("mall_orders.id", ondelete="RESTRICT")
    )
    payment_id: Mapped[int | None] = mapped_column(
        MALL_ID, ForeignKey("mall_payments.id", ondelete="RESTRICT")
    )
    refund_id: Mapped[int | None] = mapped_column(
        MALL_ID, ForeignKey("mall_refunds.id", ondelete="RESTRICT")
    )
    external_reference: Mapped[str | None] = mapped_column(String(128))
    difference_type: Mapped[str] = mapped_column(String(32))
    expected_cent: Mapped[int] = mapped_column(BigInteger)
    actual_cent: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16), default="open")
    assigned_to: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("admin_accounts.id", ondelete="RESTRICT")
    )
    resolution: Mapped[str | None] = mapped_column(String(1000))
    evidence_file_ids: Mapped[list] = mapped_column(JSON, default=list)
    resolved_at: Mapped[datetime | None] = mapped_column(UTC_TIME)
    reviewed_at: Mapped[datetime | None] = mapped_column(UTC_TIME)
