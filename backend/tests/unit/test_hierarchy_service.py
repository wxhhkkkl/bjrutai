"""Unit tests for hierarchy service cycle detection logic.

Pure Python tests with no database dependency.
Tests the DFS cycle detection algorithm with various tree structures.
"""

import pytest


# ============================================================================
# Cycle detection algorithm (pure function under test)
# ============================================================================
def _detect_cycle_dfs(source_id: int, target_parent_id: int, adjacency: dict[int, list[int]]) -> bool:
    """DFS-based cycle detection.

    Returns True if new_parent_id is a descendant of node_id (would create a cycle).
    """
    if source_id == target_parent_id:
        return True

    visited: set[int] = set()
    stack = [source_id]

    while stack:
        current = stack.pop()
        if current == target_parent_id:
            return True
        if current in visited:
            continue
        visited.add(current)
        for child_id in adjacency.get(current, []):
            if child_id not in visited:
                stack.append(child_id)

    return False


# ============================================================================
# Test helpers
# ============================================================================
def _build_adjacency(edges: list[tuple[int, int]]) -> dict[int, list[int]]:
    """Build adjacency dict from (parent_id, child_id) pairs."""
    adj: dict[int, list[int]] = {}
    for parent, child in edges:
        adj.setdefault(parent, []).append(child)
    return adj


# ============================================================================
# Tests
# ============================================================================
class TestCycleDetectionSimple:
    """Simple cycle detection scenarios."""

    def test_direct_cycle_parent_to_self(self):
        """Moving a node to itself is a cycle."""
        assert _detect_cycle_dfs(5, 5, {}) is True

    def test_direct_cycle_parent_is_child(self):
        """Moving a node to its own direct child is a cycle."""
        # Node 2 has child 5; moving 2 under 5 would create cycle
        adj = _build_adjacency([(2, 5)])
        assert _detect_cycle_dfs(2, 5, adj) is True

    def test_no_cycle_sibling_move(self):
        """Moving a node to its sibling is NOT a cycle."""
        # Root 1 has children 2 and 3; moving 2's child 4 to 3 is fine
        adj = _build_adjacency([(1, 2), (1, 3), (2, 4)])
        assert _detect_cycle_dfs(4, 3, adj) is False

    def test_no_cycle_unrelated_branch(self):
        """Moving between unrelated branches is fine."""
        adj = _build_adjacency([(1, 2), (1, 3), (2, 4), (3, 5)])
        assert _detect_cycle_dfs(4, 5, adj) is False


class TestCycleDetectionDeep:
    """Cycle detection with deep nested trees (>4 levels)."""

    def test_deep_tree_no_cycle(self):
        """Moving a leaf in a deep tree between unrelated branches."""
        # Level 1 -> 2 -> 3 -> 4 -> 5 -> 6 (chain1)
        # Level 1 -> 20 -> 30 (chain2)
        adj = _build_adjacency([
            (1, 2), (2, 3), (3, 4), (4, 5), (5, 6),
            (1, 20), (20, 30),
        ])
        # Move node 6 (deepest leaf of chain1) to node 30 (chain2)
        assert _detect_cycle_dfs(6, 30, adj) is False

    def test_deep_tree_cycle_detected(self):
        """Detect cycle in deep tree where target is a deep descendant."""
        # Level 1 -> 2 -> 3 -> 4 -> 5 -> 6
        adj = _build_adjacency([
            (1, 2), (2, 3), (3, 4), (4, 5), (5, 6),
        ])
        # Move node 2 to its great-great-grandchild 5 - CYCLE!
        assert _detect_cycle_dfs(2, 5, adj) is True

    def test_max_level_6_no_cycle(self):
        """Max level 6 tree - moving root of one chain to another chain's leaf."""
        # Chain A: 1 -> 2 -> 3 -> 4 -> 5 -> 6
        # Chain B: 10 -> 20
        adj = _build_adjacency([
            (1, 2), (2, 3), (3, 4), (4, 5), (5, 6),
            (1, 10), (10, 20),
        ])
        # Move node 10 (with its subtree) to node 6
        assert _detect_cycle_dfs(10, 6, adj) is False


class TestCycleDetectionVariousStructures:
    """Various tree shapes for cycle detection."""

    def test_wide_tree_no_cycle(self):
        """Wide tree with many siblings - no cycle when moving across branches."""
        # Root 1 with 10 children, each with 5 children
        edges = []
        for i in range(2, 12):
            edges.append((1, i))
            for j in range(i * 10, i * 10 + 5):
                edges.append((i, j))
        adj = _build_adjacency(edges)
        # Move a grandchild of node 2 to a child of node 11
        assert _detect_cycle_dfs(20, 11, adj) is False

    def test_wide_tree_cycle_to_ancestor(self):
        """Wide tree - moving ancestor to descendant creates cycle."""
        edges = [(1, 2), (2, 3), (3, 4), (4, 5)]
        for i in range(10, 20):
            edges.append((5, i))
        adj = _build_adjacency(edges)
        # Move node 3 under one of its deep descendants
        assert _detect_cycle_dfs(3, 15, adj) is True

    def test_chain_cycle_last_to_root(self):
        """Moving root of a chain to a leaf in that chain."""
        adj = _build_adjacency([(1, 2), (2, 3), (3, 4)])
        # Move node 2 under node 4
        assert _detect_cycle_dfs(2, 4, adj) is True

    def test_single_node_no_children(self):
        """Single node with no children - no cycle to unrelated node."""
        adj = _build_adjacency([(1, 2)])
        # Move node 2 (leaf) under a new node 10
        assert _detect_cycle_dfs(2, 10, adj) is False

    def test_root_to_self(self):
        """Moving root to itself."""
        adj = _build_adjacency([(1, 2), (1, 3), (2, 4)])
        assert _detect_cycle_dfs(1, 1, adj) is True

    def test_empty_adjacency(self):
        """Empty tree - no cycle possible."""
        assert _detect_cycle_dfs(1, 2, {}) is False


class TestCycleDetectionEdgeCases:
    """Edge cases for cycle detection."""

    def test_proposed_cycle_large_tree(self):
        """Large tree with cross-branch migration that would create cycle."""
        # Build a tree: 1 -> 2,3; 2 -> 4,5; 3 -> 6,7; 4 -> 8,9
        adj = _build_adjacency([
            (1, 2), (1, 3),
            (2, 4), (2, 5),
            (3, 6), (3, 7),
            (4, 8), (4, 9),
        ])
        # Move node 2 under node 8 (8 is descendant of 4 which is under 2)
        assert _detect_cycle_dfs(2, 8, adj) is True

    def test_same_level_cousins_no_cycle(self):
        """Cousins at the same level - no cycle."""
        adj = _build_adjacency([
            (1, 2), (1, 3),
            (2, 4), (3, 5),
        ])
        assert _detect_cycle_dfs(4, 5, adj) is False

    def test_uncle_nephew(self):
        """Moving nephew under uncle - no cycle (same level different branches)."""
        adj = _build_adjacency([
            (1, 2), (1, 3),
            (2, 4),  # 4 is child of 2
        ])
        # Move 4 (child of 2) under 3 (sibling of 2) - no cycle
        assert _detect_cycle_dfs(4, 3, adj) is False

    def test_grandparent_under_grandchild(self):
        """Moving grandparent under grandchild creates cycle."""
        adj = _build_adjacency([
            (1, 2), (2, 3), (3, 4),
        ])
        assert _detect_cycle_dfs(2, 4, adj) is True
