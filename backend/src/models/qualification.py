import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base


class QualificationType(str, enum.Enum):
    INDIVIDUAL = "individual"
    ENTERPRISE = "enterprise"


class QualStatus(str, enum.Enum):
    DRAFT = "draft"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRING = "expiring"
    EXPIRED = "expired"


class Qualification(Base):
    # 迁移 004 已将表重命名（数据保留），映射到废弃表
    __tablename__ = "_deprecated_qualifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    promoter_id: Mapped[int] = mapped_column(Integer, ForeignKey("_deprecated_promoters.id"), nullable=False, index=True)
    legal_entity: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    qualification_type: Mapped[QualificationType] = mapped_column(
        SAEnum(QualificationType, name="qualification_type_enum"), nullable=False
    )
    credit_code_encrypted: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    credit_code_masked: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[QualStatus] = mapped_column(
        SAEnum(QualStatus, name="qual_status_enum"), default=QualStatus.DRAFT
    )
    file_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    file_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    file_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    rejected_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    promoter: Mapped["Promoter"] = relationship("Promoter", back_populates="qualifications")
