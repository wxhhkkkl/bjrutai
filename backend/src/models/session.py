import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base


class TokenType(str, enum.Enum):
    ACCESS = "access"
    REFRESH = "refresh"


class UserToken(Base):
    __tablename__ = "user_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    token_type: Mapped[TokenType] = mapped_column(
        SAEnum(TokenType, name="token_type_enum"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    family: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # user relationship removed — user_id is polymorphic (users or admin_accounts)
