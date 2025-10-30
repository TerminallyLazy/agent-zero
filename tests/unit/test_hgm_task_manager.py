# tests/unit/test_hgm_task_manager.py
import pytest
import tempfile
import json
import os
from python.helpers.hgm_task_manager import (
    TaskPool,
    TaskManager,
    TaskMetadata,
    TaskResult,
    TaskSelectionStrategy
)


def test_task_metadata_creation():
    """Test creating task metadata"""
    task = TaskMetadata(
        task_id="task_001",
        category="testing",
        difficulty=0.7,
        tags=["unit", "integration"]
    )

    assert task.task_id == "task_001"
    assert task.category == "testing"
    assert task.difficulty == 0.7
    assert task.tags == ["unit", "integration"]
    assert task.total_attempts == 0
    assert task.success_rate == 0.0


def test_task_metadata_update_statistics():
    """Test updating task statistics"""
    task = TaskMetadata(task_id="task_001")

    # Add successful attempt
    task.update_statistics(success=True, execution_time=5.0)
    assert task.total_attempts == 1
    assert task.total_successes == 1
    assert task.success_rate == 1.0
    assert task.avg_execution_time == 5.0

    # Add failed attempt
    task.update_statistics(success=False, execution_time=3.0)
    assert task.total_attempts == 2
    assert task.total_successes == 1
    assert task.success_rate == 0.5
    # Rolling average: (5.0 * 0.9) + (3.0 * 0.1) = 4.8
    assert abs(task.avg_execution_time - 4.8) < 0.01


def test_task_pool_initialization():
    """Test task pool initialization"""
    task_ids = ["task_001", "task_002", "task_003"]
    pool = TaskPool(task_ids)

    assert len(pool.tasks) == 3
    assert "task_001" in pool.tasks
    assert pool.tasks["task_001"].task_id == "task_001"
    assert pool.tasks["task_001"].category == "general"


def test_task_pool_add_task():
    """Test adding tasks to pool"""
    pool = TaskPool([])

    pool.add_task("task_001", category="testing", difficulty=0.8, tags=["hard"])

    assert "task_001" in pool.tasks
    assert pool.tasks["task_001"].category == "testing"
    assert pool.tasks["task_001"].difficulty == 0.8
    assert pool.tasks["task_001"].tags == ["hard"]


def test_task_pool_update_result():
    """Test updating task with result"""
    pool = TaskPool(["task_001"])

    result = TaskResult(
        task_id="task_001",
        node_id=0,
        commit_id="abc123",
        success=True,
        execution_time=5.0
    )

    pool.update_task_result(result)

    task = pool.tasks["task_001"]
    assert task.total_attempts == 1
    assert task.total_successes == 1
    assert task.success_rate == 1.0


def test_task_pool_get_by_category():
    """Test getting tasks by category"""
    pool = TaskPool([])

    pool.add_task("task_001", category="unit")
    pool.add_task("task_002", category="integration")
    pool.add_task("task_003", category="unit")

    unit_tasks = pool.get_tasks_by_category("unit")
    assert len(unit_tasks) == 2
    assert "task_001" in unit_tasks
    assert "task_003" in unit_tasks


def test_task_pool_get_by_difficulty():
    """Test getting tasks by difficulty range"""
    pool = TaskPool([])

    pool.add_task("easy", difficulty=0.2)
    pool.add_task("medium", difficulty=0.5)
    pool.add_task("hard", difficulty=0.9)

    medium_tasks = pool.get_tasks_by_difficulty(0.4, 0.6)
    assert len(medium_tasks) == 1
    assert "medium" in medium_tasks


def test_task_pool_statistics():
    """Test pool statistics calculation"""
    pool = TaskPool(["task_001", "task_002"])

    # Add some results
    pool.update_task_result(TaskResult("task_001", 0, "abc", True))
    pool.update_task_result(TaskResult("task_001", 1, "def", False))
    pool.update_task_result(TaskResult("task_002", 0, "abc", True))

    stats = pool.get_statistics()

    assert stats['total_tasks'] == 2
    assert stats['total_attempts'] == 3
    assert stats['total_successes'] == 2
    assert abs(stats['overall_success_rate'] - 0.667) < 0.01


