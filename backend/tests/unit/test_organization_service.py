"""Unit tests for organization_service (US1)."""

import pytest

from src.core.exceptions import BadRequestException, ConflictException, NotFoundException
from src.models.organization import Organization
from src.models.org_history import OrgHistory
from src.schemas.organization import OrgCreate, OrgMigrateRequest, OrgUpdate
from src.services import organization_service


@pytest.mark.asyncio
async def test_create_root_org(db_session):
    org = await organization_service.create_org(
        db_session, OrgCreate(name="总部", orgType="headquarters")
    )
    assert org.id is not None
    assert org.level == 1
    assert org.parent_id is None


@pytest.mark.asyncio
async def test_create_child_org_computes_level(db_session):
    root = await organization_service.create_org(
        db_session, OrgCreate(name="总部", orgType="headquarters")
    )
    child = await organization_service.create_org(
        db_session, OrgCreate(name="华北区", orgType="region", parentId=root.id)
    )
    assert child.level == 2


@pytest.mark.asyncio
async def test_create_dup_name_under_parent_conflicts(db_session):
    root = await organization_service.create_org(
        db_session, OrgCreate(name="总部", orgType="headquarters")
    )
    await organization_service.create_org(
        db_session, OrgCreate(name="华北区", orgType="region", parentId=root.id)
    )
    with pytest.raises(ConflictException):
        await organization_service.create_org(
            db_session, OrgCreate(name="华北区", orgType="region", parentId=root.id)
        )


@pytest.mark.asyncio
async def test_create_missing_parent_raises_not_found(db_session):
    with pytest.raises(NotFoundException):
        await organization_service.create_org(
            db_session, OrgCreate(name="孤儿", orgType="region", parentId=99999)
        )


@pytest.mark.asyncio
async def test_update_org(db_session):
    org = await organization_service.create_org(
        db_session, OrgCreate(name="总部", orgType="headquarters")
    )
    updated = await organization_service.update_org(
        db_session, org.id, OrgUpdate(name="北京总部", status="disabled")
    )
    assert updated.name == "北京总部"
    assert updated.status.value == "disabled"


@pytest.mark.asyncio
async def test_delete_org_with_children_rejected(db_session):
    root = await organization_service.create_org(
        db_session, OrgCreate(name="总部", orgType="headquarters")
    )
    await organization_service.create_org(
        db_session, OrgCreate(name="华北区", orgType="region", parentId=root.id)
    )
    with pytest.raises(BadRequestException):
        await organization_service.delete_org(db_session, root.id)


@pytest.mark.asyncio
async def test_delete_leaf_org_succeeds(db_session):
    root = await organization_service.create_org(
        db_session, OrgCreate(name="总部", orgType="headquarters")
    )
    child = await organization_service.create_org(
        db_session, OrgCreate(name="华北区", orgType="region", parentId=root.id)
    )
    await organization_service.delete_org(db_session, child.id)
    result = await db_session.get(Organization, child.id)
    assert result is None


@pytest.mark.asyncio
async def test_migrate_subtree_updates_levels(db_session):
    root = await organization_service.create_org(
        db_session, OrgCreate(name="总部", orgType="headquarters")
    )
    a = await organization_service.create_org(
        db_session, OrgCreate(name="A区", orgType="region", parentId=root.id)
    )
    b = await organization_service.create_org(
        db_session, OrgCreate(name="B区", orgType="region", parentId=root.id)
    )
    a1 = await organization_service.create_org(
        db_session, OrgCreate(name="A1城市", orgType="city", parentId=a.id)
    )

    await organization_service.migrate_branch(
        db_session, a.id, OrgMigrateRequest(newParentId=b.id)
    )

    moved_a = await db_session.get(Organization, a.id)
    moved_a1 = await db_session.get(Organization, a1.id)
    assert moved_a.parent_id == b.id
    assert moved_a.level == 3          # root(1) -> B区(2) -> A区(3)
    assert moved_a1.level == 4


