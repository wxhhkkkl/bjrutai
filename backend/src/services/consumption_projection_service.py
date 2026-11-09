"""Read-only projection across legacy bills and independent mall sources.

Legacy bills keep their established attribution, time, status and partial-refund
rules. Paid mall orders contribute only their goods performance base and fixed
Beijing business period; freight and unassigned orders are never attributed.
"""

import base64
import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.exceptions import BadRequestException
from ..models.bill import Bill, TransactionStatus
from ..models.binding import Customer
from ..models.distributor import Distributor
from ..models.mall_consumption import MallConsumption
from ..models.mall_trade import MallOrder
from ..models.organization import Organization
from ..models.user import User
from .consumption_service import period_start_end

_SOURCE_RANK = {"legacy_bill": 1, "mall_order": 2}


class ConsumptionProjectionService:
    """Combine source records without assigning either source a false identity."""

    async def aggregate_by_distributor(
        self,
        db: AsyncSession,
        distributor_ids: list[int],
        month: Optional[str] = None,
        organization_ids: Optional[set[int]] = None,
    ) -> dict[int, int]:
        if not distributor_ids:
            return {}
        totals = await self._aggregate_legacy_bills(
            db,
            distributor_ids=distributor_ids,
            month=month,
            organization_ids=organization_ids,
        )
        mall_totals = await self._aggregate_mall(
            db,
            distributor_ids=distributor_ids,
            month=month,
            organization_ids=organization_ids,
        )
        for distributor_id, amount in mall_totals.items():
            totals[distributor_id] = totals.get(distributor_id, 0) + amount
        return totals

    async def aggregate_by_organization(
        self,
        db: AsyncSession,
        organization_ids: set[int],
        month: Optional[str] = None,
    ) -> dict[int, int]:
        if not organization_ids:
            return {}
        effective_organization = func.coalesce(Bill.attributed_org_id, Distributor.org_id)
        legacy_stmt = (
            select(effective_organization, func.coalesce(func.sum(Bill.paid_amount_cent), 0))
            .select_from(Customer)
            .join(Bill, Bill.customer_id == Customer.id)
            .join(Distributor, Distributor.id == Customer.distributor_id)
            .where(
                effective_organization.in_(organization_ids),
                Bill.transaction_status.notin_(
                    [TransactionStatus.REFUNDED, TransactionStatus.CANCELLED]
                ),
            )
        )
        if month is not None:
            start, end = period_start_end(month)
            legacy_stmt = legacy_stmt.where(
                Bill.transaction_time >= start, Bill.transaction_time < end
            )
        legacy = {
            int(identity): int(amount)
            for identity, amount in (
                await db.execute(legacy_stmt.group_by(effective_organization))
            ).all()
            if identity is not None
        }
        mall = await self._aggregate_mall(db, organization_ids=organization_ids, month=month)
        for org_id, amount in mall.items():
            legacy[org_id] = legacy.get(org_id, 0) + amount
        return legacy

    async def aggregate_by_customer(
        self,
        db: AsyncSession,
        customer_ids: list[int],
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> dict[int, int]:
        if not customer_ids:
            return {}
        legacy_stmt = select(
            Bill.customer_id, func.coalesce(func.sum(Bill.paid_amount_cent), 0)
        ).where(
            Bill.customer_id.in_(customer_ids),
            Bill.transaction_status.notin_(
                [TransactionStatus.REFUNDED, TransactionStatus.CANCELLED]
            ),
        )
        if start is not None:
            legacy_stmt = legacy_stmt.where(
                Bill.transaction_time >= start, Bill.transaction_time < end
            )
        totals = {
            int(identity): int(amount)
            for identity, amount in (await db.execute(legacy_stmt.group_by(Bill.customer_id))).all()
        }

        mall_stmt = select(
            MallConsumption.customer_id,
            func.coalesce(func.sum(MallConsumption.performance_base_cent), 0),
        ).where(
            MallConsumption.customer_id.in_(customer_ids),
            MallConsumption.status == "assigned",
        )
        if start is not None:
            mall_stmt = mall_stmt.where(
                MallConsumption.paid_at >= start, MallConsumption.paid_at < end
            )
        for identity, amount in (
            await db.execute(mall_stmt.group_by(MallConsumption.customer_id))
        ).all():
            totals[int(identity)] = totals.get(int(identity), 0) + int(amount)
        return totals

    async def list_person_details(
        self,
        db: AsyncSession,
        distributor_id: int,
        month: Optional[str] = None,
        status: Optional[str] = None,
        cursor: Optional[str] = None,
        page_size: int = 20,
    ) -> dict:
        if not 1 <= page_size <= 100:
            raise BadRequestException(message="pageSize必须在1到100之间")
        cursor_key = _decode_cursor(cursor) if cursor else None
        bill_time = Bill.transaction_time
        bill_id = Bill.id
        mall_time = MallConsumption.paid_at
        mall_id = MallOrder.id

        bill_distributor = func.coalesce(Bill.attributed_distributor_id, Customer.distributor_id)
        bill_stmt = (
            select(Bill, Customer.name, Customer.phone_masked, bill_distributor)
            .select_from(Customer)
            .join(Bill, Bill.customer_id == Customer.id)
            .join(Distributor, Distributor.id == Customer.distributor_id)
            .where(bill_distributor == distributor_id)
        )
        mall_stmt = (
            select(MallConsumption, MallOrder)
            .join(MallOrder, MallOrder.id == MallConsumption.order_id)
            .where(
                MallConsumption.attributed_distributor_id == distributor_id,
                MallConsumption.status == "assigned",
            )
        )
        if month:
            start, end = period_start_end(month)
            bill_stmt = bill_stmt.where(bill_time >= start, bill_time < end)
            mall_stmt = mall_stmt.where(MallConsumption.business_period == month)
        if status:
            bill_stmt = bill_stmt.where(Bill.transaction_status == status)
            if status != "paid":
                mall_stmt = mall_stmt.where(False)
        if cursor_key:
            cursor_time, cursor_rank, cursor_id = cursor_key
            bill_stmt = bill_stmt.where(
                _after_cursor(
                    bill_time,
                    bill_id,
                    _SOURCE_RANK["legacy_bill"],
                    cursor_time,
                    cursor_rank,
                    cursor_id,
                )
            )
            mall_stmt = mall_stmt.where(
                _after_cursor(
                    mall_time,
                    mall_id,
                    _SOURCE_RANK["mall_order"],
                    cursor_time,
                    cursor_rank,
                    cursor_id,
                )
            )

        bill_rows = (
            await db.execute(
                bill_stmt.order_by(bill_time.desc(), bill_id.desc()).limit(page_size + 1)
            )
        ).all()
        mall_rows = (
            await db.execute(
                mall_stmt.order_by(mall_time.desc(), mall_id.desc()).limit(page_size + 1)
            )
        ).all()

        items = [
            _bill_detail(bill, customer_name, phone_masked)
            for bill, customer_name, phone_masked, _ in bill_rows
        ]
        items.extend(_mall_detail(source, order) for source, order in mall_rows)
        items.sort(key=_detail_sort_key, reverse=True)
        has_more = len(items) > page_size
        page = items[:page_size]
        next_cursor = _encode_cursor(page[-1]) if has_more and page else None
        for item in page:
            item.pop("_occurredAt", None)
            item.pop("_sourceRank", None)
            item.pop("_nativeId", None)
        return {"items": page, "nextCursor": next_cursor, "hasMore": has_more}

    async def list_admin_latest(
        self,
        db: AsyncSession,
        *,
        distributor_ids: Optional[set[int]] = None,
        organization_ids: Optional[set[int]] = None,
        limit: int = 30,
    ) -> list[dict]:
        if not 1 <= limit <= 100:
            raise BadRequestException(message="limit必须在1到100之间")
        bill_distributor = func.coalesce(Bill.attributed_distributor_id, Customer.distributor_id)
        bill_org = func.coalesce(Bill.attributed_org_id, Distributor.org_id)
        bill_stmt = (
            select(
                Bill,
                Customer,
                bill_distributor,
                bill_org,
                User.name,
                Organization.name,
            )
            .select_from(Bill)
            .join(Customer, Customer.id == Bill.customer_id)
            .join(Distributor, Distributor.id == Customer.distributor_id)
            .join(User, User.id == Distributor.user_id)
            .join(Organization, Organization.id == Distributor.org_id)
            .where(
                Bill.transaction_status.notin_(
                    [TransactionStatus.REFUNDED, TransactionStatus.CANCELLED]
                )
            )
        )
        mall_stmt = (
            select(
                MallConsumption,
                MallOrder,
                Distributor,
                User.name,
                Organization.name,
            )
            .join(MallOrder, MallOrder.id == MallConsumption.order_id)
            .join(Distributor, Distributor.id == MallConsumption.attributed_distributor_id)
            .join(User, User.id == Distributor.user_id)
            .join(Organization, Organization.id == Distributor.org_id)
            .where(
                MallConsumption.status == "assigned",
                MallConsumption.attributed_distributor_id.is_not(None),
            )
        )
        if organization_ids is not None:
            if not organization_ids:
                return []
            bill_stmt = bill_stmt.where(bill_org.in_(organization_ids))
            mall_stmt = mall_stmt.where(Distributor.org_id.in_(organization_ids))
        elif distributor_ids is not None:
            if not distributor_ids:
                return []
            bill_stmt = bill_stmt.where(bill_distributor.in_(distributor_ids))
            mall_stmt = mall_stmt.where(
                MallConsumption.attributed_distributor_id.in_(distributor_ids)
            )

        bills = (
            await db.execute(
                bill_stmt.order_by(Bill.transaction_time.desc(), Bill.id.desc()).limit(limit)
            )
        ).all()
        mall_sources = (
            await db.execute(
                mall_stmt.order_by(MallConsumption.paid_at.desc(), MallOrder.id.desc()).limit(limit)
            )
        ).all()
        items = []
        for bill, customer, distributor_id, org_id, person_name, org_name in bills:
            item = _bill_detail(bill, customer.name, customer.phone_masked)
            item.update(
                {
                    "id": str(bill.id),
                    "distributorId": str(distributor_id),
                    "personName": bill.attributed_person_name or person_name,
                    "orgName": bill.attributed_org_name or org_name,
                    "source": bill.source,
                    "sourceType": "legacy_bill",
                }
            )
            items.append(item)
        for source, order, distributor, person_name, org_name in mall_sources:
            item = _mall_detail(source, order)
            item.update(
                {
                    "distributorId": str(distributor.id),
                    "personName": person_name,
                    "orgName": org_name,
                    "sourceType": "mall_order",
                }
            )
            items.append(item)
        items.sort(key=_detail_sort_key, reverse=True)
        page = items[:limit]
        for item in page:
            item.pop("_occurredAt", None)
            item.pop("_sourceRank", None)
            item.pop("_nativeId", None)
        return page

    async def _aggregate_legacy_bills(
        self,
        db: AsyncSession,
        *,
        distributor_ids: Optional[list[int]] = None,
        organization_ids: Optional[set[int]] = None,
        month: Optional[str] = None,
    ) -> dict[int, int]:
        effective_distributor = func.coalesce(
            Bill.attributed_distributor_id, Customer.distributor_id
        )
        effective_organization = func.coalesce(Bill.attributed_org_id, Distributor.org_id)
        stmt = (
            select(effective_distributor, func.coalesce(func.sum(Bill.paid_amount_cent), 0))
            .select_from(Customer)
            .join(Bill, Bill.customer_id == Customer.id)
            .join(Distributor, Distributor.id == Customer.distributor_id)
            .where(
                Bill.transaction_status.notin_(
                    [TransactionStatus.REFUNDED, TransactionStatus.CANCELLED]
                )
            )
        )
        if distributor_ids is not None:
            stmt = stmt.where(effective_distributor.in_(distributor_ids))
        if organization_ids is not None:
            stmt = stmt.where(effective_organization.in_(organization_ids))
        if month is not None:
            start, end = period_start_end(month)
            stmt = stmt.where(Bill.transaction_time >= start, Bill.transaction_time < end)
        rows = (await db.execute(stmt.group_by(effective_distributor))).all()
        return {int(identity): int(amount) for identity, amount in rows if identity is not None}

    async def _aggregate_mall(
        self,
        db: AsyncSession,
        *,
        distributor_ids: Optional[list[int]] = None,
        organization_ids: Optional[set[int]] = None,
        month: Optional[str] = None,
    ) -> dict[int, int]:
        owner = (
            MallConsumption.attributed_distributor_id
            if distributor_ids is not None
            else Distributor.org_id
        )
        stmt = (
            select(owner, func.coalesce(func.sum(MallConsumption.performance_base_cent), 0))
            .join(Distributor, Distributor.id == MallConsumption.attributed_distributor_id)
            .where(
                MallConsumption.status == "assigned",
                owner.is_not(None),
            )
        )
        if distributor_ids is not None:
            stmt = stmt.where(owner.in_(distributor_ids))
        if organization_ids is not None:
            stmt = stmt.where(Distributor.org_id.in_(organization_ids))
        if month is not None:
            stmt = stmt.where(MallConsumption.business_period == month)
        rows = (await db.execute(stmt.group_by(owner))).all()
        return {int(identity): int(amount) for identity, amount in rows if identity is not None}


def _after_cursor(time_column, id_column, rank, cursor_time, cursor_rank, cursor_id):
    return or_(
        time_column < cursor_time,
        and_(
            time_column == cursor_time,
            or_(rank < cursor_rank, and_(rank == cursor_rank, id_column < cursor_id)),
        ),
    )


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _bill_detail(bill: Bill, customer_name: Optional[str], phone_masked: Optional[str]) -> dict:
    occurred = _normalize_datetime(bill.transaction_time)
    return {
        "id": bill.id,
        "source": "legacy_bill",
        "sourceId": str(bill.id),
        "title": bill.transaction_id,
        "amountCent": bill.paid_amount_cent,
        "status": (
            bill.transaction_status.value
            if hasattr(bill.transaction_status, "value")
            else str(bill.transaction_status)
        ),
        "customerId": str(bill.customer_id),
        "customerName": customer_name,
        "phoneMasked": phone_masked,
        "occurredAt": bill.transaction_time.isoformat() if bill.transaction_time else None,
        "_occurredAt": occurred,
        "_sourceRank": _SOURCE_RANK["legacy_bill"],
        "_nativeId": bill.id,
    }


def _mall_detail(source: MallConsumption, order: MallOrder) -> dict:
    occurred = _normalize_datetime(source.paid_at)
    snapshots = source.name_snapshots or {}
    return {
        "id": f"mall_order:{order.id}",
        "source": "mall_order",
        "sourceId": str(order.id),
        "title": order.order_no,
        "amountCent": source.performance_base_cent,
        "status": "paid",
        "customerId": str(source.customer_id) if source.customer_id else None,
        "customerName": snapshots.get("customer"),
        "phoneMasked": None,
        "occurredAt": source.paid_at.isoformat() if source.paid_at else None,
        "_occurredAt": occurred,
        "_sourceRank": _SOURCE_RANK["mall_order"],
        "_nativeId": order.id,
    }


def _detail_sort_key(item: dict) -> tuple[datetime, int, int]:
    return item["_occurredAt"], item["_sourceRank"], item["_nativeId"]


def _encode_cursor(item: dict) -> str:
    payload = {
        "time": item["_occurredAt"].isoformat(timespec="microseconds"),
        "rank": item["_sourceRank"],
        "id": item["_nativeId"],
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, int, int]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        occurred = datetime.fromisoformat(payload["time"])
        rank = int(payload["rank"])
        identity = int(payload["id"])
        if rank not in _SOURCE_RANK.values() or identity <= 0:
            raise ValueError
        return _normalize_datetime(occurred), rank, identity
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeError) as exc:
        raise BadRequestException(message="cursor无效") from exc
