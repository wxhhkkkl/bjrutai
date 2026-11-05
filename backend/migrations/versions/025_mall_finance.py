"""Create durable finance, aftersale, file, job and reconciliation records.

Revision ID: 025
Revises: 024

The final section adds the nullable cross-batch and invoice/file-cycle foreign
keys only after both referenced tables exist.  All money and operational
history uses RESTRICT; no finance fact can disappear through a cascade.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "025"
down_revision = "024"
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
        "mall_aftersales",
        *_record_columns(),
        sa.Column("aftersale_no", sa.String(32), nullable=False),
        sa.Column("order_id", _mall_id(), nullable=False),
        sa.Column("buyer_user_id", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("description", sa.String(1000), nullable=False),
        sa.Column("proof_file_ids", mysql.JSON(), nullable=False),
        sa.Column("goods_refund_cent", sa.BigInteger(), nullable=False),
        sa.Column("freight_refund_cent", sa.BigInteger(), nullable=False),
        sa.Column("reserved_refund_cent", sa.BigInteger(), nullable=False),
        sa.Column("audit_by", sa.Integer(), nullable=True),
        sa.Column("audit_reason", sa.String(500), nullable=True),
        sa.Column("return_address_snapshot", mysql.JSON(), nullable=False),
        sa.Column("return_company", sa.String(32), nullable=True),
        sa.Column("return_tracking_no", sa.String(64), nullable=True),
        sa.Column("return_sent_at", _time(), nullable=True),
        sa.Column("received_at", _time(), nullable=True),
        sa.Column("receipt_result", sa.String(32), nullable=True),
        _fk("fk_mall_aftersale_order", ["order_id"], ["mall_orders.id"]),
        _fk("fk_mall_aftersale_buyer", ["buyer_user_id"], ["users.id"]),
        _fk("fk_mall_aftersale_auditor", ["audit_by"], ["admin_accounts.id"]),
        sa.UniqueConstraint("aftersale_no", name="uq_mall_aftersale_no"),
        sa.CheckConstraint(
            "goods_refund_cent >= 0 AND freight_refund_cent >= 0 AND reserved_refund_cent >= 0",
            name="ck_mall_aftersale_amount",
        ),
        sa.CheckConstraint(
            "method IN ('refund_only','return_refund')", name="ck_mall_aftersale_method"
        ),
    )
    op.create_index("ix_mall_aftersale_order_status", "mall_aftersales", ["order_id", "status"])

    op.create_table(
        "mall_aftersale_items",
        *_record_columns(),
        sa.Column("aftersale_id", _mall_id(), nullable=False),
        sa.Column("order_item_id", _mall_id(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("goods_refund_cent", sa.BigInteger(), nullable=False),
        sa.Column("stock_return_quantity", sa.Integer(), nullable=False),
        sa.Column("active_slot", sa.Integer(), nullable=True),
        sa.Column("inspection_reason", sa.String(500), nullable=True),
        _fk("fk_mall_aftersale_item_parent", ["aftersale_id"], ["mall_aftersales.id"]),
        _fk("fk_mall_aftersale_item_order_item", ["order_item_id"], ["mall_order_items.id"]),
        sa.UniqueConstraint("aftersale_id", "order_item_id", name="uq_mall_aftersale_line"),
        sa.UniqueConstraint("order_item_id", "active_slot", name="uq_mall_aftersale_active_line"),
        sa.CheckConstraint(
            "quantity > 0 AND stock_return_quantity >= 0 AND stock_return_quantity <= quantity "
            "AND goods_refund_cent >= 0",
            name="ck_mall_aftersale_line_amount",
        ),
        sa.CheckConstraint(
            "active_slot IS NULL OR active_slot = 1", name="ck_mall_aftersale_active_slot"
        ),
    )

    op.create_table(
        "mall_files",
        *_record_columns(),
        sa.Column("object_key", sa.String(512), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("owner_actor_type", sa.String(16), nullable=False),
        sa.Column("owner_actor_id", sa.BigInteger(), nullable=False),
        sa.Column("order_id", _mall_id(), nullable=True),
        # The invoice FK is added after mall_invoices exists.
        sa.Column("invoice_id", _mall_id(), nullable=True),
        sa.Column("mime", sa.String(100), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("expires_at", _time(), nullable=False),
        _fk("fk_mall_file_order", ["order_id"], ["mall_orders.id"]),
        sa.UniqueConstraint("object_key", name="uq_mall_file_object_key"),
        sa.CheckConstraint("size >= 0", name="ck_mall_file_size"),
        sa.CheckConstraint(
            "purpose IN ('product_image','aftersale_proof','invoice_pdf',"
            "'reconciliation_evidence','finance_export')",
            name="ck_mall_file_purpose",
        ),
    )

    op.create_table(
        "mall_payments",
        *_record_columns(),
        sa.Column("order_id", _mall_id(), nullable=False),
        sa.Column("out_trade_no", sa.String(32), nullable=False),
        sa.Column("channel_transaction_id", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("active_slot", sa.Integer(), nullable=True),
        sa.Column("amount_cent", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("appid_snapshot", sa.String(64), nullable=False),
        sa.Column("mchid_snapshot", sa.String(64), nullable=False),
        sa.Column("prepay_ciphertext", sa.String(2048), nullable=True),
        sa.Column("expires_at", _time(), nullable=False),
        sa.Column("confirmed_at", _time(), nullable=True),
        sa.Column("last_query_at", _time(), nullable=True),
        sa.Column("last_error_code", sa.String(64), nullable=True),
        _fk("fk_mall_payment_order", ["order_id"], ["mall_orders.id"]),
        sa.UniqueConstraint("out_trade_no", name="uq_mall_payment_out_trade"),
        sa.UniqueConstraint("channel_transaction_id", name="uq_mall_payment_channel_transaction"),
        sa.UniqueConstraint("order_id", "active_slot", name="uq_mall_payment_active"),
        sa.CheckConstraint("amount_cent > 0 AND currency = 'CNY'", name="ck_mall_payment_amount"),
        sa.CheckConstraint("active_slot IS NULL OR active_slot = 1", name="ck_mall_payment_slot"),
        sa.CheckConstraint(
            "status IN ('creating','pending','unknown','succeeded','closed','failed')",
            name="ck_mall_payment_status",
        ),
    )

    op.create_table(
        "mall_refunds",
        *_record_columns(),
        sa.Column("aftersale_id", _mall_id(), nullable=False),
        sa.Column("payment_id", _mall_id(), nullable=False),
        sa.Column("order_id", _mall_id(), nullable=False),
        sa.Column("out_refund_no", sa.String(64), nullable=False),
        sa.Column("channel_refund_id", sa.String(64), nullable=True),
        sa.Column("predecessor_refund_id", _mall_id(), nullable=True),
        sa.Column("active_slot", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("goods_refund_cent", sa.BigInteger(), nullable=False),
        sa.Column("freight_refund_cent", sa.BigInteger(), nullable=False),
        sa.Column("total_cent", sa.BigInteger(), nullable=False),
        sa.Column("original_amount_cent", sa.BigInteger(), nullable=False),
        sa.Column("requested_by", sa.Integer(), nullable=False),
        sa.Column("submitted_at", _time(), nullable=True),
        sa.Column("confirmed_at", _time(), nullable=True),
        sa.Column("last_query_at", _time(), nullable=True),
        sa.Column("last_error_code", sa.String(64), nullable=True),
        _fk("fk_mall_refund_aftersale", ["aftersale_id"], ["mall_aftersales.id"]),
        _fk("fk_mall_refund_payment", ["payment_id"], ["mall_payments.id"]),
        _fk("fk_mall_refund_order", ["order_id"], ["mall_orders.id"]),
        _fk("fk_mall_refund_predecessor", ["predecessor_refund_id"], ["mall_refunds.id"]),
        _fk("fk_mall_refund_requester", ["requested_by"], ["admin_accounts.id"]),
        sa.UniqueConstraint("out_refund_no", name="uq_mall_refund_out_refund"),
        sa.UniqueConstraint("channel_refund_id", name="uq_mall_refund_channel_refund"),
        sa.UniqueConstraint("aftersale_id", "active_slot", name="uq_mall_refund_active"),
        sa.CheckConstraint(
            "goods_refund_cent >= 0 AND freight_refund_cent >= 0 "
            "AND total_cent = goods_refund_cent + freight_refund_cent "
            "AND total_cent > 0 AND total_cent <= original_amount_cent",
            name="ck_mall_refund_amount",
        ),
        sa.CheckConstraint("active_slot IS NULL OR active_slot = 1", name="ck_mall_refund_slot"),
        sa.CheckConstraint(
            "status IN ('prepared','processing','unknown','succeeded','closed',"
            "'abnormal','rejected_unaccepted')",
            name="ck_mall_refund_status",
        ),
    )
    op.create_index("ix_mall_refund_query", "mall_refunds", ["status", "last_query_at"])

    op.create_table(
        "mall_invoice_requests",
        *_record_columns(),
        sa.Column("request_no", sa.String(32), nullable=False),
        sa.Column("order_id", _mall_id(), nullable=False),
        sa.Column("buyer_user_id", sa.Integer(), nullable=False),
        sa.Column("buyer_type", sa.String(16), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("tax_no", sa.String(32), nullable=True),
        sa.Column("email", sa.String(254), nullable=True),
        sa.Column("invoice_type", sa.String(32), nullable=False),
        sa.Column("requested_goods_cent", sa.BigInteger(), nullable=False),
        sa.Column("requested_freight_cent", sa.BigInteger(), nullable=False),
        sa.Column("source_order_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("active_slot", sa.Integer(), nullable=True),
        sa.Column("claimed_by", sa.Integer(), nullable=True),
        sa.Column("claimed_at", _time(), nullable=True),
        _fk("fk_mall_invoice_request_order", ["order_id"], ["mall_orders.id"]),
        _fk("fk_mall_invoice_request_buyer", ["buyer_user_id"], ["users.id"]),
        _fk("fk_mall_invoice_request_claimer", ["claimed_by"], ["admin_accounts.id"]),
        sa.UniqueConstraint("request_no", name="uq_mall_invoice_request_no"),
        sa.UniqueConstraint("order_id", "active_slot", name="uq_mall_invoice_request_active"),
        sa.CheckConstraint(
            "active_slot IS NULL OR active_slot = 1", name="ck_mall_invoice_request_slot"
        ),
        sa.CheckConstraint(
            "requested_goods_cent >= 0 AND requested_freight_cent >= 0",
            name="ck_mall_invoice_request_amount",
        ),
        sa.CheckConstraint("buyer_type IN ('personal','company')", name="ck_mall_invoice_buyer"),
    )

    op.create_table(
        "mall_invoices",
        *_record_columns(),
        sa.Column("request_id", _mall_id(), nullable=False),
        sa.Column("order_id", _mall_id(), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("seller_identity", sa.String(64), nullable=False),
        sa.Column("invoice_no", sa.String(64), nullable=False),
        sa.Column("issued_at", _time(), nullable=False),
        sa.Column("total_cent", sa.BigInteger(), nullable=False),
        sa.Column("seller_snapshot", mysql.JSON(), nullable=False),
        # The file FK is added below because files can also point back here.
        sa.Column("file_id", _mall_id(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("original_invoice_id", _mall_id(), nullable=True),
        sa.Column("replacement_for_id", _mall_id(), nullable=True),
        sa.Column("issued_by", sa.Integer(), nullable=True),
        sa.Column("recorded_by", sa.Integer(), nullable=False),
        _fk("fk_mall_invoice_request", ["request_id"], ["mall_invoice_requests.id"]),
        _fk("fk_mall_invoice_order", ["order_id"], ["mall_orders.id"]),
        _fk("fk_mall_invoice_original", ["original_invoice_id"], ["mall_invoices.id"]),
        _fk("fk_mall_invoice_replacement", ["replacement_for_id"], ["mall_invoices.id"]),
        _fk("fk_mall_invoice_issuer", ["issued_by"], ["admin_accounts.id"]),
        _fk("fk_mall_invoice_recorder", ["recorded_by"], ["admin_accounts.id"]),
        sa.UniqueConstraint("seller_identity", "invoice_no", name="uq_mall_invoice_identity"),
        sa.CheckConstraint("total_cent > 0", name="ck_mall_invoice_amount"),
        sa.CheckConstraint(
            "kind IN ('blue','red') AND (kind <> 'red' OR original_invoice_id IS NOT NULL)",
            name="ck_mall_invoice_kind",
        ),
    )

    op.create_table(
        "mall_shipments",
        *_record_columns(),
        sa.Column("order_id", _mall_id(), nullable=False),
        sa.Column("courier_code", sa.String(32), nullable=False),
        sa.Column("tracking_no", sa.String(64), nullable=False),
        sa.Column("shipped_at", _time(), nullable=False),
        sa.Column("shipped_by", sa.Integer(), nullable=False),
        sa.Column("platform_sync_status", sa.String(16), nullable=False),
        sa.Column("platform_last_error", sa.String(64), nullable=True),
        sa.Column("platform_synced_at", _time(), nullable=True),
        sa.Column("platform_confirmation_status", sa.String(24), nullable=False),
        sa.Column("platform_confirmed_at", _time(), nullable=True),
        sa.Column("logistics_provider", sa.String(32), nullable=False),
        sa.Column("logistics_status", sa.String(24), nullable=False),
        sa.Column("provider_state", sa.String(32), nullable=True),
        sa.Column("tracking_identity_hash", sa.String(64), nullable=False),
        sa.Column("tracking_snapshot", mysql.JSON(), nullable=False),
        sa.Column("logistics_fetched_at", _time(), nullable=True),
        sa.Column("logistics_next_query_at", _time(), nullable=True),
        sa.Column("logistics_last_error_code", sa.String(64), nullable=True),
        _fk("fk_mall_shipment_order", ["order_id"], ["mall_orders.id"]),
        _fk("fk_mall_shipment_shipper", ["shipped_by"], ["admin_accounts.id"]),
        sa.UniqueConstraint("order_id", name="uq_mall_shipment_order"),
    )
    op.create_index(
        "ix_mall_shipments_tracking_identity_hash",
        "mall_shipments",
        ["tracking_identity_hash"],
    )

    op.create_table(
        "mall_commands",
        *_record_columns(),
        sa.Column("actor_type", sa.String(16), nullable=False),
        sa.Column("actor_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=True),
        sa.Column("entity_id", sa.BigInteger(), nullable=True),
        sa.Column("lease_until", _time(), nullable=True),
        sa.Column("result_code", sa.String(64), nullable=True),
        sa.UniqueConstraint(
            "actor_type", "actor_id", "action", "key", name="uq_mall_command_intent"
        ),
        sa.CheckConstraint("status IN ('running','completed')", name="ck_mall_command_status"),
    )

    op.create_table(
        "mall_gateway_events",
        *_record_columns(),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("event_id", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(128), nullable=False),
        sa.Column("payload_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("verified_digest", sa.String(64), nullable=False),
        sa.Column("received_at", _time(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("last_error", sa.String(64), nullable=True),
        sa.UniqueConstraint("channel", "event_id", name="uq_mall_gateway_event"),
    )

    op.create_table(
        "mall_jobs",
        *_record_columns(),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.BigInteger(), nullable=False),
        sa.Column("entity_version", sa.Integer(), nullable=False),
        sa.Column("dedupe_key", sa.String(191), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_run_at", _time(), nullable=False),
        sa.Column("lease_owner", sa.String(64), nullable=True),
        sa.Column("lease_until", _time(), nullable=True),
        sa.Column("last_error_code", sa.String(64), nullable=True),
        sa.Column("started_at", _time(), nullable=True),
        sa.Column("finished_at", _time(), nullable=True),
        sa.UniqueConstraint("dedupe_key", name="uq_mall_job_dedupe"),
        sa.CheckConstraint("attempts >= 0", name="ck_mall_job_attempts"),
    )
    op.create_index("ix_mall_job_ready", "mall_jobs", ["status", "next_run_at", "id"])
    op.create_index("ix_mall_job_lease", "mall_jobs", ["lease_until"])

    op.create_table(
        "mall_reconciliation_batches",
        *_record_columns(),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("seller_identity", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("statement_file_id", _mall_id(), nullable=False),
        sa.Column("statement_sha256", sa.String(64), nullable=False),
        sa.Column("expected_paid_cent", sa.BigInteger(), nullable=False),
        sa.Column("expected_refund_cent", sa.BigInteger(), nullable=False),
        sa.Column("local_paid_cent", sa.BigInteger(), nullable=False),
        sa.Column("local_refund_cent", sa.BigInteger(), nullable=False),
        sa.Column("evidence_note", sa.String(1000), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", _time(), nullable=True),
        _fk("fk_mall_recon_batch_file", ["statement_file_id"], ["mall_files.id"]),
        _fk("fk_mall_recon_batch_creator", ["created_by"], ["admin_accounts.id"]),
        _fk("fk_mall_recon_batch_reviewer", ["reviewed_by"], ["admin_accounts.id"]),
        sa.UniqueConstraint(
            "business_date",
            "channel",
            "seller_identity",
            "statement_sha256",
            name="uq_mall_reconciliation_evidence",
        ),
        sa.CheckConstraint(
            "expected_paid_cent >= 0 AND expected_refund_cent >= 0 "
            "AND local_paid_cent >= 0 AND local_refund_cent >= 0",
            name="ck_mall_reconciliation_amount",
        ),
    )

    op.create_table(
        "mall_reconciliation_differences",
        *_record_columns(),
        sa.Column("batch_id", _mall_id(), nullable=False),
        sa.Column("order_id", _mall_id(), nullable=True),
        sa.Column("payment_id", _mall_id(), nullable=True),
        sa.Column("refund_id", _mall_id(), nullable=True),
        sa.Column("external_reference", sa.String(128), nullable=True),
        sa.Column("difference_type", sa.String(32), nullable=False),
        sa.Column("expected_cent", sa.BigInteger(), nullable=False),
        sa.Column("actual_cent", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("assigned_to", sa.Integer(), nullable=True),
        sa.Column("resolution", sa.String(1000), nullable=True),
        sa.Column("evidence_file_ids", mysql.JSON(), nullable=False),
        sa.Column("resolved_at", _time(), nullable=True),
        sa.Column("reviewed_at", _time(), nullable=True),
        _fk("fk_mall_recon_difference_batch", ["batch_id"], ["mall_reconciliation_batches.id"]),
        _fk("fk_mall_recon_difference_order", ["order_id"], ["mall_orders.id"]),
        _fk("fk_mall_recon_difference_payment", ["payment_id"], ["mall_payments.id"]),
        _fk("fk_mall_recon_difference_refund", ["refund_id"], ["mall_refunds.id"]),
        _fk("fk_mall_recon_difference_assignee", ["assigned_to"], ["admin_accounts.id"]),
    )

    # Cross-batch and cycle-safe links: all targets exist at this point.
    op.create_foreign_key(
        "fk_mall_product_cover",
        "mall_products",
        "mall_files",
        ["cover_file_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_mall_order_payment",
        "mall_orders",
        "mall_payments",
        ["active_payment_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_mall_order_invoice_request",
        "mall_orders",
        "mall_invoice_requests",
        ["current_invoice_request_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_mall_stock_aftersale_item",
        "mall_stock_movements",
        "mall_aftersale_items",
        ["aftersale_item_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_mall_file_invoice",
        "mall_files",
        "mall_invoices",
        ["invoice_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_mall_invoice_file",
        "mall_invoices",
        "mall_files",
        ["file_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade():
    # Remove every FK whose referenced table belongs to a different revision
    # (or the invoice/file cycle) before dropping any table.
    op.drop_constraint("fk_mall_invoice_file", "mall_invoices", type_="foreignkey")
    op.drop_constraint("fk_mall_file_invoice", "mall_files", type_="foreignkey")
    op.drop_constraint("fk_mall_stock_aftersale_item", "mall_stock_movements", type_="foreignkey")
    op.drop_constraint("fk_mall_order_invoice_request", "mall_orders", type_="foreignkey")
    op.drop_constraint("fk_mall_order_payment", "mall_orders", type_="foreignkey")
    op.drop_constraint("fk_mall_product_cover", "mall_products", type_="foreignkey")

    op.drop_table("mall_reconciliation_differences")
    op.drop_table("mall_reconciliation_batches")
    op.drop_table("mall_jobs")
    op.drop_table("mall_gateway_events")
    op.drop_table("mall_commands")
    op.drop_table("mall_shipments")
    op.drop_table("mall_invoices")
    op.drop_table("mall_invoice_requests")
    op.drop_table("mall_refunds")
    op.drop_table("mall_payments")
    op.drop_table("mall_files")
    op.drop_table("mall_aftersale_items")
    op.drop_table("mall_aftersales")
