"""Column conventions shared by the mall's persistent records."""

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Integer
from sqlalchemy.dialects.mysql import BIGINT, DATETIME
from sqlalchemy.orm import Mapped, mapped_column

MALL_ID = BigInteger().with_variant(BIGINT(unsigned=True), "mysql").with_variant(Integer, "sqlite")
UTC_TIME = DateTime().with_variant(DATETIME(fsp=6), "mysql")


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class MallRecord:
    id: Mapped[int] = mapped_column(MALL_ID, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(UTC_TIME, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTC_TIME, default=utc_now, onupdate=utc_now, nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
