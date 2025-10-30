# python/helpers/hgm_tree.py
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class TreeNode:
    """
    Represents a node in the HGM agent evolution tree.

    Each node corresponds to a specific agent version (git commit)
    and tracks its performance across multiple evaluations.
    """
    commit_id: str
    parent_id: Optional[str]
    node_id: int
    children: list['TreeNode'] = field(default_factory=list)
    utility_measures: list[int] = field(default_factory=list)

    @property
    def mean_utility(self) -> float:
        """Calculate mean utility from measures"""
        if not self.utility_measures:
            return 0.0
        return sum(self.utility_measures) / len(self.utility_measures)

    def add_child(self, child: 'TreeNode') -> None:
        """Add a child node"""
        if child not in self.children:
            self.children.append(child)

    def get_descendant_evals(self, num_pseudo: int = 10) -> list[int]:
        """
        Get descendant evaluation metrics for promise estimation.

        Aggregates utility measures from this node and all descendants,
        adding pseudo-counts for regularization.

        Args:
            num_pseudo: Number of pseudo-counts to add (default: 10)

        Returns:
            List of utility measures including descendants and pseudo-counts
        """
        # Start with this node's measures
        all_evals = self.utility_measures.copy()

        # Recursively collect from descendants
        def collect_from_children(node: TreeNode):
            for child in node.children:
                all_evals.extend(child.utility_measures)
                collect_from_children(child)

        collect_from_children(self)

        # Add pseudo-counts for regularization
        # Assume 50% success rate for pseudo-counts
        pseudo_successes = num_pseudo // 2
        pseudo_failures = num_pseudo - pseudo_successes
        all_evals.extend([1] * pseudo_successes + [0] * pseudo_failures)

        return all_evals

    def to_dict(self) -> dict:
        """Serialize node to dictionary"""
        return {
            'commit_id': self.commit_id,
            'parent_id': self.parent_id,
            'node_id': self.node_id,
            'utility_measures': self.utility_measures,
            'children': [child.to_dict() for child in self.children]
        }

    @staticmethod
    def from_dict(data: dict) -> 'TreeNode':
        """Deserialize node from dictionary"""
        node = TreeNode(
            commit_id=data['commit_id'],
            parent_id=data['parent_id'],
            node_id=data['node_id'],
            utility_measures=data.get('utility_measures', [])
        )

        # Recursively restore children
        for child_data in data.get('children', []):
            child = TreeNode.from_dict(child_data)
            node.add_child(child)

        return node

    def __repr__(self) -> str:
        return (
            f"TreeNode(id={self.node_id}, commit={self.commit_id[:7]}, "
            f"parent={self.parent_id[:7] if self.parent_id else None}, "
            f"utility={self.mean_utility:.3f}, "
            f"evals={len(self.utility_measures)}, "
            f"children={len(self.children)})"
        )
