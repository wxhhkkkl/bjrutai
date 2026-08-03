"""Customer change log — audit trail for distributor (推广员) reassignment.

Records the initial promoter assignment on manual customer creation (created)
and every subsequent promoter change (transfer). Satisfies FR-012: every
promoter change carries operator, time, previous/new distributor, and reason.
"""

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class ChangeOperationType(str, enum.Enum):
    CREATED = "created"
    TRANSFER = "transfer"


class CustomerChangeLog(Base):
    __tablename__ = "customer_change_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    operation_type: Mapped[ChangeOperationType] = mapped_column(
        SAEnum(
            ChangeOperationType,
            name="change_operation_type_enum",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    # Distributor IDs for audit history (created/transfer). Plain integers —
    # a manually-created customer may have no binding request, so this table
    # deliberately does not FK to binding_requests.
    previous_distributor_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    new_distributor_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    operator_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