def test_task_pool_save_and_load():
    """Test saving and loading task metadata"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        metadata_file = f.name

    try:
        # Create pool and add tasks
        pool = TaskPool(["task_001"], metadata_file=metadata_file)
        pool.add_task("task_002", category="testing", difficulty=0.7)

        # Update with results
        pool.update_task_result(TaskResult("task_001", 0, "abc", True))

        # Save
        pool.save_metadata()

        # Load into new pool
        pool2 = TaskPool([], metadata_file=metadata_file)

        assert len(pool2.tasks) == 2
        assert pool2.tasks["task_001"].total_attempts == 1
        assert pool2.tasks["task_002"].difficulty == 0.7

    finally:
        os.unlink(metadata_file)


def test_task_manager_initialization():
    """Test task manager initialization"""
    pool = TaskPool(["task_001", "task_002"])
    manager = TaskManager(pool)

    assert manager.task_pool is pool
    assert len(manager.result_cache) == 0


def test_task_manager_cache_result():
    """Test caching task results"""
    pool = TaskPool(["task_001"])
    manager = TaskManager(pool)

    result = TaskResult(
        task_id="task_001",
        node_id=0,
        commit_id="abc123",
        success=True,
        execution_time=5.0
    )

    manager.cache_result(result)

    # Check cache
    cached = manager.get_cached_result(0, "task_001")
    assert cached is not None
    assert cached.success is True
    assert cached.execution_time == 5.0

    # Check task pool was updated
    assert pool.tasks["task_001"].total_attempts == 1


def test_task_manager_get_available_tasks():
    """Test getting available tasks for a node"""
    pool = TaskPool(["task_001", "task_002", "task_003"])
    manager = TaskManager(pool)

    # Cache result for task_001 on node 0
    manager.cache_result(TaskResult("task_001", 0, "abc", True))

    available = manager.get_available_tasks(0)
    assert len(available) == 2
    assert "task_001" not in available
    assert "task_002" in available
    assert "task_003" in available


def test_task_manager_select_random():
    """Test random task selection"""
    pool = TaskPool([f"task_{i:03d}" for i in range(10)])
    manager = TaskManager(pool)

    selected = manager.select_tasks(
        node_id=0,
        num_tasks=3,
        strategy=TaskSelectionStrategy.RANDOM
    )

    assert len(selected) == 3
    assert len(set(selected)) == 3  # All unique


def test_task_manager_select_hardest_first():
    """Test hardest-first task selection"""
    pool = TaskPool([])

    # Add tasks with different success rates - only add tasks that will be used
    pool.add_task("task_0")
    pool.add_task("task_1")
    pool.add_task("task_2")

    # Simulate different success rates
    pool.tasks["task_0"].total_attempts = 10
    pool.tasks["task_0"].total_successes = 9  # 90% success
    pool.tasks["task_0"].success_rate = 0.9

    pool.tasks["task_1"].total_attempts = 10
    pool.tasks["task_1"].total_successes = 3  # 30% success
    pool.tasks["task_1"].success_rate = 0.3

    pool.tasks["task_2"].total_attempts = 10
    pool.tasks["task_2"].total_successes = 7  # 70% success
    pool.tasks["task_2"].success_rate = 0.7

    manager = TaskManager(pool)

    selected = manager.select_tasks(
        node_id=0,
        num_tasks=2,
        strategy=TaskSelectionStrategy.HARDEST_FIRST
    )

    # Should select task_1 (30%) first and task_2 (70%) second
    assert selected[0] == "task_1"  # Lowest success rate
    assert selected[1] == "task_2"  # Second lowest


def test_task_manager_select_easiest_first():
    """Test easiest-first task selection"""
    pool = TaskPool([])

    # Add tasks with different success rates
    pool.add_task("easy", difficulty=0.2)
    pool.tasks["easy"].total_attempts = 10
    pool.tasks["easy"].total_successes = 9
    pool.tasks["easy"].success_rate = 0.9

    pool.add_task("hard", difficulty=0.8)
    pool.tasks["hard"].total_attempts = 10
    pool.tasks["hard"].total_successes = 2
    pool.tasks["hard"].success_rate = 0.2

    manager = TaskManager(pool)

    selected = manager.select_tasks(
        node_id=0,
        num_tasks=1,
        strategy=TaskSelectionStrategy.EASIEST_FIRST
    )

    assert selected[0] == "easy"


def test_task_manager_select_adaptive():
    """Test adaptive task selection based on node performance"""
    pool = TaskPool([])

    # Add tasks in different categories
    pool.add_task("math_001", category="math", difficulty=0.5)
    pool.add_task("string_001", category="string", difficulty=0.5)
    pool.add_task("array_001", category="array", difficulty=0.5)

    manager = TaskManager(pool)

    # Node performs poorly on math
    node_performance = {
        "math": 0.2,
        "string": 0.8,
        "array": 0.7
    }

    selected = manager.select_tasks(
        node_id=0,
        num_tasks=1,
        strategy=TaskSelectionStrategy.ADAPTIVE,
        node_performance=node_performance
    )

    # Should prioritize math tasks
    assert selected[0] == "math_001"


def test_task_manager_select_diversity():
    """Test diversity-based task selection"""
    pool = TaskPool([])

    # Add tasks in different categories
    for i in range(3):
        pool.add_task(f"math_{i}", category="math")
        pool.add_task(f"string_{i}", category="string")

    manager = TaskManager(pool)

    selected = manager.select_tasks(
        node_id=0,
        num_tasks=3,
        strategy=TaskSelectionStrategy.DIVERSITY
    )

    # Should have at least 2 different categories
    selected_categories = set()
    for task_id in selected:
        selected_categories.add(pool.tasks[task_id].category)

    assert len(selected_categories) >= 2


def test_task_manager_select_unresolved_only():
    """Test unresolved-only task selection"""
    pool = TaskPool(["task_001", "task_002", "task_003"])

    # Mark task_001 as failed by other nodes
    pool.tasks["task_001"].total_attempts = 5
    pool.tasks["task_001"].total_successes = 1
    pool.tasks["task_001"].success_rate = 0.2

    # Mark task_002 as successful
    pool.tasks["task_002"].total_attempts = 5
    pool.tasks["task_002"].total_successes = 5
    pool.tasks["task_002"].success_rate = 1.0

    # task_003 has no attempts
    manager = TaskManager(pool)

    selected = manager.select_tasks(
        node_id=0,
        num_tasks=2,
        strategy=TaskSelectionStrategy.UNRESOLVED_ONLY
    )

    # Should prefer task_001 (has failures)
    assert "task_001" in selected


def test_task_manager_node_statistics():
    """Test getting statistics for a node"""
    pool = TaskPool([])
    pool.add_task("task_001", category="math")
    pool.add_task("task_002", category="string")

    manager = TaskManager(pool)

    # Add results for node 0
    manager.cache_result(TaskResult("task_001", 0, "abc", True, execution_time=5.0))
    manager.cache_result(TaskResult("task_002", 0, "abc", False, execution_time=3.0))

    stats = manager.get_node_statistics(0)

    assert stats['total_evaluated'] == 2
    assert stats['total_successes'] == 1
    assert stats['success_rate'] == 0.5
    assert stats['avg_execution_time'] == 4.0

    # Check category breakdown
    assert 'math' in stats['categories']
    assert stats['categories']['math']['success_rate'] == 1.0


def test_task_manager_save_and_load_cache():
    """Test saving and loading result cache"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        cache_file = f.name

    try:
        pool = TaskPool(["task_001", "task_002"])
        manager = TaskManager(pool, cache_file=cache_file)

        # Add results
        manager.cache_result(TaskResult("task_001", 0, "abc", True, execution_time=5.0))
        manager.cache_result(TaskResult("task_002", 0, "abc", False, execution_time=3.0))

        # Save
        manager.save_cache()

        # Load into new manager
        manager2 = TaskManager(pool, cache_file=cache_file)

        assert len(manager2.result_cache[0]) == 2
        result = manager2.get_cached_result(0, "task_001")
        assert result.success is True
        assert result.execution_time == 5.0

    finally:
        os.unlink(cache_file)


