import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base


class OrgRole(str, enum.Enum):
    MEMBER = "member"
    ADMIN = "admin"


class DistributorStatus(str, enum.Enum):
    ACTIVE = "active"
    DISABLED = "disabled"


class Distributor(Base):
    """组织内人员账户，取代 promoters。单组织归属，org_role 区分成员/组织管理员。"""

    __tablename__ = "distributors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    org_id: Mapped[int] = mapped_column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    org_role: Mapped[OrgRole] = mapped_column(
        SAEnum(OrgRole, name="org_role_enum", values_callable=lambda x: [e.value for e in x]),
        default=OrgRole.MEMBER,
    )
    status: Mapped[DistributorStatus] = mapped_column(
        SAEnum(DistributorStatus, name="distributor_status_enum", values_callable=lambda x: [e.value for e in x]),
        default=DistributorStatus.ACTIVE,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="distributor")
    org: Mapped["Organization"] = relationship("Organization", back_populates="distributors")

    # 业务关系（US6 外键迁移后已接入）
    customers: Mapped[list["Customer"]] = relationship("Customer", back_populates="distributor")
    binding_requests: Mapped[list["BindingRequest"]] = relationship("BindingRequest", back_populates="distributor")
    promotion_code: Mapped[Optional["PromotionCode"]] = relationship(
        "PromotionCode", back_populates="distributor", uselist=False
    )
    contribution_records: Mapped[list["ContributionRecord"]] = relationship(
        "ContributionRecord", back_populates="distributor"
    )