@pytest.mark.asyncio
async def test_migrate_into_own_descendant_rejected(db_session):
    root = await organization_service.create_org(
        db_session, OrgCreate(name="总部", orgType="headquarters")
    )
    a = await organization_service.create_org(
        db_session, OrgCreate(name="A区", orgType="region", parentId=root.id)
    )
    a1 = await organization_service.create_org(
        db_session, OrgCreate(name="A1城市", orgType="city", parentId=a.id)
    )
    with pytest.raises(BadRequestException):
        await organization_service.migrate_branch(
            db_session, a.id, OrgMigrateRequest(newParentId=a1.id)
        )


@pytest.mark.asyncio
async def test_migrate_to_self_rejected(db_session):
    root = await organization_service.create_org(
        db_session, OrgCreate(name="总部", orgType="headquarters")
    )
    with pytest.raises(BadRequestException):
        await organization_service.migrate_branch(
            db_session, root.id, OrgMigrateRequest(newParentId=root.id)
        )


@pytest.mark.asyncio
async def test_operation_history_recorded(db_session):
    org = await organization_service.create_org(
        db_session, OrgCreate(name="总部", orgType="headquarters"), operator_id=1
    )
    history = await organization_service.get_history(db_session, org.id)
    assert len(history) == 1
    assert history[0]["action"] == "created"
    assert history[0]["operatorId"] == "1"


@pytest.mark.asyncio
async def test_disabled_org_blocks_business(db_session):
    org = await organization_service.create_org(
        db_session, OrgCreate(name="总部", orgType="headquarters")
    )
    await organization_service.update_org(
        db_session, org.id, OrgUpdate(status="disabled")
    )
    reasons = await organization_service.get_org_business_blocked_reasons(db_session, org.id)
    assert "org_disabled" in reasons


@pytest.mark.asyncio
async def test_org_without_qualification_blocks_business(db_session):
    org = await organization_service.create_org(
        db_session, OrgCreate(name="总部", orgType="headquarters")
    )
    reasons = await organization_service.get_org_business_blocked_reasons(db_session, org.id)
    assert "qualification_missing" in reasons


@pytest.mark.asyncio
async def test_tree_retrieval(db_session):
    root = await organization_service.create_org(
        db_session, OrgCreate(name="总部", orgType="headquarters")
    )
    await organization_service.create_org(
        db_session, OrgCreate(name="华北区", orgType="region", parentId=root.id)
    )
    tree = await organization_service.get_tree(db_session)
    assert tree["totalNodes"] == 2
    assert tree["tree"][0]["orgId"] == str(root.id)
    assert len(tree["tree"][0]["children"]) == 1


@pytest.mark.asyncio
async def test_tree_retrieval_returns_all_roots(db_session):
    """Multiple root orgs must all appear in the tree (regression: only roots[0] was shown)."""
    a = await organization_service.create_org(db_session, OrgCreate(name="根A", orgType=None))
    b = await organization_service.create_org(db_session, OrgCreate(name="根B", orgType=None))
    await organization_service.create_org(
        db_session, OrgCreate(name="根A子", orgType=None, parentId=a.id)
    )
    tree = await organization_service.get_tree(db_session)
    root_ids = {t["orgId"] for t in tree["tree"]}
    assert root_ids == {str(a.id), str(b.id)}
    assert tree["totalNodes"] == 3


# ── get_default_org (012-register-default-dept) ──────────────────────


@pytest.mark.asyncio
async def test_get_default_org_returns_min_sort_root(db_session):
    """get_default_org returns the root node with the smallest sort_order."""
    a = await organization_service.create_org(
        db_session, OrgCreate(name="第二组织", orgType=None)
    )
    b = await organization_service.create_org(
        db_session, OrgCreate(name="第一组织", orgType=None)
    )
    # Manually set sort_order so a < b (lower sort = first)
    from sqlalchemy import update
    from src.models.organization import Organization as OrgModel
    await db_session.execute(update(OrgModel).where(OrgModel.id == a.id).values(sort_order=2))
    await db_session.execute(update(OrgModel).where(OrgModel.id == b.id).values(sort_order=1))
    await db_session.flush()

    default = await organization_service.get_default_org(db_session)
    assert default is not None
    assert default.id == b.id  # b has sort_order=1 (smallest)
    assert default.name == "第一组织"


@pytest.mark.asyncio
async def test_get_default_org_returns_none_when_no_roots(db_session):
    """get_default_org returns None when there are no root orgs."""
    default = await organization_service.get_default_org(db_session)
    assert default is None
