"""Durable commands, inbox/work queue, scoped files and single-store settings."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import MEDIUMBLOB
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base
from .mall_base import MALL_ID, UTC_TIME, MallRecord


class MallFile(MallRecord, Base):
    __tablename__ = "mall_files"
    __table_args__ = (
        CheckConstraint("size >= 0", name="ck_mall_file_size"),
        CheckConstraint(
            "purpose IN ('product_image','aftersale_proof','invoice_pdf',"
            "'reconciliation_evidence','finance_export','attribution_evidence',"
            "'performance_adjustment_evidence')",
            name="ck_mall_file_purpose",
        ),
    )
    object_key: Mapped[str] = mapped_column(String(512), unique=True)
    purpose: Mapped[str] = mapped_column(String(32))
    owner_actor_type: Mapped[str] = mapped_column(String(16))
    owner_actor_id: Mapped[int] = mapped_column(BigInteger)
    order_id: Mapped[int | None] = mapped_column(
        MALL_ID, ForeignKey("mall_orders.id", ondelete="RESTRICT")
    )
    invoice_id: Mapped[int | None] = mapped_column(
        MALL_ID,
        ForeignKey(
            "mall_invoices.id", name="fk_mall_file_invoice", use_alter=True, ondelete="RESTRICT"
        ),
    )
    mime: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="uploading")
    expires_at: Mapped[datetime] = mapped_column(UTC_TIME)


class MallCommand(MallRecord, Base):
    __tablename__ = "mall_commands"
    __table_args__ = (
        UniqueConstraint("actor_type", "actor_id", "action", "key", name="uq_mall_command_intent"),
        CheckConstraint("status IN ('running','completed')", name="ck_mall_command_status"),
    )
    actor_type: Mapped[str] = mapped_column(String(16))
    actor_id: Mapped[int] = mapped_column(BigInteger)
    action: Mapped[str] = mapped_column(String(128))
    key: Mapped[str] = mapped_column(String(128))
    payload_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="running")
    entity_type: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[int | None] = mapped_column(BigInteger)
    lease_until: Mapped[datetime | None] = mapped_column(UTC_TIME)
    result_code: Mapped[str | None] = mapped_column(String(64))


class MallGatewayEvent(MallRecord, Base):
    __tablename__ = "mall_gateway_events"
    __table_args__ = (UniqueConstraint("channel", "event_id", name="uq_mall_gateway_event"),)
    channel: Mapped[str] = mapped_column(String(32))
    event_id: Mapped[str] = mapped_column(String(128))
    event_type: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[str] = mapped_column(String(128))
    payload_ciphertext: Mapped[bytes | None] = mapped_column(
        LargeBinary().with_variant(MEDIUMBLOB(), "mysql")
    )
    verified_digest: Mapped[str] = mapped_column(String(64))
    received_at: Mapped[datetime] = mapped_column(UTC_TIME)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    last_error: Mapped[str | None] = mapped_column(String(64))


class MallJob(MallRecord, Base):
    __tablename__ = "mall_jobs"
    __table_args__ = (
        Index("ix_mall_job_ready", "status", "next_run_at", "id"),
        Index("ix_mall_job_lease", "lease_until"),
        CheckConstraint("attempts >= 0", name="ck_mall_job_attempts"),
    )
    kind: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[int] = mapped_column(BigInteger)
    entity_version: Mapped[int] = mapped_column(Integer)
    dedupe_key: Mapped[str] = mapped_column(String(191), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="ready")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_run_at: Mapped[datetime] = mapped_column(UTC_TIME)
    lease_owner: Mapped[str | None] = mapped_column(String(64))
    lease_until: Mapped[datetime | None] = mapped_column(UTC_TIME)
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(UTC_TIME)
    finished_at: Mapped[datetime | None] = mapped_column(UTC_TIME)
    notification_payload: Mapped[dict | None] = mapped_column(JSON)
    responsibility_role: Mapped[str | None] = mapped_column(String(32))
    responsibility_first_discovered_at: Mapped[datetime | None] = mapped_column(UTC_TIME)
    responsibility_last_verified_at: Mapped[datetime | None] = mapped_column(UTC_TIME)
    responsibility_evidence: Mapped[dict | None] = mapped_column(JSON)
    responsibility_next_step: Mapped[str | None] = mapped_column(String(500))
    resolution_code: Mapped[str | None] = mapped_column(String(64))
    resolution_summary: Mapped[str | None] = mapped_column(String(500))
    resolved_by_type: Mapped[str | None] = mapped_column(String(16))
    resolved_by_id: Mapped[int | None] = mapped_column(BigInteger)
    resolved_at: Mapped[datetime | None] = mapped_column(UTC_TIME)


class MallSettings(MallRecord, Base):
    __tablename__ = "mall_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_mall_settings_singleton"),
        CheckConstraint(
            "freight_cent >= 0 AND payment_minutes > 0 "
            "AND auto_receive_days > 0 AND aftersale_days > 0",
            name="ck_mall_settings_values",
        ),
        CheckConstraint("freight_mode IN ('free','fixed')", name="ck_mall_settings_freight"),
    )
    id: Mapped[int] = mapped_column(MALL_ID, primary_key=True, autoincrement=False, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    purchase_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    freight_mode: Mapped[str] = mapped_column(String(16), default="fixed")
    freight_cent: Mapped[int] = mapped_column(BigInteger, default=0)
    blocked_regions: Mapped[list] = mapped_column(JSON, default=list)
    payment_minutes: Mapped[int] = mapped_column(Integer, default=30)
    auto_receive_days: Mapped[int] = mapped_column(Integer, default=15)
    aftersale_days: Mapped[int] = mapped_column(Integer, default=15)
    dispatch_address_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    return_address_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    contact: Mapped[str] = mapped_column(String(500), default="")
    return_instructions: Mapped[str] = mapped_column(Text, default="")
    policy_versions: Mapped[dict] = mapped_column(JSON, default=dict)
