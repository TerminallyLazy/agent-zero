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
    - run: Execute self-improvement loop (expand/evaluate cycles)
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
        elif operation == 'run':
            return await self._run()
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
        """
        Create new agent variant from promising node

        Process:
        1. Get candidate nodes (mean_utility > 0)
        2. Use Thompson Sampling to select parent
        3. Generate child via HGMUtils.sample_child()
        4. Add child to tree structure
        5. Update metadata
        """
        # Get HGM state from agent data
        nodes: Dict[int, TreeNode] = self.agent.get_data('hgm_nodes')
        if nodes is None:
            return Response(
                message="HGM system not initialized. Run with operation='initialize' first.",
                break_loop=False
            )

        config = self.agent.get_data('hgm_config') or {}
        output_dir = self.agent.get_data('hgm_output_dir')

        # Get configuration parameters
        alpha = config.get('alpha', 1.0)
        beta = config.get('beta', 1.0)
        cool_down = config.get('cool_down', True)
        n_task_evals = self.agent.get_data('hgm_n_task_evals') or 0
        max_task_evals = config.get('max_task_evals', 1000)

        # Filter candidate nodes (must have mean_utility > 0)
        candidate_nodes = [node for node in nodes.values() if node.mean_utility > 0]

        if not candidate_nodes:
            # No candidates yet, use root node
            candidate_nodes = [nodes[0]]

        self.agent.context.log.log(
            type="hgm",
            heading="Expand - Node Selection",
            content=f"Found {len(candidate_nodes)} candidate nodes for expansion"
        )

        # Prepare evaluations for Thompson Sampling
        evaluations = [
            node.get_descendant_evals(num_pseudo=10)
            for node in candidate_nodes
        ]

        # Use Thompson Sampling to select parent node
        selected_idx = thompson_sample(
            evaluations=evaluations,
            alpha=alpha,
            beta=beta,
            cool_down=cool_down,
            n_task_evals=n_task_evals,
            max_task_evals=max_task_evals
        )

        parent_node = candidate_nodes[selected_idx]

        self.agent.context.log.log(
            type="hgm",
            heading="Expand - Parent Selected",
            content=f"Selected node {parent_node.node_id} as parent (mean utility: {parent_node.mean_utility:.3f})"
        )

        # Initialize HGMUtils
        from python.helpers.hgm_utils import HGMUtils

        git_dir = self.args.get('git_dir', os.getcwd())
        base_commit = self.args.get('base_commit', 'HEAD')
        total_tasks = self.args.get('total_tasks', [])

        hgm_utils = HGMUtils(
            agent=self.agent,
            output_dir=output_dir,
            git_dir=git_dir,
            base_commit=base_commit,
            total_tasks=total_tasks
        )

        # Generate child agent version
        new_commit_id, child_node_id = await hgm_utils.sample_child(
            parent_node=parent_node,
            max_attempts=config.get('max_child_attempts', 3)
        )

        if new_commit_id is None or child_node_id is None:
            return Response(
                message=f"Failed to generate child from node {parent_node.node_id} after {config.get('max_child_attempts', 3)} attempts",
                break_loop=False
            )

        # Create new child node
        child_node = TreeNode(
            commit_id=new_commit_id,
            parent_id=parent_node.commit_id,
            node_id=child_node_id
        )

        # Add child to parent's children list
        parent_node.add_child(child_node)

        # Update nodes dictionary
        nodes[child_node_id] = child_node
        self.agent.set_data('hgm_nodes', nodes)

        # Update next node ID
        self.agent.set_data('hgm_next_node_id', child_node_id + 1)

        # Save tree metadata
        metadata_file = os.path.join(output_dir, 'hgm_metadata.json')
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)

        metadata['total_nodes'] = len(nodes)
        metadata['last_expand'] = {
            'parent_node_id': parent_node.node_id,
            'child_node_id': child_node_id,
            'commit_id': new_commit_id,
            'timestamp': time.time()
        }

        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)

        self.agent.context.log.log(
            type="hgm",
            heading="Expand - Success",
            content=f"Created child node {child_node_id} from parent {parent_node.node_id}"
        )

        return Response(
            message=f"""Successfully expanded from node {parent_node.node_id}

Parent node: {parent_node}
Child node:  {child_node}
New commit:  {new_commit_id}

Total nodes in tree: {len(nodes)}
""",
            break_loop=False
        )

    async def _evaluate(self) -> Response:
        """
        Evaluate agent on a task

        Process:
        1. Get nodes with available tasks
        2. Use Thompson Sampling to select node
        3. Select an available task
        4. Evaluate via HGMUtils.eval_agent()
        5. Update utility measures
        6. Update metadata
        """
        # Get HGM state from agent data
        nodes: Dict[int, TreeNode] = self.agent.get_data('hgm_nodes')
        if nodes is None:
            return Response(
                message="HGM system not initialized. Run with operation='initialize' first.",
                break_loop=False
            )

        config = self.agent.get_data('hgm_config') or {}
        output_dir = self.agent.get_data('hgm_output_dir')
        submitted_ids = self.agent.get_data('hgm_submitted_ids') or set()

        # Get configuration parameters
        alpha = config.get('alpha', 1.0)
        beta = config.get('beta', 1.0)
        cool_down = config.get('cool_down', True)
        n_task_evals = self.agent.get_data('hgm_n_task_evals') or 0
        max_task_evals = config.get('max_task_evals', 1000)

        # Initialize HGMUtils
        git_dir = self.args.get('git_dir', os.getcwd())
        base_commit = self.args.get('base_commit', 'HEAD')
        total_tasks = self.args.get('total_tasks', [])

        from python.helpers.hgm_utils import HGMUtils

        hgm_utils = HGMUtils(
            agent=self.agent,
            output_dir=output_dir,
            git_dir=git_dir,
            base_commit=base_commit,
            total_tasks=total_tasks
        )

        # Get nodes that have available tasks
        available_nodes = []
        for node in nodes.values():
            # Load node metadata to check evaluated tasks
            metadata = hgm_utils.load_node_metadata(node)
            if metadata is None:
                metadata = {'evaluated_tasks': {}}

            evaluated_task_ids = set(metadata.get('evaluated_tasks', {}).keys())
            node_available_tasks = [t for t in total_tasks if t not in evaluated_task_ids]

            if node_available_tasks:
                available_nodes.append(node)

        if not available_nodes:
            return Response(
                message="No nodes with available tasks. All evaluations complete!",
                break_loop=False
            )

        self.agent.context.log.log(
            type="hgm",
            heading="Evaluate - Node Selection",
            content=f"Found {len(available_nodes)} nodes with available tasks"
        )

        # Prepare evaluations for Thompson Sampling
        evaluations = [
            node.utility_measures if node.utility_measures else [0]
            for node in available_nodes
        ]

        # Use Thompson Sampling to select node
        selected_idx = thompson_sample(
            evaluations=evaluations,
            alpha=alpha,
            beta=beta,
            cool_down=cool_down,
            n_task_evals=n_task_evals,
            max_task_evals=max_task_evals
        )

        selected_node = available_nodes[selected_idx]

        self.agent.context.log.log(
            type="hgm",
            heading="Evaluate - Node Selected",
            content=f"Selected node {selected_node.node_id} for evaluation (mean utility: {selected_node.mean_utility:.3f})"
        )

        # Get available tasks for this node
        metadata = hgm_utils.load_node_metadata(selected_node)
        if metadata is None:
            metadata = {'evaluated_tasks': {}}

        evaluated_task_ids = set(metadata.get('evaluated_tasks', {}).keys())
        node_available_tasks = [t for t in total_tasks if t not in evaluated_task_ids]

        # Select number of tasks to evaluate
        num_tasks = self.args.get('num_tasks', 1)
        tasks_to_eval = node_available_tasks[:num_tasks]

        self.agent.context.log.log(
            type="hgm",
            heading="Evaluate - Tasks Selected",
            content=f"Evaluating {len(tasks_to_eval)} tasks: {tasks_to_eval}"
        )

        # Evaluate agent on tasks
        results = await hgm_utils.eval_agent(
            node=selected_node,
            tasks=tasks_to_eval
        )

        # Update utility measures
        selected_node.utility_measures.extend(results)

        # Update task evaluation counter
        n_task_evals += len(tasks_to_eval)
        self.agent.set_data('hgm_n_task_evals', n_task_evals)

        # Update nodes in agent data
        self.agent.set_data('hgm_nodes', nodes)

        # Save tree metadata
        metadata_file = os.path.join(output_dir, 'hgm_metadata.json')
        with open(metadata_file, 'r') as f:
            tree_metadata = json.load(f)

        tree_metadata['total_evals'] = sum(len(node.utility_measures) for node in nodes.values())
        tree_metadata['n_task_evals'] = n_task_evals
        tree_metadata['last_evaluate'] = {
            'node_id': selected_node.node_id,
            'tasks': tasks_to_eval,
            'results': results,
            'timestamp': time.time()
        }

        with open(metadata_file, 'w') as f:
            json.dump(tree_metadata, f, indent=2)

        success_count = sum(results)
        self.agent.context.log.log(
            type="hgm",
            heading="Evaluate - Complete",
            content=f"Node {selected_node.node_id} evaluation: {success_count}/{len(results)} tasks passed"
        )

        return Response(
            message=f"""Successfully evaluated node {selected_node.node_id}

Tasks evaluated: {tasks_to_eval}
Results: {results}
Success rate: {success_count}/{len(results)} ({success_count/len(results)*100:.1f}%)

Node statistics:
  Total evaluations: {len(selected_node.utility_measures)}
  Mean utility: {selected_node.mean_utility:.3f}

Progress: {n_task_evals} / {max_task_evals} task evaluations
""",
            break_loop=False
        )

    async def _run(self) -> Response:
        """
        Run the self-improvement loop

        Main orchestration loop that coordinates expand and evaluate operations.
        Uses the decision rule from original HGM:
        if n_task_evals**alpha >= len(nodes) - 1 + n_pending_expands:
            expand()  # Create new agent variant
        else:
            evaluate()  # Evaluate existing agent

        Parameters:
        - iterations: Number of expand/evaluate cycles to run (default: 10)
        - max_concurrent: Maximum concurrent operations (default: 1 for sequential)
        """
        # Get HGM state
        nodes: Dict[int, TreeNode] = self.agent.get_data('hgm_nodes')
        if nodes is None:
            return Response(
                message="HGM system not initialized. Run with operation='initialize' first.",
                break_loop=False
            )

        config = self.agent.get_data('hgm_config') or {}
        n_task_evals = self.agent.get_data('hgm_n_task_evals') or 0
        max_task_evals = config.get('max_task_evals', 1000)
        alpha = config.get('alpha', 1.0)

        # Get run parameters
        iterations = self.args.get('iterations', 10)
        max_concurrent = self.args.get('max_concurrent', 1)

        self.agent.context.log.log(
            type="hgm",
            heading="Run - Starting",
            content=f"Running {iterations} iterations with alpha={alpha}"
        )

        # Track pending operations
        n_pending_expands = 0
        results = []

        for i in range(iterations):
            # Check if we've hit max task evaluations
            n_task_evals = self.agent.get_data('hgm_n_task_evals') or 0
            if n_task_evals >= max_task_evals:
                self.agent.context.log.log(
                    type="hgm",
                    heading="Run - Complete",
                    content=f"Reached max task evaluations ({max_task_evals})"
                )
                break

            # Get current number of nodes
            nodes = self.agent.get_data('hgm_nodes')
            num_nodes = len(nodes)

            # Decision rule: expand vs evaluate
            # if n_task_evals**alpha >= len(nodes) - 1 + n_pending_expands
            should_expand = (n_task_evals ** alpha) >= (num_nodes - 1 + n_pending_expands)

            self.agent.context.log.log(
                type="hgm",
                heading=f"Run - Iteration {i+1}/{iterations}",
                content=f"Decision: {'EXPAND' if should_expand else 'EVALUATE'} (n_task_evals={n_task_evals}, nodes={num_nodes}, alpha={alpha})"
            )

            if should_expand:
                # Expand: create new agent variant
                n_pending_expands += 1
                try:
                    response = await self._expand()
                    n_pending_expands -= 1
                    results.append({
                        'iteration': i + 1,
                        'operation': 'expand',
                        'success': 'successfully expanded' in response.message.lower(),
                        'message': response.message
                    })
                except Exception as e:
                    n_pending_expands -= 1
                    self.agent.context.log.log(
                        type="hgm",
                        heading="Run - Expand Error",
                        content=f"Iteration {i+1} expand failed: {str(e)}"
                    )
                    results.append({
                        'iteration': i + 1,
                        'operation': 'expand',
                        'success': False,
                        'error': str(e)
                    })
            else:
                # Evaluate: evaluate existing agent
                try:
                    response = await self._evaluate()
                    results.append({
                        'iteration': i + 1,
                        'operation': 'evaluate',
                        'success': 'successfully evaluated' in response.message.lower(),
                        'message': response.message
                    })
                except Exception as e:
                    self.agent.context.log.log(
                        type="hgm",
                        heading="Run - Evaluate Error",
                        content=f"Iteration {i+1} evaluate failed: {str(e)}"
                    )
                    results.append({
                        'iteration': i + 1,
                        'operation': 'evaluate',
                        'success': False,
                        'error': str(e)
                    })

        # Generate summary
        expand_count = sum(1 for r in results if r['operation'] == 'expand')
        evaluate_count = sum(1 for r in results if r['operation'] == 'evaluate')
        success_count = sum(1 for r in results if r.get('success', False))

        nodes = self.agent.get_data('hgm_nodes')
        n_task_evals = self.agent.get_data('hgm_n_task_evals') or 0

        summary = f"""HGM Self-Improvement Run Complete

Iterations completed: {len(results)}/{iterations}
Operations:
  - Expand: {expand_count}
  - Evaluate: {evaluate_count}
  - Success rate: {success_count}/{len(results)} ({success_count/len(results)*100:.1f}%)

Final statistics:
  - Total nodes: {len(nodes)}
  - Task evaluations: {n_task_evals}/{max_task_evals}
  - Tree depth: {self._calculate_tree_depth(nodes[0])}

Best performing node:
"""

        # Find best node
        if nodes:
            best_node = max(nodes.values(), key=lambda n: (n.mean_utility, len(n.utility_measures)))
            summary += f"  {best_node}\n"

        self.agent.context.log.log(
            type="hgm",
            heading="Run - Complete",
            content=summary
        )

        return Response(
            message=summary,
            break_loop=False
        )

    def _calculate_tree_depth(self, node: TreeNode, current_depth: int = 0) -> int:
        """Calculate maximum depth of tree from given node"""
        if not node.children:
            return current_depth
        return max(self._calculate_tree_depth(child, current_depth + 1) for child in node.children)

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
