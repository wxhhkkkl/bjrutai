import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base


class UserType(str, enum.Enum):
    PROMOTER = "promoter"
    DOCTOR = "doctor"
    ADMIN = "admin"
    FINANCE = "finance"
    OPS = "ops"


class ActivationStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DISABLED = "disabled"


class QualificationStatus(str, enum.Enum):
    DRAFT = "draft"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRING = "expiring"
    EXPIRED = "expired"


class AdminStatus(str, enum.Enum):
    ACTIVE = "active"
    DISABLED = "disabled"
    LOCKED = "locked"


# ---------------------------------------------------------------------------
# Junction table: admin_account <-> role
# ---------------------------------------------------------------------------
admin_account_roles = Table(
    "admin_account_roles",
    Base.metadata,
    Column("admin_account_id", Integer, ForeignKey("admin_accounts.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    openid: Mapped[Optional[str]] = mapped_column(String(128), unique=True, nullable=True, index=True)
    user_type: Mapped[UserType] = mapped_column(
        SAEnum(UserType, name="user_type_enum"), default=UserType.PROMOTER
    )
    name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    phone_masked: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    id_card_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    organization: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    activation_status: Mapped[ActivationStatus] = mapped_column(
        SAEnum(ActivationStatus, name="activation_status_enum"),
        default=ActivationStatus.ACTIVE,
    )
    qualification_status: Mapped[QualificationStatus] = mapped_column(
        SAEnum(QualificationStatus, name="qualification_status_enum"),
        default=QualificationStatus.DRAFT,
    )
    profile_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    wechat_bound: Mapped[bool] = mapped_column(Boolean, default=False)
    phone_authorized: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # relationships
    promoter: Mapped[Optional["Promoter"]] = relationship("Promoter", back_populates="user", uselist=False)
    notifications: Mapped[list["Notification"]] = relationship("Notification", back_populates="user")
    # tokens relationship — FK removed; user_id is polymorphic


class AdminAccount(Base):
    __tablename__ = "admin_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[AdminStatus] = mapped_column(
        SAEnum(AdminStatus, name="admin_status_enum"), default=AdminStatus.ACTIVE
    )
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
