# tests/unit/test_hgm_tree.py
import pytest
from python.helpers.hgm_tree import TreeNode

def test_node_creation():
    """Verify node initialization"""
    node = TreeNode(
        commit_id="abc123",
        parent_id=None,
        node_id=0
    )

    assert node.commit_id == "abc123"
    assert node.parent_id is None
    assert node.node_id == 0
    assert node.children == []
    assert node.utility_measures == []

def test_mean_utility_calculation():
    """Verify utility metric computation"""
    node = TreeNode(
        commit_id="abc123",
        parent_id=None,
        node_id=0,
        utility_measures=[1, 1, 0, 1, 0, 1]
    )

    # Mean of [1,1,0,1,0,1] = 4/6 = 0.666...
    assert abs(node.mean_utility - 0.6667) < 0.001

def test_mean_utility_empty():
    """Verify mean utility with no measurements"""
    node = TreeNode(
        commit_id="abc123",
        parent_id=None,
        node_id=0
    )

    assert node.mean_utility == 0.0

def test_add_child():
    """Verify child node addition"""
    parent = TreeNode(commit_id="parent", parent_id=None, node_id=0)
    child = TreeNode(commit_id="child", parent_id="parent", node_id=1)

    parent.add_child(child)

    assert len(parent.children) == 1
    assert parent.children[0] == child

def test_serialization():
    """Verify node serialization/deserialization"""
    node = TreeNode(
        commit_id="abc123",
        parent_id="parent456",
        node_id=5,
        utility_measures=[1, 0, 1, 1]
    )

    # Add child
    child = TreeNode(commit_id="child789", parent_id="abc123", node_id=6)
    node.add_child(child)

    # Serialize
    data = node.to_dict()

    assert data['commit_id'] == "abc123"
    assert data['parent_id'] == "parent456"
    assert data['node_id'] == 5
    assert data['utility_measures'] == [1, 0, 1, 1]
    assert len(data['children']) == 1
    assert data['children'][0]['commit_id'] == "child789"

    # Deserialize
    restored = TreeNode.from_dict(data)

    assert restored.commit_id == node.commit_id
    assert restored.parent_id == node.parent_id
    assert restored.node_id == node.node_id
    assert restored.utility_measures == node.utility_measures
    assert len(restored.children) == 1

def test_descendant_traversal():
    """Verify tree traversal algorithms"""
    # Create tree structure:
    #     root
    #    /    \
    #   c1     c2
    #  /
    # c3

    root = TreeNode(
        commit_id="root",
        parent_id=None,
        node_id=0,
        utility_measures=[1, 1]
    )

    child1 = TreeNode(
        commit_id="child1",
        parent_id="root",
        node_id=1,
        utility_measures=[1, 0, 1]
    )

    child2 = TreeNode(
        commit_id="child2",
        parent_id="root",
        node_id=2,
        utility_measures=[0, 0]
    )

    child3 = TreeNode(
        commit_id="child3",
        parent_id="child1",
        node_id=3,
        utility_measures=[1, 1, 1]
    )

    root.add_child(child1)
    root.add_child(child2)
    child1.add_child(child3)

    # Get descendant evals with no pseudo-counts
    descendant_evals = root.get_descendant_evals(num_pseudo=0)

    # Should include: root (2), child1 (3), child2 (2), child3 (3) = 10 total
    assert len(descendant_evals) == 10
    assert sum(descendant_evals) == 7  # 1+1 + 1+0+1 + 0+0 + 1+1+1

    # With pseudo-counts
    descendant_evals_pseudo = root.get_descendant_evals(num_pseudo=10)
    assert len(descendant_evals_pseudo) == 20  # 10 real + 10 pseudo
