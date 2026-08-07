"""Report model for multi-dimensional reconciliation reports (US8)."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    start_date: Mapped[str] = mapped_column(String(10), nullable=False)
    end_date: Mapped[str] = mapped_column(String(10), nullable=False)
    dimensions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    sections: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    generated_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="reconciliation", server_default="reconciliation")
    period: Mapped[Optional[str]] = mapped_column(String(7), nullable=True, index=True)  # 'YYYY-MM' for settlement reports
    status: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # settlement: pending/reviewed/rejected
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
