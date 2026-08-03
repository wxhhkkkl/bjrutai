import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base


class OrgQualStatus(str, enum.Enum):
    REVIEWING = "reviewing"
    APPROVED = "approved"
    REJECTED = "rejected"


class OrganizationQualification(Base):
    """组织级资质文件，取代个人资质（qualifications）。"""

    __tablename__ = "org_qualifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    legal_entity_name: Mapped[str] = mapped_column(String(256), nullable=False)
    qualification_types: Mapped[list] = mapped_column(JSON, nullable=False)
    credit_code: Mapped[str] = mapped_column(String(64), nullable=False)
    file_urls: Mapped[list] = mapped_column(JSON, nullable=False)
    valid_from: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    valid_until: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[OrgQualStatus] = mapped_column(
        SAEnum(OrgQualStatus, name="org_qual_status_enum", values_callable=lambda x: [e.value for e in x]),
        default=OrgQualStatus.REVIEWING,
    )
    review_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("admin_accounts.id"), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    org: Mapped["Organization"] = relationship("Organization", back_populates="qualifications")
