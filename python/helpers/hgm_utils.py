"""
HGM (Hierarchical Genetic Memory) Utility Functions

This module provides core utilities for the HGM self-improvement system:
- sample_child(): Generate new agent versions through diagnosis and improvement
- eval_agent(): Evaluate agent performance on tasks
- choose_entry(): Select diagnosis strategy based on parent performance
- Metadata persistence and management

Adapted from: https://github.com/metauto-ai/HGM
"""

import json
import os
import random
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from python.helpers.hgm_tree import TreeNode
from python.helpers.tool import Response
from python.helpers.hgm_task_manager import (
    TaskPool,
    TaskManager,
    TaskResult,
    TaskSelectionStrategy
)


class HGMUtils:
    """Core utilities for HGM self-improvement operations"""

    def __init__(
        self,
        agent,
        output_dir: str,
        git_dir: str,
        base_commit: str,
        total_tasks: List[str],
        task_selection_strategy: TaskSelectionStrategy = TaskSelectionStrategy.RANDOM
    ):
        """
        Initialize HGM utilities

        Args:
            agent: Agent instance for tool access
            output_dir: Directory for HGM outputs and metadata
            git_dir: Path to git repository being improved
            base_commit: Base commit for comparisons
            total_tasks: List of all task IDs available for evaluation
            task_selection_strategy: Strategy for selecting tasks (default: RANDOM)
        """
        self.agent = agent
        self.output_dir = output_dir
        self.git_dir = git_dir
        self.base_commit = base_commit
        self.total_tasks = total_tasks
        self.task_selection_strategy = task_selection_strategy

        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)

        # Initialize task management system
        task_pool = TaskPool(
            task_ids=total_tasks,
            metadata_file=os.path.join(output_dir, 'task_metadata.json')
        )
        self.task_manager = TaskManager(
            task_pool=task_pool,
            cache_file=os.path.join(output_dir, 'task_cache.json')
        )

    async def sample_child(
        self,
        parent_node: TreeNode,
        max_attempts: int = 3
    ) -> Tuple[Optional[str], Optional[int]]:
        """
        Generate a new child agent version through diagnosis and improvement

        This is the core self-improvement function that:
        1. Selects a diagnosis strategy based on parent performance
        2. Runs diagnostic analysis to identify improvements
        3. Generates a problem statement for the improvement
        4. Uses a subordinate agent to implement the improvement
        5. Captures the new commit as a child node

        Args:
            parent_node: Parent node to improve from
            max_attempts: Maximum retry attempts on failure

        Returns:
            Tuple of (new_commit_id, child_node_id) or (None, None) on failure
        """
        # Generate run ID and create output directory for this child
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_id = f"child_{parent_node.node_id}_{timestamp}"
        child_output_dir = os.path.join(self.output_dir, run_id)
        os.makedirs(child_output_dir, exist_ok=True)

        # Check if parent failed
        if parent_node.commit_id == "failed":
            self.agent.context.log.log(
                type="hgm",
                heading="Sample Child",
                content=f"Parent node {parent_node.node_id} failed, cannot generate child"
            )
            return None, None

        # Load parent metadata to understand performance
        parent_metadata_path = self._get_metadata_path(parent_node.commit_id)
        if not os.path.exists(parent_metadata_path):
            self.agent.context.log.log(
                type="hgm",
                heading="Sample Child",
                content=f"Parent metadata not found: {parent_metadata_path}"
            )
            return None, None

        with open(parent_metadata_path, 'r') as f:
            parent_metadata = json.load(f)

        # Choose diagnosis strategy
        entry = self.choose_entry(parent_metadata)

        self.agent.context.log.log(
            type="hgm",
            heading="Sample Child",
            content=f"Selected strategy: {entry} for parent node {parent_node.node_id}"
        )

        # Run diagnostic analysis to generate problem statement
        problem_statement = await self._run_diagnosis(
            parent_node,
            parent_metadata,
            entry,
            child_output_dir
        )

        if not problem_statement:
            self.agent.context.log.log(
                type="hgm",
                heading="Sample Child",
                content="Diagnosis failed to generate problem statement"
            )
            return None, None

        # Reset to parent commit
        result = subprocess.run(
            ['git', 'reset', '--hard', parent_node.commit_id],
            cwd=self.git_dir,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            self.agent.context.log.log(
                type="hgm",
                heading="Sample Child",
                content=f"Failed to reset to parent commit: {result.stderr}"
            )
            return None, None

        # Use subordinate agent to implement improvement
        attempt = 0
        while attempt < max_attempts:
            try:
                # Create subordinate agent to implement the improvement
                from python.tools.call_subordinate import Delegation

                delegation = Delegation(
                    agent=self.agent,
                    name="call_subordinate",
                    method=None,
                    args={
                        'message': f"""You are improving the coding agent system.

Repository: {self.git_dir}
Base Commit: {parent_node.commit_id}

Problem to solve:
{problem_statement}

Please implement the necessary changes to address this problem. Make targeted improvements to the relevant code.""",
                        'reset': 'true'
                    },
                    message="Delegating improvement implementation to subordinate",
                    loop_data=None
                )

                response = await delegation.execute()

                # Get the new commit ID
                result = subprocess.run(
                    ['git', 'rev-parse', 'HEAD'],
                    cwd=self.git_dir,
                    capture_output=True,
                    text=True,
                    check=True
                )
                new_commit_id = result.stdout.strip()

                # Check if any changes were made
                if new_commit_id == parent_node.commit_id:
                    self.agent.context.log.log(
                        type="hgm",
                        heading="Sample Child",
                        content=f"Attempt {attempt + 1}: No changes made, retrying..."
                    )
                    attempt += 1
                    continue

                # Get next node ID from agent data
                nodes: Dict[int, TreeNode] = self.agent.get_data('hgm_nodes') or {}
                child_node_id = max(nodes.keys()) + 1 if nodes else 1

                # Save child metadata
                child_metadata = {
                    'run_id': run_id,
                    'parent_commit': parent_node.commit_id,
                    'parent_node_id': parent_node.node_id,
                    'commit_id': new_commit_id,
                    'node_id': child_node_id,
                    'strategy': entry,
                    'problem_statement': problem_statement,
                    'timestamp': timestamp,
                    'attempt': attempt + 1
                }

                metadata_path = os.path.join(child_output_dir, 'metadata.json')
                with open(metadata_path, 'w') as f:
                    json.dump(child_metadata, f, indent=2)

                self.agent.context.log.log(
                    type="hgm",
                    heading="Sample Child",
                    content=f"Successfully created child node {child_node_id} from parent {parent_node.node_id}"
                )

                return new_commit_id, child_node_id

            except Exception as e:
                self.agent.context.log.log(
                    type="hgm",
                    heading="Sample Child",
                    content=f"Attempt {attempt + 1} failed: {str(e)}"
                )
                attempt += 1

        # All attempts failed
        return None, None

    async def eval_agent(
        self,
        node: TreeNode,
        tasks: Optional[List[str]] = None,
        num_tasks: int = 1
    ) -> List[int]:
        """
        Evaluate agent on specified tasks

        Args:
            node: TreeNode to evaluate
            tasks: Specific tasks to evaluate on (if None, uses task manager selection)
            num_tasks: Number of tasks to evaluate if tasks is None

        Returns:
            List of binary results (1 for success, 0 for failure) for each task
        """
        if node.commit_id == "failed":
            return [0] * num_tasks

        # Load node metadata for backward compatibility
        metadata_path = self._get_metadata_path(node.commit_id)
        if os.path.exists(metadata_path):
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
        else:
            metadata = {
                'commit_id': node.commit_id,
                'node_id': node.node_id,
                'evaluated_tasks': {},
                'resolved_ids': [],
                'unresolved_ids': [],
                'empty_patch_ids': []
            }

        # Select tasks if not provided - use task manager
        if tasks is None:
            # Check cache first
            available_tasks = self.task_manager.get_available_tasks(node.node_id)

            if not available_tasks:
                # All tasks evaluated, return cached results
                cached_results = self.task_manager.get_node_results(node.node_id)
                return [1 if r.success else 0 for r in list(cached_results.values())[:num_tasks]]

            # Use task manager to select tasks with strategy
            tasks = self.task_manager.select_tasks(
                node_id=node.node_id,
                num_tasks=num_tasks,
                strategy=self.task_selection_strategy
            )

        self.agent.context.log.log(
            type="hgm",
            heading="Eval Agent",
            content=f"Evaluating node {node.node_id} on {len(tasks)} tasks"
        )

        # Reset to node's commit
        result = subprocess.run(
            ['git', 'reset', '--hard', node.commit_id],
            cwd=self.git_dir,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            self.agent.context.log.log(
                type="hgm",
                heading="Eval Agent",
                content=f"Failed to reset to commit {node.commit_id}: {result.stderr}"
            )
            return [0] * len(tasks)

        # Evaluate each task
        results = []
        for task_id in tasks:
            # Use RepoSolver tool to solve the task
            from python.tools.repo_solver_tool import RepoSolver

            repo_solver = RepoSolver(
                agent=self.agent,
                name="repo_solver",
                method=None,
                args={
                    'mode': 'solve',
                    'git_dir': self.git_dir,
                    'base_commit': self.base_commit,
                    'problem_statement': f"Task {task_id}",  # Would load actual problem from dataset
                    'instance_id': f"{node.node_id}_{task_id}",
                    'timeout': 300
                },
                message="",
                loop_data=None
            )

            try:
                import time
                start_time = time.time()
                response = await repo_solver.execute()
                execution_time = time.time() - start_time

                # Check if solution was successful (simplified - would check tests)
                success = "success" in response.message.lower()
                result_value = 1 if success else 0

                results.append(result_value)

                # Cache result in task manager
                task_result = TaskResult(
                    task_id=task_id,
                    node_id=node.node_id,
                    commit_id=node.commit_id,
                    success=success,
                    execution_time=execution_time,
                    timestamp=time.time()
                )
                self.task_manager.cache_result(task_result)

                # Update legacy metadata for backward compatibility
                metadata['evaluated_tasks'][task_id] = result_value
                if success:
                    metadata['resolved_ids'].append(task_id)
                else:
                    metadata['unresolved_ids'].append(task_id)

            except Exception as e:
                self.agent.context.log.log(
                    type="hgm",
                    heading="Eval Agent",
                    content=f"Error evaluating task {task_id}: {str(e)}"
                )
                results.append(0)

                # Cache failure
                task_result = TaskResult(
                    task_id=task_id,
                    node_id=node.node_id,
                    commit_id=node.commit_id,
                    success=False,
                    error_message=str(e),
                    timestamp=time.time()
                )
                self.task_manager.cache_result(task_result)

                metadata['unresolved_ids'].append(task_id)

        # Update metadata
        metadata['accuracy'] = sum(results) / len(results) if results else 0.0

        # Save updated metadata
        metadata_path = self._get_metadata_path(node.commit_id)
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)

        self.agent.context.log.log(
            type="hgm",
            heading="Eval Agent",
            content=f"Node {node.node_id} evaluation complete: {sum(results)}/{len(results)} tasks passed"
        )

        return results

    def choose_entry(self, parent_metadata: Dict[str, Any]) -> str:
        """
        Select diagnosis strategy based on parent performance

        Strategy selection probabilities:
        - 25% solve_empty_patches (if >10% tasks produce empty patches)
        - 25% solve_stochasticity (improve consistency)
        - 25% solve_contextlength (if context errors detected)
        - Default: select random unresolved task

        Args:
            parent_metadata: Parent agent's performance metadata

        Returns:
            Strategy name or specific task ID
        """
        resolved_ids = parent_metadata.get('resolved_ids', [])
        unresolved_ids = parent_metadata.get('unresolved_ids', [])
        empty_patch_ids = parent_metadata.get('empty_patch_ids', [])

        total_ids = len(resolved_ids) + len(unresolved_ids) + len(empty_patch_ids)

        if total_ids == 0:
            # No evaluations yet, return strategy to run first evaluation
            return "initial_evaluation"

        # Calculate empty patch ratio
        empty_ratio = len(empty_patch_ids) / total_ids if total_ids > 0 else 0

        # Probabilistic strategy selection
        rand = random.random()

        # 25% chance: Focus on empty patches if they're significant
        if rand < 0.25 and empty_ratio >= 0.10:
            return "solve_empty_patches"

        # 25% chance: Improve stochasticity/consistency
        elif rand < 0.50:
            return "solve_stochasticity"

        # 25% chance: Address context length if it's an issue
        elif rand < 0.75:
            # Check if any tasks exceeded context length
            context_issues = parent_metadata.get('context_length_errors', [])
            if context_issues:
                return "solve_contextlength"

        # Default: Select random unresolved task
        if unresolved_ids:
            return random.choice(unresolved_ids)

        # Fallback: Select from all tasks
        all_ids = resolved_ids + unresolved_ids + empty_patch_ids
        if all_ids:
            return random.choice(all_ids)

        return "initial_evaluation"

    async def _run_diagnosis(
        self,
        parent_node: TreeNode,
        parent_metadata: Dict[str, Any],
        entry: str,
        output_dir: str
    ) -> Optional[str]:
        """
        Run diagnostic analysis to generate problem statement

        Args:
            parent_node: Parent node being diagnosed
            parent_metadata: Parent performance metadata
            entry: Selected diagnosis strategy or task ID
            output_dir: Directory to save diagnosis results

        Returns:
            Problem statement string or None on failure
        """
        from python.tools.diagnostic_tool import Diagnostic

        # Map entry to diagnostic strategy
        strategy = self._entry_to_strategy(entry)

        diagnostic = Diagnostic(
            agent=self.agent,
            name="diagnostic_analysis",
            method=None,
            args={
                'strategy': strategy,
                'log_file': '',  # Could pass log file path if available
                'problem_statement': entry if entry not in ['solve_empty_patches', 'solve_stochasticity', 'solve_contextlength'] else f"Strategy: {entry}",
                'generated_patch': parent_metadata.get('last_patch', ''),
                'test_patch': '',
                'test_results': parent_metadata.get('test_results', '')
            },
            message="",
            loop_data=None
        )

        try:
            response = await diagnostic.execute()

            # Extract problem statement from diagnostic response
            # The response should contain improvement suggestions in JSON format
            if response.message:
                # Save diagnostic results
                diag_path = os.path.join(output_dir, 'diagnosis.json')
                with open(diag_path, 'w') as f:
                    json.dump({
                        'strategy': entry,
                        'diagnostic_strategy': strategy,
                        'diagnosis': response.message
                    }, f, indent=2)

                # Parse JSON response to get problem_description field
                try:
                    diagnosis_data = json.loads(response.message)
                    if 'problem_description' in diagnosis_data:
                        problem_statement = diagnosis_data['problem_description']
                    else:
                        # Fallback: Use implementation_suggestion
                        problem_statement = f"""Problem Diagnosis for Agent Improvement

Strategy: {entry}
Diagnostic Strategy: {strategy}

Implementation Suggestion:
{diagnosis_data.get('implementation_suggestion', 'No specific suggestion provided')}

Improvement Proposal:
{diagnosis_data.get('improvement_proposal', 'No proposal provided')}

Please implement improvements to address the identified issues."""
                except json.JSONDecodeError:
                    # Fallback if response is not JSON
                    problem_statement = f"""Problem Diagnosis for Agent Improvement

Strategy: {entry}
Diagnostic Strategy: {strategy}

{response.message}

Please implement improvements to address the identified issues."""

                return problem_statement

        except Exception as e:
            self.agent.context.log.log(
                type="hgm",
                heading="Diagnosis",
                content=f"Diagnostic analysis failed: {str(e)}"
            )

        return None

    def _entry_to_strategy(self, entry: str) -> str:
        """Convert choose_entry() result to diagnostic strategy"""
        if entry == "solve_empty_patches":
            return "empty_patch"
        elif entry == "solve_stochasticity":
            return "stochasticity"
        elif entry == "solve_contextlength":
            return "contextlength"
        else:
            # Task-specific entry uses general SWE analysis
            return "swe"

    def _get_metadata_path(self, commit_id: str) -> str:
        """Get metadata file path for a commit"""
        return os.path.join(self.output_dir, f"{commit_id}_metadata.json")

    def save_node_metadata(self, node: TreeNode, metadata: Dict[str, Any]):
        """Save metadata for a node"""
        metadata_path = self._get_metadata_path(node.commit_id)

        # Merge with existing metadata if present
        if os.path.exists(metadata_path):
            with open(metadata_path, 'r') as f:
                existing = json.load(f)
            existing.update(metadata)
            metadata = existing

        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)

    def load_node_metadata(self, node: TreeNode) -> Optional[Dict[str, Any]]:
        """Load metadata for a node"""
        metadata_path = self._get_metadata_path(node.commit_id)

        if not os.path.exists(metadata_path):
            return None

        with open(metadata_path, 'r') as f:
            return json.load(f)
