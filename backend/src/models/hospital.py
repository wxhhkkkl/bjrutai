"""Internet-hospital visit intent events.

Only the two events our mini program can observe are stored: the entry-button
tap and the QR-code long press. The target mini program is opened by WeChat
directly, so actual opens are not observable here.
"""

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class HospitalEventType(str, enum.Enum):
    ENTRY_TAP = "entry_tap"
    QR_LONGPRESS = "qr_longpress"


class HospitalVisitEvent(Base):
    __tablename__ = "hospital_visit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    entry_source: Mapped[str] = mapped_column(
        String(64), nullable=False, default="internet_hospital"
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )
    occurred_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
