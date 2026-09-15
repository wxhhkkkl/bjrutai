import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum as SAEnum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class BannerStatus(str, enum.Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"


class BannerActionType(str, enum.Enum):
    NONE = "none"
    ARTICLE = "article"


class Banner(Base):
    __tablename__ = "banners"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    image_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    action_type: Mapped[BannerActionType] = mapped_column(
        SAEnum(BannerActionType, name="banner_action_type_enum"),
        nullable=False,
        default=BannerActionType.NONE,
    )
    article_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[BannerStatus] = mapped_column(
        SAEnum(BannerStatus, name="banner_status_enum"),
        nullable=False,
        default=BannerStatus.DISABLED,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
