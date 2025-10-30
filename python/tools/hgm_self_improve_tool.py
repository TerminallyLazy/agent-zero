# python/tools/hgm_self_improve_tool.py
from python.helpers.tool import Tool, Response
from python.helpers.hgm_tree import TreeNode
from python.helpers.hgm_thompson import thompson_sample
import json
import os
import time
from typing import Dict, Any

class HGMSelfImprove(Tool):
    """
    Tool for orchestrating HGM self-improvement process.

    Operations:
    - initialize: Setup initial agent version and root node
    - expand: Create new agent variant from promising node
    - evaluate: Evaluate agent on a task
    - status: Report current tree statistics
    """

    async def execute(self, **kwargs) -> Response:
        operation = self.args.get('operation', 'status')

        if operation == 'initialize':
            return await self._initialize()
        elif operation == 'expand':
            return await self._expand()
        elif operation == 'evaluate':
            return await self._evaluate()
        elif operation == 'status':
            return await self._status()
        else:
            return Response(
                message=f"Error: Unknown operation '{operation}'",
                break_loop=False
            )

    async def _initialize(self) -> Response:
        """Setup initial agent version and create root node"""
        output_dir = self.args.get('output_dir', 'output_hgm')
        agent_profile = self.args.get('agent_profile', 'default')
        config = self.args.get('config', {})

        # Create output directory
        os.makedirs(output_dir, exist_ok=True)

        # Get current git commit (representing initial agent version)
        import subprocess

        try:
            result = subprocess.run(
                ['git', 'rev-parse', 'HEAD'],
                capture_output=True,
                text=True,
                check=True
            )
            initial_commit = result.stdout.strip()[:40]
        except subprocess.CalledProcessError as e:
            return Response(
                message=f"Error getting git commit: {e.stderr}",
                break_loop=False
            )

        # Create root node
        root_node = TreeNode(
            commit_id=initial_commit,
            parent_id=None,
            node_id=0
        )

        # Initialize HGM state in agent data
        nodes: Dict[int, TreeNode] = {0: root_node}
        self.agent.set_data('hgm_nodes', nodes)
        self.agent.set_data('hgm_submitted_ids', set())
        self.agent.set_data('hgm_n_task_evals', 0)
        self.agent.set_data('hgm_config', config)
        self.agent.set_data('hgm_output_dir', output_dir)
        self.agent.set_data('hgm_agent_profile', agent_profile)
        self.agent.set_data('hgm_next_node_id', 1)

        # Save metadata
        metadata = {
            'root_node': root_node.to_dict(),
            'initial_commit': initial_commit,
            'agent_profile': agent_profile,
            'config': config,
            'created_at': time.time()
        }

        metadata_file = os.path.join(output_dir, 'hgm_metadata.json')
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)

        return Response(
            message=f"""HGM system initialized successfully.

Root node: {root_node}
Initial commit: {initial_commit}
Output directory: {output_dir}
Agent profile: {agent_profile}

Metadata saved to: {metadata_file}
""",
            break_loop=False
        )

    async def _expand(self) -> Response:
        """Create new agent variant from promising node"""
        # Stub for future implementation
        return Response(
            message="Expand operation not yet implemented",
            break_loop=False
        )

    async def _evaluate(self) -> Response:
        """Evaluate agent on a task"""
        # Stub for future implementation
        return Response(
            message="Evaluate operation not yet implemented",
            break_loop=False
        )

    async def _status(self) -> Response:
        """Report current tree statistics"""
        nodes = self.agent.get_data('hgm_nodes')

        if nodes is None:
            return Response(
                message="HGM system not initialized. Run with operation='initialize' first.",
                break_loop=False
            )

        n_task_evals = self.agent.get_data('hgm_n_task_evals') or 0
        config = self.agent.get_data('hgm_config') or {}

        # Calculate statistics
        total_nodes = len(nodes)
        total_evals = sum(len(node.utility_measures) for node in nodes.values())

        # Find best performing node
        best_node = max(nodes.values(), key=lambda n: (n.mean_utility, len(n.utility_measures)))

        status_msg = f"""HGM System Status:

Total nodes: {total_nodes}
Total evaluations: {total_evals}
Task evaluations: {n_task_evals} / {config.get('max_task_evals', 'N/A')}

Best performing node:
  {best_node}

Tree structure:
"""

        # Show tree hierarchy
        def show_tree(node: TreeNode, indent: int = 0):
            prefix = "  " * indent
            msg = f"{prefix}- {node}\n"
            for child in node.children:
                msg += show_tree(child, indent + 1)
            return msg

        root = nodes[0]
        status_msg += show_tree(root)

        return Response(
            message=status_msg,
            break_loop=False
        )

    def get_log_object(self):
        return self.agent.context.log.log(
            type="tool",
            heading=f"icon://account_tree HGM Self-Improve: {self.args.get('operation', 'unknown')}",
            content="",
            kvps=self.args,
        )
