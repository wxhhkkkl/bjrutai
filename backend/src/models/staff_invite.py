"""Organization-admin invite codes for adding business members."""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class StaffInviteCodeStatus(str, enum.Enum):
    AVAILABLE = "available"
    DISABLED = "disabled"
    EXPIRED = "expired"


class StaffInviteCode(Base):
    __tablename__ = "staff_invite_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id"), nullable=False, index=True
    )
    inviter_distributor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("distributors.id"), unique=True, nullable=False, index=True
    )
    ref_token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    status: Mapped[StaffInviteCodeStatus] = mapped_column(
        SAEnum(
            StaffInviteCodeStatus,
            name="staff_invite_code_status_enum",
            values_callable=lambda values: [value.value for value in values],
        ),
        default=StaffInviteCodeStatus.AVAILABLE,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    joined_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
