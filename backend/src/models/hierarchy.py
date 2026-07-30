import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
)
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base


class NodeType(str, enum.Enum):
    HEADQUARTERS = "headquarters"
    REGION = "region"
    BRANCH = "branch"
    PROMOTER = "promoter"
    TERMINAL = "terminal"


# ---------------------------------------------------------------------------
# Snapshot table for hierarchy history
# ---------------------------------------------------------------------------
hierarchy_snapshots = Table(
    "hierarchy_snapshots",
    Base.metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("node_id", Integer, ForeignKey("hierarchy_nodes.id"), nullable=False),
    Column("snapshot_data", JSON, default=dict),
    Column("created_at", DateTime, default=datetime.utcnow),
)


class HierarchyNode(Base):
    __tablename__ = "hierarchy_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parent_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("hierarchy_nodes.id"), nullable=True, index=True
    )
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    node_type: Mapped[NodeType] = mapped_column(
        SAEnum(NodeType, name="node_type_enum"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # self-referential
    children: Mapped[list["HierarchyNode"]] = relationship(
        "HierarchyNode", backref="parent", remote_side=[id]
    )
    promoter: Mapped[Optional["Promoter"]] = relationship("Promoter", back_populates="node", uselist=False)


class Promoter(Base):
    __tablename__ = "promoters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    node_id: Mapped[int] = mapped_column(Integer, ForeignKey("hierarchy_nodes.id"), unique=True, nullable=False)
    qualification_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="promoter")
    node: Mapped["HierarchyNode"] = relationship("HierarchyNode", back_populates="promoter")

    # Business relationships
    qualifications: Mapped[list["Qualification"]] = relationship("Qualification", back_populates="promoter")
    customers: Mapped[list["Customer"]] = relationship("Customer", back_populates="promoter")
    binding_requests: Mapped[list["BindingRequest"]] = relationship(
        "BindingRequest", back_populates="promoter"
    )
    promotion_code: Mapped[Optional["PromotionCode"]] = relationship(
        "PromotionCode", back_populates="promoter", uselist=False
    )
    contribution_records: Mapped[list["ContributionRecord"]] = relationship(
        "ContributionRecord", back_populates="promoter"
    )
