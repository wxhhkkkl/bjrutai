"""An independent consumption source; never a fabricated hospital Bill."""

from datetime import datetime

from sqlalchemy import JSON, BigInteger, CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base
from .mall_base import MALL_ID, UTC_TIME, MallRecord


class MallConsumption(MallRecord, Base):
    __tablename__ = "mall_consumptions"
    __table_args__ = (
        CheckConstraint(
            "original_goods_cent >= 0 AND successful_goods_refund_cent >= 0 "
            "AND successful_goods_refund_cent <= original_goods_cent "
            "AND performance_base_cent >= 0 AND performance_base_cent <= original_goods_cent",
            name="ck_mall_consumption_amount",
        ),
        Index(
            "ix_mall_consumption_person_period",
            "attributed_distributor_id",
            "business_period",
            "id",
        ),
        Index("ix_mall_consumption_customer_time", "customer_id", "paid_at", "id"),
        Index("ix_mall_consumption_status_time", "status", "paid_at", "id"),
    )
    order_id: Mapped[int] = mapped_column(
        MALL_ID, ForeignKey("mall_orders.id", ondelete="RESTRICT"), unique=True
    )
    buyer_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="RESTRICT"))
    customer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="RESTRICT")
    )
    attributed_distributor_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("distributors.id", ondelete="RESTRICT")
    )
    trade_org_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    name_snapshots: Mapped[dict] = mapped_column(JSON, default=dict)
    paid_at: Mapped[datetime] = mapped_column(UTC_TIME)
    business_period: Mapped[str] = mapped_column(String(7))
    original_goods_cent: Mapped[int] = mapped_column(BigInteger)
    successful_goods_refund_cent: Mapped[int] = mapped_column(BigInteger, default=0)
    performance_base_cent: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(24), default="unassigned")
    source_version: Mapped[int] = mapped_column(Integer, default=1)
    attribution_evidence: Mapped[dict] = mapped_column(JSON, default=dict)
