import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Enum as SAEnum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class OrgHistoryAction(str, enum.Enum):
    CREATED = "created"
    UPDATED = "updated"
    MOVED = "moved"
    DELETED = "deleted"


class OrgHistory(Base):
    """组织结构操作历史（FR-004）。"""

    __tablename__ = "org_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action: Mapped[OrgHistoryAction] = mapped_column(
        SAEnum(OrgHistoryAction, name="org_history_action_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    operator_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("admin_accounts.id"), nullable=True)
    detail: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
