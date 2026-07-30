"""Contract tests for hierarchy admin endpoints.

Tests ensure the hierarchy endpoints conform to the unified response format
{code, message, data, requestId, serverTime} and behave correctly under all
documented scenarios.

Uses mocked database for isolation and reliability.
TDD: These tests are written FIRST and are expected to FAIL until the
implementation is complete.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.core.security import create_access_token
from src.main import app
from tests.conftest import assert_response_envelope, auth_header, mock_scalar_result


# ---------------------------------------------------------------------------
# Mock builder helpers
# ---------------------------------------------------------------------------
def _mock_execute_result(*, scalar_first=None, scalar_all=None, fetchall_values=None):
    """Build a mock SQLAlchemy Result that supports both .scalars() and .fetchall()."""
    result = MagicMock()

    if scalar_first is not None or scalar_all is not None:
        scalars_mock = MagicMock()
        if scalar_first is not None:
            scalars_mock.first = MagicMock(return_value=scalar_first)
        if scalar_all is not None:
            scalars_mock.all = MagicMock(return_value=scalar_all)
        result.scalars = MagicMock(return_value=scalars_mock)

    if fetchall_values is not None:
        result.fetchall = MagicMock(return_value=fetchall_values)

    return result


def make_mock_node(
    node_id: int = 1,
    parent_id: int | None = None,
    level: int = 1,
    node_type: str = "headquarters",
    name: str = "北京总部",
    children: list | None = None,
) -> MagicMock:
    """Build a mock HierarchyNode for unit/contract testing."""
    n = MagicMock()
    n.id = node_id
    n.parent_id = parent_id
    n.level = level
    n.node_type = type("NodeType", (), {"value": node_type})()
    n.name = name
    n.children = children or []
    n.created_at = None
    n.updated_at = None
    return n


# ---------------------------------------------------------------------------
# Fixture: AsyncClient with mocked DB
# ---------------------------------------------------------------------------
@pytest.fixture
async def mock_client():
    """Return an AsyncClient with get_db overridden to yield a mock session."""
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.refresh = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.delete = AsyncMock()
    mock_session.flush = AsyncMock()
    mock_session.execute = AsyncMock()

    from src.core.database import get_db

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        ac._mock_db = mock_session
        yield ac

    app.dependency_overrides.clear()


def _admin_token() -> str:
    return create_access_token(data={"sub": "1", "user_type": "admin"})


# ============================================================================
# GET /api/v1/admin/hierarchy - Tree retrieval
# ============================================================================
class TestGetHierarchyTree:
    """GET /api/v1/admin/hierarchy"""

    async def test_returns_tree_structure(self, mock_client):
        """Admin gets full tree with nested children."""
        root = make_mock_node(node_id=1, level=1, node_type="headquarters", name="总部")
        child = make_mock_node(node_id=2, parent_id=1, level=2, node_type="region", name="华东大区")
        root.children = [child]

        mock_client._mock_db.execute = AsyncMock(
            return_value=mock_scalar_result(all_values=[root])
        )

        response = await mock_client.get(
            "/api/v1/admin/hierarchy",
            headers=auth_header(_admin_token()),
        )

        assert response.status_code == 200
        body = response.json()
        assert_response_envelope(body)
        assert body["code"] == 0
        assert body["data"]["tree"] is not None
        assert body["data"]["tree"]["nodeId"] is not None

    async def test_requires_admin_auth(self, mock_client):
        """Calling without admin token returns 403."""
        token = create_access_token(data={"sub": "1", "user_type": "promoter"})
        response = await mock_client.get(
            "/api/v1/admin/hierarchy",
            headers=auth_header(token),
        )
        assert response.status_code == 403

    async def test_no_auth_returns_401(self, mock_client):
        """Calling without auth returns 401."""
        response = await mock_client.get("/api/v1/admin/hierarchy")
        assert response.status_code == 401

    async def test_returns_empty_tree_when_no_nodes(self, mock_client):
        """Empty database returns null tree."""
        mock_client._mock_db.execute = AsyncMock(
            return_value=mock_scalar_result(all_values=[])
        )

        response = await mock_client.get(
            "/api/v1/admin/hierarchy",
            headers=auth_header(_admin_token()),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["code"] == 0
        assert body["data"]["tree"] is None
        assert body["data"]["totalNodes"] == 0
        assert body["data"]["maxDepth"] == 0

    async def test_returns_node_count(self, mock_client):
        """Response includes totalNodes and maxDepth."""
        root = make_mock_node(node_id=1, level=1, name="总部")
        c1 = make_mock_node(node_id=2, parent_id=1, level=2, name="大区1")
        c2 = make_mock_node(node_id=3, parent_id=2, level=3, name="分部1")

        # The service loads ALL nodes flat and builds tree in Python
        mock_client._mock_db.execute = AsyncMock(
            return_value=mock_scalar_result(all_values=[root, c1, c2])
        )

        response = await mock_client.get(
            "/api/v1/admin/hierarchy",
            headers=auth_header(_admin_token()),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["code"] == 0
        assert body["data"]["totalNodes"] == 3
        assert body["data"]["maxDepth"] == 3


# ============================================================================
# GET /api/v1/admin/hierarchy/nodes/{id} - Subtree retrieval
# ============================================================================
class TestGetSubtree:
    """GET /api/v1/admin/hierarchy/nodes/{id}"""

    async def test_returns_subtree(self, mock_client):
        """Admin gets subtree from a given node."""
        node = make_mock_node(node_id=5, parent_id=1, level=2, node_type="region", name="华东大区")
        child = make_mock_node(node_id=6, parent_id=5, level=3, node_type="branch", name="上海分部")

        mock_client._mock_db.execute = AsyncMock()
        mock_client._mock_db.execute.side_effect = [
            mock_scalar_result(first_value=node),     # _get_node_or_404 check
            mock_scalar_result(all_values=[node, child]),  # load all nodes
        ]

        response = await mock_client.get(
            "/api/v1/admin/hierarchy/nodes/5",
            headers=auth_header(_admin_token()),
        )

        assert response.status_code == 200
        body = response.json()
        assert_response_envelope(body)
        assert body["code"] == 0
        assert body["data"]["nodeId"] is not None

    async def test_node_not_found_returns_404(self, mock_client):
        """Non-existent node returns 404."""
        mock_client._mock_db.execute = AsyncMock(
            return_value=mock_scalar_result(first_value=None)
        )

        response = await mock_client.get(
            "/api/v1/admin/hierarchy/nodes/999",
            headers=auth_header(_admin_token()),
        )

        assert response.status_code == 404


# ============================================================================
# POST /api/v1/admin/hierarchy/nodes - Create node
# ============================================================================
class TestCreateNode:
    """POST /api/v1/admin/hierarchy/nodes"""

    async def test_create_child_node(self, mock_client):
        """Admin creates a child node under an existing parent."""
        parent = make_mock_node(node_id=1, level=1, name="总部")

        # First call: find parent, second: check duplicate, third: create node
        mock_client._mock_db.execute = AsyncMock()
        mock_client._mock_db.execute.side_effect = [
            mock_scalar_result(first_value=parent),  # find parent
            mock_scalar_result(first_value=None),  # duplicate check
        ]

        response = await mock_client.post(
            "/api/v1/admin/hierarchy/nodes",
            json={"parentId": 1, "name": "华东大区", "nodeType": "region"},
            headers=auth_header(_admin_token()),
        )

        assert response.status_code == 200
        body = response.json()
        assert_response_envelope(body)
        assert body["code"] == 0
        assert body["data"]["nodeId"] is not None
        assert body["data"]["name"] == "华东大区"
        assert body["data"]["nodeType"] == "region"

    async def test_invalid_parent_returns_404(self, mock_client):
        """Creating under non-existent parent returns 404."""
        mock_client._mock_db.execute = AsyncMock(
            return_value=mock_scalar_result(first_value=None)
        )

        response = await mock_client.post(
            "/api/v1/admin/hierarchy/nodes",
            json={"parentId": 999, "name": "幽灵节点", "nodeType": "region"},
            headers=auth_header(_admin_token()),
        )

        assert response.status_code == 404

    async def test_duplicate_name_under_same_parent(self, mock_client):
        """Duplicate name under same parent returns 409."""
        parent = make_mock_node(node_id=1, level=1, name="总部")
        existing = make_mock_node(node_id=2, parent_id=1, level=2, name="华东大区")

        mock_client._mock_db.execute = AsyncMock()
        mock_client._mock_db.execute.side_effect = [
            mock_scalar_result(first_value=parent),  # find parent
            mock_scalar_result(first_value=existing),  # duplicate check - found
        ]

        response = await mock_client.post(
            "/api/v1/admin/hierarchy/nodes",
            json={"parentId": 1, "name": "华东大区", "nodeType": "region"},
            headers=auth_header(_admin_token()),
        )

        assert response.status_code == 409

    async def test_requires_admin_auth(self, mock_client):
        """Non-admin cannot create nodes."""
        token = create_access_token(data={"sub": "1", "user_type": "promoter"})
        response = await mock_client.post(
            "/api/v1/admin/hierarchy/nodes",
            json={"parentId": 1, "name": "test", "nodeType": "region"},
            headers=auth_header(token),
        )
        assert response.status_code == 403


# ============================================================================
# PUT /api/v1/admin/hierarchy/nodes/{id} - Update node
# ============================================================================
class TestUpdateNode:
    """PUT /api/v1/admin/hierarchy/nodes/{id}"""

    async def test_update_node_name(self, mock_client):
        """Admin updates a node's name."""
        node = make_mock_node(node_id=2, parent_id=1, level=2, node_type="region", name="华东大区")

        mock_client._mock_db.execute = AsyncMock()
        mock_client._mock_db.execute.side_effect = [
            mock_scalar_result(first_value=node),   # find node to update
            mock_scalar_result(first_value=None),   # duplicate name check - not found
        ]

        response = await mock_client.put(
            "/api/v1/admin/hierarchy/nodes/2",
            json={"name": "华东大区(已更名)"},
            headers=auth_header(_admin_token()),
        )

        assert response.status_code == 200
        body = response.json()
        assert_response_envelope(body)
        assert body["code"] == 0
        assert body["data"]["name"] == "华东大区(已更名)"

    async def test_update_node_type(self, mock_client):
        """Admin updates a node's type."""
        node = make_mock_node(node_id=2, parent_id=1, level=2, node_type="region", name="华东大区")

        mock_client._mock_db.execute = AsyncMock(
            return_value=mock_scalar_result(first_value=node)
        )

        response = await mock_client.put(
            "/api/v1/admin/hierarchy/nodes/2",
            json={"nodeType": "branch"},
            headers=auth_header(_admin_token()),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["data"]["nodeType"] == "branch"

    async def test_node_not_found_returns_404(self, mock_client):
        """Updating non-existent node returns 404."""
        mock_client._mock_db.execute = AsyncMock(
            return_value=mock_scalar_result(first_value=None)
        )

        response = await mock_client.put(
            "/api/v1/admin/hierarchy/nodes/999",
            json={"name": "nonexistent"},
            headers=auth_header(_admin_token()),
        )

        assert response.status_code == 404


# ============================================================================
# DELETE /api/v1/admin/hierarchy/nodes/{id} - Delete node
# ============================================================================
class TestDeleteNode:
    """DELETE /api/v1/admin/hierarchy/nodes/{id}"""

    async def test_delete_leaf_node(self, mock_client):
        """Admin deletes a leaf node (no children)."""
        node = make_mock_node(node_id=5, parent_id=2, level=3, name="终端节点", children=[])

        mock_client._mock_db.execute = AsyncMock()
        mock_client._mock_db.execute.side_effect = [
            mock_scalar_result(first_value=node),   # find node (with children loaded)
            mock_scalar_result(all_values=[]),       # check for children - none found
        ]

        response = await mock_client.delete(
            "/api/v1/admin/hierarchy/nodes/5",
            headers=auth_header(_admin_token()),
        )

        assert response.status_code == 200
        body = response.json()
        assert_response_envelope(body)
        assert body["code"] == 0

    async def test_reject_non_leaf_deletion(self, mock_client):
        """Cannot delete a node with children."""
        child = make_mock_node(node_id=6, level=3, name="child")
        node = make_mock_node(node_id=2, parent_id=1, level=2, name="华东大区", children=[child])

        mock_client._mock_db.execute = AsyncMock()
        mock_client._mock_db.execute.side_effect = [
            mock_scalar_result(first_value=node),   # find node (with children loaded)
            mock_scalar_result(all_values=[child]),  # check for children - found child
        ]

        response = await mock_client.delete(
            "/api/v1/admin/hierarchy/nodes/2",
            headers=auth_header(_admin_token()),
        )

        assert response.status_code == 400

    async def test_node_not_found_returns_404(self, mock_client):
        """Deleting non-existent node returns 404."""
        mock_client._mock_db.execute = AsyncMock(
            return_value=mock_scalar_result(first_value=None)
        )

        response = await mock_client.delete(
            "/api/v1/admin/hierarchy/nodes/999",
            headers=auth_header(_admin_token()),
        )

        assert response.status_code == 404


# ============================================================================
# POST /api/v1/admin/hierarchy/nodes/{id}/migrate - Migrate branch
# ============================================================================
class TestMigrateBranch:
    """POST /api/v1/admin/hierarchy/nodes/{id}/migrate"""

    async def test_migrate_success(self, mock_client):
        """Admin migrates a branch to a new parent."""
        node = make_mock_node(node_id=5, parent_id=2, level=3, name="上海分部")
        target = make_mock_node(node_id=3, parent_id=1, level=2, name="华南大区")
        old_parent = make_mock_node(node_id=2, parent_id=1, level=2, name="华东大区")

        mock_client._mock_db.execute = AsyncMock()
        mock_client._mock_db.execute.side_effect = [
            _mock_execute_result(scalar_first=node),          # find source node
            _mock_execute_result(scalar_first=target),         # find target parent
            _mock_execute_result(fetchall_values=[]),          # cycle check: children of source (empty)
            _mock_execute_result(scalar_first=old_parent),     # lookup from_parent for snapshot
            _mock_execute_result(scalar_first=None),           # snapshot insert
            _mock_execute_result(fetchall_values=[]),          # _update_descendant_levels: no children
        ]

        response = await mock_client.post(
            "/api/v1/admin/hierarchy/nodes/5/migrate",
            json={"targetParentId": 3},
            headers=auth_header(_admin_token()),
        )

        assert response.status_code == 200
        body = response.json()
        assert_response_envelope(body)
        assert body["code"] == 0
        assert body["data"]["migratedNodeId"] is not None
        assert body["data"]["toParentId"] is not None

    async def test_cycle_detection_rejection(self, mock_client):
        """Migrating a node to its own descendant is blocked."""
        node = make_mock_node(node_id=2, parent_id=1, level=2, name="华东大区")
        descendant = make_mock_node(node_id=5, parent_id=2, level=3, name="上海分部")

        mock_client._mock_db.execute = AsyncMock()
        mock_client._mock_db.execute.side_effect = [
            _mock_execute_result(scalar_first=node),        # find source node
            _mock_execute_result(scalar_first=descendant),   # find target parent
            _mock_execute_result(fetchall_values=[(5,)]),    # cycle check: children of node 2
            _mock_execute_result(fetchall_values=[]),        # cycle check: children of node 5 (leaf)
        ]

        response = await mock_client.post(
            "/api/v1/admin/hierarchy/nodes/2/migrate",
            json={"targetParentId": 5},
            headers=auth_header(_admin_token()),
        )

        assert response.status_code == 400

    async def test_invalid_target_returns_404(self, mock_client):
        """Migrating to non-existent target returns 404."""
        node = make_mock_node(node_id=5, parent_id=2, level=3, name="上海分部")

        mock_client._mock_db.execute = AsyncMock()
        mock_client._mock_db.execute.side_effect = [
            mock_scalar_result(first_value=node),  # find source node
            mock_scalar_result(first_value=None),   # find target - not found
        ]

        response = await mock_client.post(
            "/api/v1/admin/hierarchy/nodes/5/migrate",
            json={"targetParentId": 999},
            headers=auth_header(_admin_token()),
        )

        assert response.status_code == 404
