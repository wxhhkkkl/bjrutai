"""Contribution service: calculation, up-tree aggregation, refund reversal, settlement.

Points are stored as decimal strings (e.g. "1234.56") to avoid float precision issues.
All monetary amounts are in cents (integer), converted to points via the coefficient.
"""

from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.bill import Bill, TransactionStatus
from ..models.binding import Customer
from ..models.contribution import (
    ContributionCategory,
    ContributionRecord,
    ContributionStatus,
    SettlementLog,
    SettlementStatus,
)
from ..models.distributor import Distributor
from ..models.organization import Organization
from ..models.sharing import ContributionCoefficient


class ContributionService:
    """Handles contribution calculation, aggregation and settlement."""

    # ------------------------------------------------------------------
    # Point calculation
    # ------------------------------------------------------------------
    @staticmethod
    def _calc_points(paid_amount_cent: int, coefficient: str) -> str:
        """Convert cents to contribution points using the coefficient.

        Formula: (paid_amount_cent / 100) * coefficient, rounded to 2 decimal places.

        Args:
            paid_amount_cent: Amount paid in cents (integer).
            coefficient: Multiplier as a decimal string (e.g. "1.0", "2.5", "0.3333").

        Returns:
            Points as a 2-decimal string (e.g. "100.00", "250.50", "-50.00").
        """
        yuan = Decimal(paid_amount_cent) / Decimal(100)
        coeff = Decimal(coefficient)
        points = (yuan * coeff).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return str(points)

    # ------------------------------------------------------------------
    # Coefficient lookup
    # ------------------------------------------------------------------
    async def get_coefficient(self, db: AsyncSession) -> str:
        """Return the current active contribution coefficient.

        Reads the most recent entry from contribution_coefficient table.
        Defaults to "1.0" if no coefficient is configured.
        """
        result = await db.execute(
            select(ContributionCoefficient)
            .order_by(ContributionCoefficient.effective_from.desc())
            .limit(1)
        )
        row = result.scalars().first()
        if row is not None:
            return row.coefficient
        return "1.0"

    # ------------------------------------------------------------------
    # Contribution creation from bill
    # ------------------------------------------------------------------
    async def create_from_bill(
        self,
        db: AsyncSession,
        bill: Bill,
    ) -> Optional[ContributionRecord]:
        """Create a ContributionRecord from a Bill.

        Looks up the customer to find the distributor_id, calculates points,
        and inserts a new ContributionRecord. Skips if the bill already
        has a contribution record (idempotency).

        Returns the created record or None if already exists.
        """
        # Check if contribution already exists for this bill
        existing_result = await db.execute(
            select(ContributionRecord).where(
                ContributionRecord.bill_id == bill.id,
                ContributionRecord.source_id == bill.transaction_id,
                ContributionRecord.category == ContributionCategory.BILL,
            )
        )
        if existing_result.scalars().first() is not None:
            return None

        # Get the customer to find promoter
        customer_result = await db.execute(
            select(Customer).where(Customer.id == bill.customer_id)
        )
        customer = customer_result.scalars().first()
        if customer is None:
            return None

        # Get the coefficient
        coefficient = await self.get_coefficient(db)

        # Calculate points
        points = self._calc_points(bill.paid_amount_cent, coefficient)

        record = ContributionRecord(
            distributor_id=customer.distributor_id,
            customer_id=bill.customer_id,
            bill_id=bill.id,
            points=points,
            status=ContributionStatus.PENDING,
            category=ContributionCategory.BILL,
            title=f"消费贡献 - {bill.transaction_id}",
            source_type="bill",
            source_id=bill.transaction_id,
            rule_version=coefficient,
            occurred_at=bill.transaction_time or datetime.now(timezone.utc),
        )
        db.add(record)
        await db.flush()
        await db.refresh(record)
        return record

    # ------------------------------------------------------------------
    # Up-tree aggregation
    # ------------------------------------------------------------------
    async def _get_ancestor_chain(
        self,
        db: AsyncSession,
        distributor_id: int,
    ) -> list[dict]:
        """Walk up the hierarchy from a promoter to root, returning ancestor
        info for each level. Each entry has distributor_id, node_id, level."""
        # Find the promoter's node
        result = await db.execute(
            select(Distributor).where(Distributor.id == distributor_id)
        )
        promoter = result.scalars().first()
        if promoter is None:
            return []

        # Get the node
        result = await db.execute(
            select(Organization).where(Organization.id == promoter.org_id)
        )
        current_node = result.scalars().first()
        if current_node is None:
            return []

        # Walk up
        chain = []
        chain.append({
            "distributor_id": promoter.id,
            "node_id": current_node.id,
            "level": current_node.level,
        })

        visited = {current_node.id}
        while current_node.parent_id is not None:
            parent_result = await db.execute(
                select(Organization).where(
                    Organization.id == current_node.parent_id
                )
            )
            parent_node = parent_result.scalars().first()
            if parent_node is None:
                break
            if parent_node.id in visited:
                break  # cycle guard
            visited.add(parent_node.id)

            # Find promoter for this node
            promoter_result = await db.execute(
                select(Distributor).where(Distributor.org_id == parent_node.id)
            )
            parent_promoter = promoter_result.scalars().first()

            chain.append({
                "distributor_id": parent_promoter.id if parent_promoter else None,
                "node_id": parent_node.id,
                "level": parent_node.level,
            })
            current_node = parent_node

        return chain

    async def _upsert_team_contribution(
        self,
        db: AsyncSession,
        ancestor_promoter_id: int,
        source_promoter_id: int,
        month: str,
        level: int,
    ) -> None:
        """Create or update a team contribution record for an ancestor.

        Source identifies the downstream promoter whose contribution is being
        aggregated upwards.
        """
        source_id = f"month:{month}:promoter:{source_promoter_id}"

        # Check if already exists
        result = await db.execute(
            select(ContributionRecord).where(
                ContributionRecord.distributor_id == ancestor_promoter_id,
                ContributionRecord.source_type == "team_aggregation",
                ContributionRecord.source_id == source_id,
            )
        )
        existing = result.scalars().first()
        if existing is not None:
            return

        record = ContributionRecord(
            distributor_id=ancestor_promoter_id,
            customer_id=0,  # team aggregation, not tied to specific customer
            bill_id=None,
            points="0.00",  # placeholder, actual aggregation via recalculation
            status=ContributionStatus.PENDING,
            category=ContributionCategory.BILL,
            title=f"团队贡献汇总 {month} L{level}",
            source_type="team_aggregation",
            source_id=source_id,
            occurred_at=datetime.now(timezone.utc),
        )
        db.add(record)
        await db.flush()

    async def aggregate_up_tree(
        self,
        db: AsyncSession,
        distributor_id: int,
        month: str,
    ) -> dict:
        """Walk up the hierarchy tree and create team contribution records
        for each ancestor of the given promoter.

        Args:
            db: Database session.
            distributor_id: The leaf promoter whose contribution to aggregate.
            month: Settlement month string (e.g. "2026-07").

        Returns:
            Dict with aggregated count and levels.
        """
        chain = await self._get_ancestor_chain(db, distributor_id)
        if len(chain) <= 1:
            return {"aggregated": 0, "message": "No ancestors to aggregate"}

        # Skip the first entry (self), aggregate to all ancestors
        aggregated = 0
        for entry in chain[1:]:
            if entry["distributor_id"] is None:
                continue  # skip nodes without an assigned promoter
            await self._upsert_team_contribution(
                db,
                ancestor_promoter_id=entry["distributor_id"],
                source_promoter_id=distributor_id,
                month=month,
                level=entry["level"],
            )
            aggregated += 1

        return {
            "aggregated": aggregated,
            "levels": [e["level"] for e in chain[1:] if e["distributor_id"] is not None],
        }

    # ------------------------------------------------------------------
    # Refund reversal
    # ------------------------------------------------------------------
    async def reverse_on_refund(
        self,
        db: AsyncSession,
        original_contribution_id: int,
        refund_amount_cent: int,
    ) -> Optional[ContributionRecord]:
        """Create a reversal ContributionRecord for a refund.

        The reversal points are negative: (refund_amount_cent / 100) * coefficient.

        Updates the original contribution's bill transaction status tracking
        and creates a new REVERSED record linked via reversed_record_id.

        Args:
            db: Database session.
            original_contribution_id: The ContributionRecord to reverse.
            refund_amount_cent: Refund amount in cents.

        Returns:
            The newly created reversal ContributionRecord.
        """
        # Fetch the original contribution
        result = await db.execute(
            select(ContributionRecord).where(
                ContributionRecord.id == original_contribution_id
            )
        )
        original = result.scalars().first()
        if original is None:
            return None

        coefficient = await self.get_coefficient(db)

        # Calculate reversal points (negative)
        reversal_points = self._calc_points(-abs(refund_amount_cent), coefficient)

        reversal = ContributionRecord(
            distributor_id=original.distributor_id,
            customer_id=original.customer_id,
            bill_id=original.bill_id,
            points=reversal_points,
            status=ContributionStatus.REVERSED,
            category=original.category,
            title=f"退款冲正 - {original.source_id or original.title}",
            source_type=original.source_type,
            source_id=original.source_id,
            rule_version=coefficient,
            occurred_at=datetime.now(timezone.utc),
            reversed_record_id=original.id,
            adjustment_reason=f"Refund {refund_amount_cent} cents",
        )
        db.add(reversal)
        await db.flush()
        await db.refresh(reversal)
        return reversal

    # ------------------------------------------------------------------
    # Manual adjustment
    # ------------------------------------------------------------------
    async def adjust_manual(
        self,
        db: AsyncSession,
        contribution_id: int,
        new_points: str,
        reason: str,
        admin_id: int,
    ) -> Optional[ContributionRecord]:
        """Create a manual adjustment contribution record.

        The original record keeps its status. A new ADJUSTMENT record is
        created with the delta.

        Args:
            db: Database session.
            contribution_id: The original ContributionRecord ID.
            new_points: The corrected points value as string.
            reason: Justification for the adjustment.
            admin_id: The admin user performing the adjustment.

        Returns:
            The newly created adjustment ContributionRecord.
        """
        result = await db.execute(
            select(ContributionRecord).where(
                ContributionRecord.id == contribution_id
            )
        )
        original = result.scalars().first()
        if original is None:
            return None

        # Calculate delta
        original_points = Decimal(original.points)
        target_points = Decimal(new_points)
        delta = target_points - original_points
        delta_str = str(delta.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

        adjustment = ContributionRecord(
            distributor_id=original.distributor_id,
            customer_id=original.customer_id,
            bill_id=original.bill_id,
            points=delta_str,
            status=ContributionStatus.CONFIRMED,
            category=ContributionCategory.ADJUSTMENT,
            title=f"手动调整 - {reason}",
            source_type="manual_adjustment",
            source_id=str(original.id),
            occurred_at=datetime.now(timezone.utc),
            adjustment_reason=f"Admin {admin_id}: {reason}",
        )
        db.add(adjustment)
        await db.flush()
        await db.refresh(adjustment)
        return adjustment

    # ------------------------------------------------------------------
    # Monthly settlement
    # ------------------------------------------------------------------
    async def batch_settle(
        self,
        db: AsyncSession,
        month: str,
        batch_size: int = 500,
    ) -> dict:
        """Settle all pending contributions for a given month.

        Uses SELECT FOR UPDATE to lock rows for concurrent safety.
        Processes in batches to avoid long-running transactions.

        Args:
            db: Database session.
            month: Settlement month string (e.g. "2026-07").
            batch_size: Number of records to process per batch.

        Returns:
            Dict with settled_count, total_processed, errors.
        """
        # Create or find settlement log
        log_result = await db.execute(
            select(SettlementLog).where(
                SettlementLog.period == month,
                SettlementLog.status == SettlementStatus.RUNNING,
            )
        )
        log = log_result.scalars().first()

        if log is None:
            # Check for already completed
            completed_result = await db.execute(
                select(SettlementLog).where(
                    SettlementLog.period == month,
                    SettlementLog.status == SettlementStatus.COMPLETED,
                )
            )
            if completed_result.scalars().first() is not None:
                return {"settled_count": 0, "total_processed": 0, "message": "Already settled"}

            log = SettlementLog(
                period=month,
                status=SettlementStatus.RUNNING,
                total_records=0,
                settled_records=0,
            )
            db.add(log)
            await db.flush()

        # Count total pending for this month
        from sqlalchemy import func

        count_result = await db.execute(
            select(func.count(ContributionRecord.id)).where(
                ContributionRecord.status == ContributionStatus.PENDING,
                func.strftime("%Y-%m", ContributionRecord.occurred_at) == month,
            )
        )
        total_pending = count_result.scalar() or 0
        log.total_records = total_pending

        if total_pending == 0:
            log.status = SettlementStatus.COMPLETED
            log.completed_at = datetime.now(timezone.utc)
            await db.flush()
            return {"settled_count": 0, "total_processed": 0, "message": "No pending records"}

        settled = 0
        errors = []

        # Process in batches
        offset = 0
        while offset < total_pending:
            # SELECT FOR UPDATE with LIMIT - locks rows to prevent concurrent modifications
            batch_result = await db.execute(
                select(ContributionRecord)
                .where(
                    ContributionRecord.status == ContributionStatus.PENDING,
                    func.strftime("%Y-%m", ContributionRecord.occurred_at) == month,
                )
                .order_by(ContributionRecord.id)
                .limit(batch_size)
                .offset(offset)
                .with_for_update(skip_locked=True)
            )
            batch = batch_result.scalars().all()

            if not batch:
                break

            now = datetime.now(timezone.utc)
            for record in batch:
                record.status = ContributionStatus.SETTLED
                record.settled_at = now
                settled += 1

            await db.flush()
            offset += batch_size

        log.settled_records = settled
        log.status = SettlementStatus.COMPLETED
        log.completed_at = datetime.now(timezone.utc)
        log.error_message = "; ".join(errors) if errors else None
        await db.flush()

        return {
            "settled_count": settled,
            "total_processed": total_pending,
            "errors": errors if errors else None,
        }
