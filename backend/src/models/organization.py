import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base


class OrgStatus(str, enum.Enum):
    ACTIVE = "active"
    DISABLED = "disabled"


class Organization(Base):
    """任意深度通用组织树节点，取代 hierarchy_nodes。"""

    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parent_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("organizations.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    org_type: Mapped[str] = mapped_column(String(50), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[OrgStatus] = mapped_column(
        SAEnum(OrgStatus, name="org_status_enum"), default=OrgStatus.ACTIVE
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # self-referential tree
    children: Mapped[list["Organization"]] = relationship(
        "Organization", backref="parent", remote_side=[id]
    )
    distributors: Mapped[list["Distributor"]] = relationship(
        "Distributor", back_populates="org"
    )
    qualifications: Mapped[list["OrganizationQualification"]] = relationship(
        "OrganizationQualification", back_populates="org"
    )
