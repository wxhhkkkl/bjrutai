"""US6 data migration: hierarchy/promoter -> organization/distributor.

The transformation logic lives here so it is testable against any backend
(SQLite test DB included).  The Alembic revision ``004`` invokes
``run_org_data_migration`` then performs the MySQL-specific DDL (FK switch,
table deprecation) that cannot run in SQLite tests.

Historical data is 100% preserved (SC-009): org/distributor rows keep the
legacy ids, so downstream FK values stay numerically aligned.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.distributor import Distributor, DistributorStatus, OrgRole
from ..models.hierarchy import HierarchyNode, Promoter
from ..models.organization import Organization, OrgStatus
from ..models.org_qualification import OrgQualStatus, OrganizationQualification
from ..models.qualification import Qualification, QualStatus


def _map_qual_status(status: QualStatus) -> OrgQualStatus:
    if status == QualStatus.APPROVED:
        return OrgQualStatus.APPROVED
    if status == QualStatus.REJECTED:
        return OrgQualStatus.REJECTED
    return OrgQualStatus.REVIEWING


async def run_org_data_migration(db: AsyncSession) -> dict:
    """Migrate hierarchy_nodes/promoters/qualifications into the new model.

    Returns a summary dict of migrated counts. Assumes the target tables are
    empty (one-time migration).
    """
    summary = {"organizations": 0, "distributors": 0, "org_qualifications": 0}

    # ── 1. organizations from hierarchy_nodes (ids preserved) ──────────
    nodes = (await db.execute(select(HierarchyNode))).scalars().all()
    for node in nodes:
        org_type = node.node_type.value if hasattr(node.node_type, "value") else str(node.node_type)
        db.add(Organization(
            id=node.id,
            parent_id=node.parent_id,
            name=node.name,
            org_type=org_type,
            level=node.level,
            sort_order=0,
            status=OrgStatus.ACTIVE,
        ))
        summary["organizations"] += 1

    # ── 2. distributors from promoters (ids preserved, org_id = node_id) ─
    promoters = (await db.execute(select(Promoter))).scalars().all()
    for p in promoters:
        db.add(Distributor(
            id=p.id,
            user_id=p.user_id,
            org_id=p.node_id,
            org_role=OrgRole.MEMBER,
            status=DistributorStatus.ACTIVE,
        ))
        summary["distributors"] += 1

    await db.flush()

    # ── 3. org_qualifications from latest promoter qualification per org ─
    # Build promoter -> org mapping (distributor.org_id was node_id == org id)
    promo_org: dict[int, int] = {p.id: p.node_id for p in promoters}
    if promo_org:
        quals = (await db.execute(select(Qualification))).scalars().all()
        # Latest per promoter
        latest_by_promoter: dict[int, Qualification] = {}
        for q in quals:
            prev = latest_by_promoter.get(q.promoter_id)
            if prev is None or (q.created_at or datetime.min) > (prev.created_at or datetime.min):
                latest_by_promoter[q.promoter_id] = q

        # Latest per org across its promoters
        latest_by_org: dict[int, Qualification] = {}
        for pid, q in latest_by_promoter.items():
            org_id = promo_org.get(pid)
            if org_id is None:
                continue
            prev = latest_by_org.get(org_id)
            if prev is None or (q.created_at or datetime.min) > (prev.created_at or datetime.min):
                latest_by_org[org_id] = q

        for org_id, q in latest_by_org.items():
            db.add(OrganizationQualification(
                org_id=org_id,
                legal_entity_name=q.legal_entity or "迁移资质",
                qualification_types=[q.qualification_type.value] if hasattr(q.qualification_type, "value") else [str(q.qualification_type)],
                credit_code=q.credit_code_masked or q.credit_code_encrypted or "migrated",
                file_urls=[{"url": q.file_id, "type": q.file_type, "size": q.file_size}] if q.file_id else [],
                valid_from=None,
                valid_until=q.expires_at or datetime(2099, 12, 31, 23, 59, 59),
                status=_map_qual_status(q.status),
                review_comment=q.rejected_reason,
            ))
            summary["org_qualifications"] += 1

    await db.flush()
    return summary
