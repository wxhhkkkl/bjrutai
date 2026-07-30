import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base


class AgreementType(str, enum.Enum):
    PRIVACY_POLICY = "privacy_policy"
    TERMS_OF_SERVICE = "terms_of_service"
    DATA_AUTHORIZATION = "data_authorization"
    MARKETING_CONSENT = "marketing_consent"


class SubjectType(str, enum.Enum):
    USER = "user"
    CUSTOMER = "customer"


class ConsentScene(str, enum.Enum):
    REGISTRATION = "registration"
    BINDING = "binding"
    PROMOTION = "promotion"
    FOLLOWUP = "followup"


class EvidenceType(str, enum.Enum):
    CLICK = "click"
    SIGNATURE = "signature"
    SMS = "sms"
    FACIAL = "facial"


class Agreement(Base):
    __tablename__ = "agreements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[AgreementType] = mapped_column(
        SAEnum(AgreementType, name="agreement_type_enum"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    effective_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ConsentRecord(Base):
    __tablename__ = "consent_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    customer_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    subject_type: Mapped[SubjectType] = mapped_column(
        SAEnum(SubjectType, name="subject_type_enum"), nullable=False
    )
    scene: Mapped[ConsentScene] = mapped_column(
        SAEnum(ConsentScene, name="consent_scene_enum"), nullable=False
    )
    agreement_versions: Mapped[dict] = mapped_column(JSON, default=dict)
    scopes: Mapped[dict] = mapped_column(JSON, default=dict)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    evidence_type: Mapped[Optional[EvidenceType]] = mapped_column(
        SAEnum(EvidenceType, name="evidence_type_enum"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(50), default="active")
    consented_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    customer: Mapped["Customer"] = relationship("Customer", back_populates="consent_records")
