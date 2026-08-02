import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base


class PromotionCodeStatus(str, enum.Enum):
    AVAILABLE = "available"
    DISABLED = "disabled"
    EXPIRED = "expired"


class PromotionCode(Base):
    __tablename__ = "promotion_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    distributor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("distributors.id"), unique=True, nullable=False
    )
    ref_token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    source_code: Mapped[str] = mapped_column(String(10), default="BJTR")
    qr_image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    share_title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    share_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[PromotionCodeStatus] = mapped_column(
        SAEnum(PromotionCodeStatus, name="promotion_code_status_enum"),
        default=PromotionCodeStatus.AVAILABLE,
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    disabled_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scan_count: Mapped[int] = mapped_column(Integer, default=0)
    lead_count: Mapped[int] = mapped_column(Integer, default=0)
    bind_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    distributor: Mapped["Distributor"] = relationship("Distributor", back_populates="promotion_code")