def test_task_manager_cross_node_caching():
    """Test that results are cached per node"""
    pool = TaskPool(["task_001"])
    manager = TaskManager(pool)

    # Node 0 succeeds
    manager.cache_result(TaskResult("task_001", 0, "abc", True))

    # Node 1 fails
    manager.cache_result(TaskResult("task_001", 1, "def", False))

    # Check both are cached correctly
    result_0 = manager.get_cached_result(0, "task_001")
    result_1 = manager.get_cached_result(1, "task_001")

    assert result_0.success is True
    assert result_1.success is False

    # Task pool should aggregate both attempts
    assert pool.tasks["task_001"].total_attempts == 2
    assert pool.tasks["task_001"].total_successes == 1
    assert pool.tasks["task_001"].success_rate == 0.5


def test_task_manager_empty_available_tasks():
    """Test selection when no tasks available"""
    pool = TaskPool(["task_001"])
    manager = TaskManager(pool)

    # Cache the only task
    manager.cache_result(TaskResult("task_001", 0, "abc", True))

    selected = manager.select_tasks(0, num_tasks=5, strategy=TaskSelectionStrategy.RANDOM)

    assert len(selected) == 0


def test_task_result_creation():
    """Test creating task result"""
    result = TaskResult(
        task_id="task_001",
        node_id=0,
        commit_id="abc123",
        success=True,
        execution_time=5.5,
        timestamp=123456.0,
        error_message=None
    )

    assert result.task_id == "task_001"
    assert result.node_id == 0
    assert result.success is True
    assert result.execution_time == 5.5
    assert result.error_message is None
