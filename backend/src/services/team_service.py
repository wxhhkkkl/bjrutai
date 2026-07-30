"""Team service: team contribution summary and drill-down with branch access control.

Monetary amounts are intentionally excluded from all responses --
only contribution points are shown.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.exceptions import ForbiddenException, NotFoundException
from ..models.contribution import ContributionRecord, ContributionStatus
from ..models.hierarchy import HierarchyNode, Promoter
from ..models.user import User


class TeamService:
    """Team contribution queries with branch-level access control."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    async def _get_promoter_by_user(db: AsyncSession, user_id: int) -> Promoter:
        """Get promoter by user_id."""
        result = await db.execute(
            select(Promoter).where(Promoter.user_id == user_id)
        )
        promoter = result.scalars().first()
        if promoter is None:
            raise NotFoundException(message="Promoter not found")
        return promoter

    @staticmethod
    async def _get_promoter_by_id(db: AsyncSession, promoter_id: int) -> Promoter:
        """Get promoter by its ID."""
        result = await db.execute(
            select(Promoter).where(Promoter.id == promoter_id)
        )
        promoter = result.scalars().first()
        if promoter is None:
            raise NotFoundException(message="Promoter not found")
        return promoter

    @staticmethod
    async def _get_node(db: AsyncSession, node_id: int) -> Optional[HierarchyNode]:
        """Get a hierarchy node by ID."""
        result = await db.execute(
            select(HierarchyNode).where(HierarchyNode.id == node_id)
        )
        return result.scalars().first()

    @staticmethod
    def _sum_points(records: list[ContributionRecord]) -> str:
        """Sum points, excluding reversed/cancelled."""
        total = Decimal("0")
        for r in records:
            if r.status in (ContributionStatus.REVERSED, ContributionStatus.CANCELLED):
                continue
            total += Decimal(r.points)
        return str(total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    # ------------------------------------------------------------------
    # Branch access verification
    # ------------------------------------------------------------------
    async def verify_branch_access(
        self,
        db: AsyncSession,
        requester_promoter: Promoter,
        target_promoter: Promoter,
    ) -> bool:
        """Check if target_promoter is in the requester's subtree.

        Walks up from target's node to see if requester's node is an ancestor.
        Returns True if target IS in requester's branch.
        """
        if requester_promoter.id == target_promoter.id:
            return True  # Viewing own team is always allowed

        target_node = await self._get_node(db, target_promoter.node_id)
        if target_node is None:
            return False

        requester_node_id = requester_promoter.node_id

        # Walk up from target
        current = target_node
        visited = set()
        while current.parent_id is not None:
            if current.parent_id in visited:
                break
            visited.add(current.parent_id)
            if current.parent_id == requester_node_id:
                return True
            parent = await self._get_node(db, current.parent_id)
            if parent is None:
                break
            current = parent

        return False

    # ------------------------------------------------------------------
    # Team summary
    # ------------------------------------------------------------------
    async def get_team_summary(
        self,
        db: AsyncSession,
        user_id: int,
        month: Optional[str] = None,
    ) -> dict:
        """Get team contribution summary for the current promoter.

        Aggregates all direct children's contributions for the given month.
        """
        promoter = await self._get_promoter_by_user(db, user_id)
        node = await self._get_node(db, promoter.node_id)
        if node is None:
            raise NotFoundException(message="Hierarchy node not found")

        # Find direct children nodes
        result = await db.execute(
            select(HierarchyNode).where(HierarchyNode.parent_id == node.id)
        )
        child_nodes = result.scalars().all()

        if not child_nodes:
            return {
                "teamMonthlyPoints": "0.00",
                "directMemberCount": 0,
                "members": [],
            }

        members = []
        team_total = Decimal("0")

        for child_node in child_nodes:
            # Find promoter for this child node
            result = await db.execute(
                select(Promoter).where(Promoter.node_id == child_node.id)
            )
            child_promoter = result.scalars().first()
            if child_promoter is None:
                continue

            # Get user info
            result = await db.execute(
                select(User).where(User.id == child_promoter.user_id)
            )
            child_user = result.scalars().first()
            child_name = child_user.name if child_user else f"Promoter {child_promoter.id}"

            # Get contributions for this child in the given month or all time
            from sqlalchemy import func
            conditions = [ContributionRecord.promoter_id == child_promoter.id]
            if month:
                conditions.append(func.strftime("%Y-%m", ContributionRecord.occurred_at) == month)

            result = await db.execute(
                select(ContributionRecord).where(*conditions)
            )
            child_records = result.scalars().all()
            child_points = self._sum_points(child_records)
            child_points_dec = Decimal(child_points)
            team_total += child_points_dec

            # Status counts
            status_counts = {}
            for r in child_records:
                s = r.status.value if hasattr(r.status, "value") else str(r.status)
                status_counts[s] = status_counts.get(s, 0) + 1

            members.append({
                "promoterId": child_promoter.id,
                "name": child_name,
                "nodeName": child_node.name,
                "monthlyPoints": child_points,
                "statusCounts": status_counts,
            })

        return {
            "teamMonthlyPoints": str(team_total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "directMemberCount": len(members),
            "members": members,
        }

    # ------------------------------------------------------------------
    # Drill-down: view a specific member's team
    # ------------------------------------------------------------------
    async def drill_down(
        self,
        db: AsyncSession,
        requester_user_id: int,
        target_promoter_id: int,
        month: Optional[str] = None,
    ) -> dict:
        """View a specific team member's own team summary.

        Verifies that the requester has branch access (target is in
        requester's subtree). Returns 403 if unauthorized.
        """
        requester = await self._get_promoter_by_user(db, requester_user_id)
        target = await self._get_promoter_by_id(db, target_promoter_id)

        # Verify branch access: target must be in requester's subtree
        has_access = await self.verify_branch_access(db, requester, target)
        if not has_access:
            raise ForbiddenException(message="Cannot access team outside your branch")

        # Now get team summary from target's perspective
        target_node = await self._get_node(db, target.node_id)
        if target_node is None:
            raise NotFoundException(message="Hierarchy node not found")

        # Find direct children of target
        result = await db.execute(
            select(HierarchyNode).where(HierarchyNode.parent_id == target_node.id)
        )
        child_nodes = result.scalars().all()

        members = []
        team_total = Decimal("0")

        for child_node in child_nodes:
            result = await db.execute(
                select(Promoter).where(Promoter.node_id == child_node.id)
            )
            child_promoter = result.scalars().first()
            if child_promoter is None:
                continue

            result = await db.execute(
                select(User).where(User.id == child_promoter.user_id)
            )
            child_user = result.scalars().first()
            child_name = child_user.name if child_user else f"Promoter {child_promoter.id}"

            from sqlalchemy import func
            conditions = [ContributionRecord.promoter_id == child_promoter.id]
            if month:
                conditions.append(func.strftime("%Y-%m", ContributionRecord.occurred_at) == month)

            result = await db.execute(
                select(ContributionRecord).where(*conditions)
            )
            child_records = result.scalars().all()
            child_points = self._sum_points(child_records)
            team_total += Decimal(child_points)

            status_counts = {}
            for r in child_records:
                s = r.status.value if hasattr(r.status, "value") else str(r.status)
                status_counts[s] = status_counts.get(s, 0) + 1

            members.append({
                "promoterId": child_promoter.id,
                "name": child_name,
                "nodeName": child_node.name,
                "monthlyPoints": child_points,
                "statusCounts": status_counts,
            })

        return {
            "teamMonthlyPoints": str(team_total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "directMemberCount": len(members),
            "members": members,
        }
