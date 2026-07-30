import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base


class BindingStatus(str, enum.Enum):
    PENDING = "pending"
    BOUND = "bound"
    UNBOUND = "unbound"


class BindingRequestStatus(str, enum.Enum):
    PENDING_MATCH = "pending_match"
    MATCHING = "matching"
    BOUND = "bound"
    NO_CONSUME = "no_consume"
    RETRYING = "retrying"
    MANUAL_REVIEW = "manual_review"
    ABNORMAL = "abnormal"
    UNBOUND = "unbound"
    TRANSFERRED = "transferred"


class MatchLevel(str, enum.Enum):
    EXACT = "exact"
    FUZZY = "fuzzy"
    NONE = "none"


class SourceType(str, enum.Enum):
    SCAN = "scan"
    MANUAL = "manual"
    SHARE = "share"
    IMPORT = "import"


class OperationType(str, enum.Enum):
    BIND = "bind"
    UNBIND = "unbind"
    TRANSFER = "transfer"


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    promoter_id: Mapped[int] = mapped_column(Integer, ForeignKey("promoters.id"), nullable=False, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    phone_masked: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    id_card_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    id_card_masked: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    medical_account_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    family_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    rutai_user_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    binding_status: Mapped[BindingStatus] = mapped_column(
        SAEnum(BindingStatus, name="binding_status_enum"), default=BindingStatus.PENDING
    )
    bound_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    promoter: Mapped["Promoter"] = relationship("Promoter", back_populates="customers")
    bills: Mapped[list["Bill"]] = relationship("Bill", back_populates="customer")
    followup_records: Mapped[list["FollowupRecord"]] = relationship(
        "FollowupRecord", back_populates="customer"
    )
    consent_records: Mapped[list["ConsentRecord"]] = relationship(
        "ConsentRecord", back_populates="customer"
    )


class BindingRequest(Base):
    __tablename__ = "binding_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("customers.id"), nullable=True, index=True
    )
    promoter_id: Mapped[int] = mapped_column(Integer, ForeignKey("promoters.id"), nullable=False, index=True)
    submitted_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    rutai_user_id_masked: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    customer_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    phone_masked: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    id_card_masked: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    source_type: Mapped[SourceType] = mapped_column(
        SAEnum(SourceType, name="source_type_enum"), nullable=False
    )
    source_lead_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    ref_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    consent_record_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("consent_records.id"), nullable=True
    )
    status: Mapped[BindingRequestStatus] = mapped_column(
        SAEnum(BindingRequestStatus, name="binding_request_status_enum"),
        default=BindingRequestStatus.PENDING_MATCH,
    )
    match_level: Mapped[Optional[MatchLevel]] = mapped_column(
        SAEnum(MatchLevel, name="match_level_enum"), nullable=True
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bound_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    promoter: Mapped["Promoter"] = relationship("Promoter", back_populates="binding_requests")
    change_logs: Mapped[list["BindingChangeLog"]] = relationship(
        "BindingChangeLog", back_populates="binding_request"
    )


class BindingChangeLog(Base):
    __tablename__ = "binding_change_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    binding_request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("binding_requests.id"), nullable=False, index=True
    )
    operation_type: Mapped[OperationType] = mapped_column(
        SAEnum(OperationType, name="operation_type_enum"), nullable=False
    )
    previous_promoter_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("promoters.id"), nullable=True
    )
    new_promoter_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("promoters.id"), nullable=True
    )
    operator_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    binding_request: Mapped["BindingRequest"] = relationship(
        "BindingRequest", back_populates="change_logs"
    )
