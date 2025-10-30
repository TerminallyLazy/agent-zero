# python/helpers/hgm_task_manager.py
"""
HGM Task Management System

Provides centralized task pool management with:
- Task metadata and categorization
- Multiple selection strategies (random, priority, adaptive, diversity)
- Result caching across nodes
- Performance tracking and analytics
"""

import json
import random
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Set, Tuple, Any
from enum import Enum
from pathlib import Path


class TaskSelectionStrategy(Enum):
    """Task selection strategies for evaluation"""
    RANDOM = "random"  # Random selection from available tasks
    HARDEST_FIRST = "hardest_first"  # Prioritize tasks with lowest success rate
    EASIEST_FIRST = "easiest_first"  # Prioritize tasks with highest success rate
    ADAPTIVE = "adaptive"  # Focus on tasks where current node is weak
    DIVERSITY = "diversity"  # Ensure broad coverage across categories
    UNRESOLVED_ONLY = "unresolved_only"  # Only select previously failed tasks


@dataclass
class TaskMetadata:
    """Metadata for a single task"""
    task_id: str
    category: str = "general"
    difficulty: float = 0.5  # 0.0 (easy) to 1.0 (hard)
    tags: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)  # Task IDs that should be solved first

    # Performance statistics (updated as nodes evaluate this task)
    total_attempts: int = 0
    total_successes: int = 0
    success_rate: float = 0.0
    avg_execution_time: float = 0.0

    def update_statistics(self, success: bool, execution_time: float = 0.0):
        """Update statistics after task evaluation"""
        self.total_attempts += 1
        if success:
            self.total_successes += 1
        self.success_rate = self.total_successes / self.total_attempts if self.total_attempts > 0 else 0.0

        # Update rolling average execution time
        if execution_time > 0:
            if self.avg_execution_time == 0:
                self.avg_execution_time = execution_time
            else:
                self.avg_execution_time = (self.avg_execution_time * 0.9) + (execution_time * 0.1)


@dataclass
class TaskResult:
    """Result of a task evaluation"""
    task_id: str
    node_id: int
    commit_id: str
    success: bool
    execution_time: float = 0.0
    timestamp: float = 0.0
    error_message: Optional[str] = None


class TaskPool:
    """
    Manages the pool of evaluation tasks with metadata and statistics
    """

    def __init__(self, task_ids: List[str], metadata_file: Optional[str] = None):
        """
        Initialize task pool

        Args:
            task_ids: List of task IDs available for evaluation
            metadata_file: Optional path to load/save task metadata
        """
        self.metadata_file = metadata_file
        self.tasks: Dict[str, TaskMetadata] = {}

        # Initialize tasks
        for task_id in task_ids:
            self.tasks[task_id] = TaskMetadata(task_id=task_id)

        # Load metadata if file exists
        if metadata_file and Path(metadata_file).exists():
            self.load_metadata()

    def add_task(self, task_id: str, category: str = "general", difficulty: float = 0.5, tags: List[str] = None):
        """Add a new task to the pool"""
        self.tasks[task_id] = TaskMetadata(
            task_id=task_id,
            category=category,
            difficulty=difficulty,
            tags=tags or []
        )

    def update_task_result(self, result: TaskResult):
        """Update task statistics based on evaluation result"""
        if result.task_id in self.tasks:
            self.tasks[result.task_id].update_statistics(
                success=result.success,
                execution_time=result.execution_time
            )

            # Save updated metadata
            if self.metadata_file:
                self.save_metadata()

    def get_task_metadata(self, task_id: str) -> Optional[TaskMetadata]:
        """Get metadata for a specific task"""
        return self.tasks.get(task_id)

    def get_tasks_by_category(self, category: str) -> List[str]:
        """Get all task IDs in a category"""
        return [tid for tid, meta in self.tasks.items() if meta.category == category]

    def get_tasks_by_difficulty(self, min_difficulty: float, max_difficulty: float) -> List[str]:
        """Get tasks within a difficulty range"""
        return [
            tid for tid, meta in self.tasks.items()
            if min_difficulty <= meta.difficulty <= max_difficulty
        ]

    def get_statistics(self) -> Dict[str, Any]:
        """Get overall pool statistics"""
        if not self.tasks:
            return {
                'total_tasks': 0,
                'total_attempts': 0,
                'overall_success_rate': 0.0
            }

        total_attempts = sum(t.total_attempts for t in self.tasks.values())
        total_successes = sum(t.total_successes for t in self.tasks.values())

        # Category breakdown
        categories = {}
        for task_id, meta in self.tasks.items():
            if meta.category not in categories:
                categories[meta.category] = {
                    'count': 0,
                    'attempts': 0,
                    'successes': 0
                }
            categories[meta.category]['count'] += 1
            categories[meta.category]['attempts'] += meta.total_attempts
            categories[meta.category]['successes'] += meta.total_successes

        # Calculate category success rates
        for cat_stats in categories.values():
            if cat_stats['attempts'] > 0:
                cat_stats['success_rate'] = cat_stats['successes'] / cat_stats['attempts']
            else:
                cat_stats['success_rate'] = 0.0

        return {
            'total_tasks': len(self.tasks),
            'total_attempts': total_attempts,
            'total_successes': total_successes,
            'overall_success_rate': total_successes / total_attempts if total_attempts > 0 else 0.0,
            'categories': categories,
            'avg_execution_time': sum(t.avg_execution_time for t in self.tasks.values()) / len(self.tasks)
        }

    def save_metadata(self):
        """Save task metadata to file"""
        if not self.metadata_file:
            return

        data = {
            task_id: asdict(meta)
            for task_id, meta in self.tasks.items()
        }

        with open(self.metadata_file, 'w') as f:
            json.dump(data, f, indent=2)

    def load_metadata(self):
        """Load task metadata from file"""
        if not self.metadata_file or not Path(self.metadata_file).exists():
            return

        # Check if file is non-empty
        if Path(self.metadata_file).stat().st_size == 0:
            return

        with open(self.metadata_file, 'r') as f:
            data = json.load(f)

        for task_id, meta_dict in data.items():
            self.tasks[task_id] = TaskMetadata(**meta_dict)


