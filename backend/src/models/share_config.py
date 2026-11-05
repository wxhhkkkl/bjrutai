"""Administrator-managed Mini Program share-card settings."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class MiniProgramShareConfig(Base):
    __tablename__ = "mini_program_share_configs"
    __table_args__ = (UniqueConstraint("page_key", name="uq_mini_share_page_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    page_key: Mapped[str] = mapped_column(String(40), nullable=False)
    page_name: Mapped[str] = mapped_column(String(80), nullable=False)
    friend_title: Mapped[str] = mapped_column(String(100), nullable=False)
    friend_image_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    timeline_title: Mapped[str | None] = mapped_column(String(100), nullable=True)
    timeline_image_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    landing_path: Mapped[str] = mapped_column(String(512), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
