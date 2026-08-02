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
    Column("node_id", Integer, ForeignKey("_deprecated_hierarchy_nodes.id"), nullable=False),
    Column("snapshot_data", JSON, default=dict),
    Column("created_at", DateTime, default=datetime.utcnow),
)


class HierarchyNode(Base):
    # 迁移 004 已将表重命名（数据保留），映射到废弃表
    __tablename__ = "_deprecated_hierarchy_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parent_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("_deprecated_hierarchy_nodes.id"), nullable=True, index=True
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
    # 迁移 004 已将表重命名（数据保留），映射到废弃表
    __tablename__ = "_deprecated_promoters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    node_id: Mapped[int] = mapped_column(Integer, ForeignKey("_deprecated_hierarchy_nodes.id"), unique=True, nullable=False)
    qualification_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="promoter")
    node: Mapped["HierarchyNode"] = relationship("HierarchyNode", back_populates="promoter")

    # Business relationships（仅保留仍匹配 back_populates 的关系；
    # customers/promotion_code/contribution_records/binding_requests 已迁移到 Distributor）
    qualifications: Mapped[list["Qualification"]] = relationship("Qualification", back_populates="promoter")
