import enum
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class ArticleStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    UNPUBLISHED = "unpublished"


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    cover_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    category_label: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    category_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("article_categories.id", ondelete="SET NULL"), nullable=True
    )
    tags: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    status: Mapped[ArticleStatus] = mapped_column(
        SAEnum(ArticleStatus, name="article_status_enum"), default=ArticleStatus.DRAFT
    )
    author_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
