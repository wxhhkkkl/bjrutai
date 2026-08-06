"""Team service: team 消费金额 summary and drill-down with branch access control.

业绩贡献 = 消费金额：成员按账单（Bill.paid_amount_cent）实时统计，单位为分。
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.exceptions import ForbiddenException, NotFoundException
from ..models.distributor import Distributor
from ..models.organization import Organization
from ..models.user import User
from .consumption_service import consumption_by_distributor


class TeamService:
    """Team consumption queries with branch-level access control."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    async def _get_promoter_by_user(db: AsyncSession, user_id: int) -> Distributor:
        result = await db.execute(select(Distributor).where(Distributor.user_id == user_id))
        promoter = result.scalars().first()
        if promoter is None:
            raise NotFoundException(message="Distributor not found")
        return promoter

    @staticmethod
    async def _get_promoter_by_id(db: AsyncSession, distributor_id: int) -> Distributor:
        result = await db.execute(select(Distributor).where(Distributor.id == distributor_id))
        promoter = result.scalars().first()
        if promoter is None:
            raise NotFoundException(message="Distributor not found")
        return promoter

    @staticmethod
    async def _get_node(db: AsyncSession, node_id: int) -> Optional[Organization]:
        result = await db.execute(select(Organization).where(Organization.id == node_id))
        return result.scalars().first()

    # ------------------------------------------------------------------
    # Branch access verification
    # ------------------------------------------------------------------
    async def verify_branch_access(
        self,
        db: AsyncSession,
        requester_promoter: Distributor,
        target_promoter: Distributor,
    ) -> bool:
        if requester_promoter.id == target_promoter.id:
            return True

        target_node = await self._get_node(db, target_promoter.org_id)
        if target_node is None:
            return False

        requester_node_id = requester_promoter.org_id
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
        promoter = await self._get_promoter_by_user(db, user_id)
        node = await self._get_node(db, promoter.org_id)
        if node is None:
            raise NotFoundException(message="Hierarchy node not found")

        child_nodes = (await db.execute(
            select(Organization).where(Organization.parent_id == node.id)
        )).scalars().all()
        if not child_nodes:
            return {"teamMonthlyAmountCent": 0, "directMemberCount": 0, "members": []}

        child_promoters = []
        for child_node in child_nodes:
            cp = (await db.execute(
                select(Distributor).where(Distributor.org_id == child_node.id)
            )).scalars().first()
            if cp is not None:
                child_promoters.append((child_node, cp))

        consumption = await consumption_by_distributor(db, [cp.id for _, cp in child_promoters], month)
        members = []
        team_total = 0
        for child_node, cp in child_promoters:
            user = (await db.execute(select(User).where(User.id == cp.user_id))).scalars().first()
            child_name = user.name if user else f"Distributor {cp.id}"
            cents = consumption.get(cp.id, 0)
            team_total += cents
            members.append({
                "promoterId": cp.id,
                "name": child_name,
                "nodeName": child_node.name,
                "monthlyAmountCent": cents,
            })

        return {
            "teamMonthlyAmountCent": team_total,
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
        requester = await self._get_promoter_by_user(db, requester_user_id)
        target = await self._get_promoter_by_id(db, target_promoter_id)

        has_access = await self.verify_branch_access(db, requester, target)
        if not has_access:
            raise ForbiddenException(message="Cannot access team outside your branch")

        target_node = await self._get_node(db, target.org_id)
        if target_node is None:
            raise NotFoundException(message="Hierarchy node not found")

        child_nodes = (await db.execute(
            select(Organization).where(Organization.parent_id == target_node.id)
        )).scalars().all()
        if not child_nodes:
            return {"teamMonthlyAmountCent": 0, "directMemberCount": 0, "members": []}

        child_promoters = []
        for child_node in child_nodes:
            cp = (await db.execute(
                select(Distributor).where(Distributor.org_id == child_node.id)
            )).scalars().first()
            if cp is not None:
                child_promoters.append((child_node, cp))

        consumption = await consumption_by_distributor(db, [cp.id for _, cp in child_promoters], month)
        members = []
        team_total = 0
        for child_node, cp in child_promoters:
            user = (await db.execute(select(User).where(User.id == cp.user_id))).scalars().first()
            child_name = user.name if user else f"Distributor {cp.id}"
            cents = consumption.get(cp.id, 0)
            team_total += cents
            members.append({
                "promoterId": cp.id,
                "name": child_name,
                "nodeName": child_node.name,
                "monthlyAmountCent": cents,
            })

        return {
            "teamMonthlyAmountCent": team_total,
            "directMemberCount": len(members),
            "members": members,
        }
