"""Integration test: full hierarchy management flow.

Tests the complete lifecycle using a real SQLite database:
  create root -> build tree -> migrate branch -> verify snapshot -> detect cycle
"""

import pytest
from httpx import AsyncClient

from src.core.security import create_access_token
from src.models.hierarchy import HierarchyNode, NodeType
from tests.conftest import auth_header, assert_response_envelope


def _admin_token() -> str:
    return create_access_token(data={"sub": "1", "user_type": "admin"})


async def _create_node(
    client: AsyncClient,
    parent_id: int,
    name: str,
    node_type: str,
) -> dict:
    resp = await client.post(
        "/api/v1/admin/hierarchy/nodes",
        json={"parentId": parent_id, "name": name, "nodeType": node_type},
        headers=auth_header(_admin_token()),
    )
    assert resp.status_code == 200, f"Failed to create node '{name}': {resp.text}"
    body = resp.json()
    return body["data"]


async def _seed_root(client: AsyncClient, db_session) -> int:
    """Seed a root node directly via DB."""
    root = HierarchyNode(
        parent_id=None,
        level=1,
        node_type=NodeType.HEADQUARTERS,
        name="北京总部",
    )
    db_session.add(root)
    await db_session.flush()
    await db_session.refresh(root)
    return root.id


class TestHierarchyFullFlow:
    """End-to-end hierarchy management lifecycle."""

    async def test_full_lifecycle(self, client: AsyncClient, db_session):
        """
        Complete lifecycle:
        1. Seed root node
        2. Build two-level tree under root
        3. Verify tree structure
        4. Migrate a branch to another parent
        5. Verify tree after migration
        6. Detect cycle on invalid migration
        7. Delete a leaf node
        """
        headers = auth_header(_admin_token())

        # ── Phase 1: Seed root node ─────────────────────────────────
        root_id = await _seed_root(client, db_session)

        # ── Phase 2: Build tree ─────────────────────────────────────
        region1 = await _create_node(client, root_id, "华东大区", "region")
        region2 = await _create_node(client, root_id, "华南大区", "region")
        assert region1["nodeId"] is not None
        assert region2["nodeId"] is not None
        assert region1["level"] == 2

        branch1 = await _create_node(client, int(region1["nodeId"]), "上海分部", "branch")
        branch2 = await _create_node(client, int(region1["nodeId"]), "杭州分部", "branch")
        assert branch1["level"] == 3

        # ── Phase 3: Verify tree structure ──────────────────────────
        tree_resp = await client.get("/api/v1/admin/hierarchy", headers=headers)
        assert tree_resp.status_code == 200
        tree_body = tree_resp.json()
        assert_response_envelope(tree_body)
        assert tree_body["data"]["tree"] is not None
        assert tree_body["data"]["totalNodes"] == 5  # root + 2 regions + 2 branches
        assert tree_body["data"]["maxDepth"] == 3

        # Verify children of root
        root_children = tree_body["data"]["tree"]["children"]
        assert len(root_children) == 2
        region_names = [c["name"] for c in root_children]
        assert "华东大区" in region_names
        assert "华南大区" in region_names

        # Verify华东大区 has 2 children
        region1_tree = next(c for c in root_children if c["name"] == "华东大区")
        assert len(region1_tree["children"]) == 2

        # ── Phase 4: Migrate 上海分部 to 华南大区 ───────────────────
        migrate_resp = await client.post(
            f"/api/v1/admin/hierarchy/nodes/{branch1['nodeId']}/migrate",
            json={"targetParentId": int(region2["nodeId"])},
            headers=headers,
        )
        assert migrate_resp.status_code == 200
        migrate_body = migrate_resp.json()
        assert_response_envelope(migrate_body)
        assert migrate_body["code"] == 0
        assert migrate_body["data"]["migratedNodeId"] == branch1["nodeId"]
        assert migrate_body["data"]["toParentId"] == region2["nodeId"]

        # ── Phase 5: Verify tree after migration ────────────────────
        tree_resp2 = await client.get("/api/v1/admin/hierarchy", headers=headers)
        assert tree_resp2.status_code == 200
        tree_body2 = tree_resp2.json()

        root_children2 = tree_body2["data"]["tree"]["children"]
        # 华东大区 now has 1 child (杭州分部)
        region1_after = next(c for c in root_children2 if c["name"] == "华东大区")
        assert len(region1_after["children"]) == 1
        # 华南大区 now has 1 child (上海分部)
        region2_after = next(c for c in root_children2 if c["name"] == "华南大区")
        assert len(region2_after["children"]) == 1
        assert region2_after["children"][0]["name"] == "上海分部"

        # ── Phase 6: Cycle detection - try to migrate 华东大区 to 杭州分部 ──
        cycle_resp = await client.post(
            f"/api/v1/admin/hierarchy/nodes/{region1['nodeId']}/migrate",
            json={"targetParentId": int(branch2["nodeId"])},
            headers=headers,
        )
        assert cycle_resp.status_code == 400
        cycle_body = cycle_resp.json()
        assert cycle_body["code"] != 0

        # ── Phase 7: Delete a leaf node ─────────────────────────────
        # 杭州分部 is now a leaf (no children)
        delete_resp = await client.delete(
            f"/api/v1/admin/hierarchy/nodes/{branch2['nodeId']}",
            headers=headers,
        )
        assert delete_resp.status_code == 200
        delete_body = delete_resp.json()
        assert delete_body["code"] == 0

        # ── Phase 8: Verify tree after deletion ─────────────────────
        tree_resp3 = await client.get("/api/v1/admin/hierarchy", headers=headers)
        tree_body3 = tree_resp3.json()
        assert tree_body3["data"]["totalNodes"] == 4  # root + 2 regions + 1 branch

        print("Full lifecycle completed: create -> build -> migrate -> cycle detect -> delete")

    async def test_delete_non_leaf_rejected(self, client: AsyncClient, db_session):
        """Cannot delete a node that has children."""
        root_id = await _seed_root(client, db_session)
        region = await _create_node(client, root_id, "华北区", "region")
        branch = await _create_node(client, int(region["nodeId"]), "天津分部", "branch")

        # Try to delete region which has a child
        resp = await client.delete(
            f"/api/v1/admin/hierarchy/nodes/{region['nodeId']}",
            headers=auth_header(_admin_token()),
        )
        assert resp.status_code == 400

    async def test_migration_snapshot_created(self, client: AsyncClient, db_session):
        """Verify that migration creates a hierarchy snapshot record."""
        root_id = await _seed_root(client, db_session)
        region = await _create_node(client, root_id, "东北大区", "region")
        target = await _create_node(client, root_id, "西南大区", "region")
        branch = await _create_node(client, int(region["nodeId"]), "沈阳分部", "branch")

        # Migrate
        resp = await client.post(
            f"/api/v1/admin/hierarchy/nodes/{branch['nodeId']}/migrate",
            json={"targetParentId": int(target["nodeId"])},
            headers=auth_header(_admin_token()),
        )
        assert resp.status_code == 200

        # Verify snapshot exists in DB
        from sqlalchemy import select, text
        result = await db_session.execute(text("SELECT * FROM hierarchy_snapshots"))
        snapshots = result.fetchall()
        assert len(snapshots) >= 1