class TaskManager:
    """
    High-level task management with result caching and selection strategies
    """

    def __init__(
        self,
        task_pool: TaskPool,
        cache_file: Optional[str] = None
    ):
        """
        Initialize task manager

        Args:
            task_pool: TaskPool instance
            cache_file: Optional path to result cache file
        """
        self.task_pool = task_pool
        self.cache_file = cache_file

        # Result cache: {node_id: {task_id: TaskResult}}
        self.result_cache: Dict[int, Dict[str, TaskResult]] = {}

        # Load cache if exists
        if cache_file and Path(cache_file).exists():
            self.load_cache()

    def cache_result(self, result: TaskResult):
        """Cache a task result"""
        if result.node_id not in self.result_cache:
            self.result_cache[result.node_id] = {}

        self.result_cache[result.node_id][result.task_id] = result

        # Update task pool statistics
        self.task_pool.update_task_result(result)

        # Save cache
        if self.cache_file:
            self.save_cache()

    def get_cached_result(self, node_id: int, task_id: str) -> Optional[TaskResult]:
        """Get cached result for node and task"""
        return self.result_cache.get(node_id, {}).get(task_id)

    def get_node_results(self, node_id: int) -> Dict[str, TaskResult]:
        """Get all cached results for a node"""
        return self.result_cache.get(node_id, {})

    def get_evaluated_tasks(self, node_id: int) -> Set[str]:
        """Get set of task IDs already evaluated for a node"""
        return set(self.result_cache.get(node_id, {}).keys())

    def get_available_tasks(self, node_id: int) -> List[str]:
        """Get task IDs not yet evaluated for a node"""
        evaluated = self.get_evaluated_tasks(node_id)
        return [tid for tid in self.task_pool.tasks.keys() if tid not in evaluated]

    def select_tasks(
        self,
        node_id: int,
        num_tasks: int,
        strategy: TaskSelectionStrategy = TaskSelectionStrategy.RANDOM,
        node_performance: Optional[Dict[str, float]] = None
    ) -> List[str]:
        """
        Select tasks for evaluation using specified strategy

        Args:
            node_id: Node ID to select tasks for
            num_tasks: Number of tasks to select
            strategy: Selection strategy
            node_performance: Optional dict of category -> success_rate for adaptive strategy

        Returns:
            List of selected task IDs
        """
        available = self.get_available_tasks(node_id)

        if not available:
            return []

        if len(available) <= num_tasks:
            return available

        # Apply selection strategy
        if strategy == TaskSelectionStrategy.RANDOM:
            return random.sample(available, num_tasks)

        elif strategy == TaskSelectionStrategy.HARDEST_FIRST:
            # Sort by success rate (lowest first)
            sorted_tasks = sorted(
                available,
                key=lambda tid: self.task_pool.tasks[tid].success_rate
            )
            return sorted_tasks[:num_tasks]

        elif strategy == TaskSelectionStrategy.EASIEST_FIRST:
            # Sort by success rate (highest first)
            sorted_tasks = sorted(
                available,
                key=lambda tid: self.task_pool.tasks[tid].success_rate,
                reverse=True
            )
            return sorted_tasks[:num_tasks]

        elif strategy == TaskSelectionStrategy.ADAPTIVE:
            # Focus on categories where this node performs poorly
            if not node_performance:
                return random.sample(available, num_tasks)

            # Score tasks based on node's weakness in their category
            task_scores = []
            for tid in available:
                task = self.task_pool.tasks[tid]
                category_perf = node_performance.get(task.category, 0.5)
                # Lower performance = higher priority
                score = (1.0 - category_perf) * (1.0 + task.difficulty)
                task_scores.append((tid, score))

            # Sort by score (highest first)
            task_scores.sort(key=lambda x: x[1], reverse=True)
            return [tid for tid, _ in task_scores[:num_tasks]]

        elif strategy == TaskSelectionStrategy.DIVERSITY:
            # Ensure coverage across categories
            selected = []
            categories_used = set()

            # First pass: one task per category
            for tid in available:
                task = self.task_pool.tasks[tid]
                if task.category not in categories_used:
                    selected.append(tid)
                    categories_used.add(task.category)
                    if len(selected) >= num_tasks:
                        break

            # Second pass: fill remaining slots randomly
            if len(selected) < num_tasks:
                remaining = [t for t in available if t not in selected]
                additional = random.sample(remaining, min(num_tasks - len(selected), len(remaining)))
                selected.extend(additional)

            return selected

        elif strategy == TaskSelectionStrategy.UNRESOLVED_ONLY:
            # Only select tasks that failed in previous evaluations
            failed_tasks = []
            for tid in available:
                # Check if task has been attempted by other nodes and failed
                task_meta = self.task_pool.tasks[tid]
                if task_meta.total_attempts > 0 and task_meta.success_rate < 1.0:
                    failed_tasks.append(tid)

            if not failed_tasks:
                # If no failures, fall back to random
                return random.sample(available, num_tasks)

            return random.sample(failed_tasks, min(num_tasks, len(failed_tasks)))

        # Default: random
        return random.sample(available, num_tasks)

    def get_node_statistics(self, node_id: int) -> Dict[str, Any]:
        """Get performance statistics for a specific node"""
        results = self.get_node_results(node_id)

        if not results:
            return {
                'total_evaluated': 0,
                'total_successes': 0,
                'success_rate': 0.0
            }

        total_successes = sum(1 for r in results.values() if r.success)

        # Category breakdown
        category_stats = {}
        for result in results.values():
            task = self.task_pool.tasks[result.task_id]
            if task.category not in category_stats:
                category_stats[task.category] = {'total': 0, 'successes': 0}

            category_stats[task.category]['total'] += 1
            if result.success:
                category_stats[task.category]['successes'] += 1

        # Calculate category success rates
        for cat_stats in category_stats.values():
            cat_stats['success_rate'] = cat_stats['successes'] / cat_stats['total'] if cat_stats['total'] > 0 else 0.0

        return {
            'total_evaluated': len(results),
            'total_successes': total_successes,
            'success_rate': total_successes / len(results),
            'categories': category_stats,
            'avg_execution_time': sum(r.execution_time for r in results.values()) / len(results)
        }

    def save_cache(self):
        """Save result cache to file"""
        if not self.cache_file:
            return

        # Convert to serializable format
        cache_data = {}
        for node_id, results in self.result_cache.items():
            cache_data[str(node_id)] = {
                task_id: asdict(result)
                for task_id, result in results.items()
            }

        with open(self.cache_file, 'w') as f:
            json.dump(cache_data, f, indent=2)

    def load_cache(self):
        """Load result cache from file"""
        if not self.cache_file or not Path(self.cache_file).exists():
            return

        # Check if file is non-empty
        if Path(self.cache_file).stat().st_size == 0:
            return

        with open(self.cache_file, 'r') as f:
            cache_data = json.load(f)

        # Convert back to TaskResult objects
        for node_id_str, results in cache_data.items():
            node_id = int(node_id_str)
            self.result_cache[node_id] = {}

            for task_id, result_dict in results.items():
                self.result_cache[node_id][task_id] = TaskResult(**result_dict)
