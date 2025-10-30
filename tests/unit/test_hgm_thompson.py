# tests/unit/test_hgm_thompson.py
import pytest
import numpy as np
from python.helpers.hgm_thompson import thompson_sample

def test_thompson_sample_basic():
    """Verify Thompson Sampling selection logic"""
    # Create evaluation data for 3 nodes
    evaluations = [
        [1, 1, 1, 0, 1],  # Node 0: 80% success (4/5)
        [0, 0, 1, 0],     # Node 1: 25% success (1/4)
        [1, 1, 1, 1, 1]   # Node 2: 100% success (5/5)
    ]

    # Sample many times and check distribution
    samples = []
    for _ in range(1000):
        selected = thompson_sample(
            evaluations=evaluations,
            alpha=0.5,
            beta=1.0,
            cool_down=False,
            n_task_evals=0,
            max_task_evals=100
        )
        samples.append(selected)

    # Node 2 (100% success) should be selected most often
    # Node 0 (80% success) should be selected second most
    # Node 1 (25% success) should be selected least
    counts = [samples.count(i) for i in range(3)]

    assert counts[2] > counts[0] > counts[1]
    # Node 2 should get at least 40% of selections
    assert counts[2] / len(samples) > 0.4

def test_thompson_sample_cooling():
    """Verify cooling reduces exploration over time"""
    evaluations = [
        [1, 1, 1, 1],     # Node 0: 100% success
        [1, 0, 1, 0]      # Node 1: 50% success (more competitive)
    ]

    # Early in run (more exploration)
    early_samples = []
    for _ in range(200):
        selected = thompson_sample(
            evaluations=evaluations,
            alpha=0.5,
            beta=1.0,
            cool_down=True,
            n_task_evals=10,
            max_task_evals=1000
        )
        early_samples.append(selected)

    # Late in run (cooling applied, more exploitation)
    late_samples = []
    for _ in range(200):
        selected = thompson_sample(
            evaluations=evaluations,
            alpha=0.5,
            beta=1.0,
            cool_down=True,
            n_task_evals=900,
            max_task_evals=1000
        )
        late_samples.append(selected)

    # Node 0 (better) should be selected more often in late samples
    early_node0_rate = early_samples.count(0) / len(early_samples)
    late_node0_rate = late_samples.count(0) / len(late_samples)

    # Late samples should favor the best node more strongly
    assert late_node0_rate > early_node0_rate

def test_thompson_sample_empty_evals():
    """Verify handling of nodes with no evaluations"""
    evaluations = [
        [1, 0, 1],  # Node 0: has evals
        [],         # Node 1: no evals
        [1, 1]      # Node 2: has evals
    ]

    # Should still work without crashing
    selected = thompson_sample(
        evaluations=evaluations,
        alpha=0.5,
        beta=1.0,
        cool_down=False,
        n_task_evals=0,
        max_task_evals=100
    )

    assert 0 <= selected < 3

def test_thompson_sample_deterministic_at_max():
    """Verify that cooling makes selection more deterministic at max evals"""
    evaluations = [
        [1, 1, 1, 1, 1],  # Node 0: perfect
        [0, 0, 0]         # Node 1: terrible
    ]

    # At max_task_evals, cooling should strongly favor best node
    samples = []
    for _ in range(50):
        selected = thompson_sample(
            evaluations=evaluations,
            alpha=0.5,
            beta=1.0,
            cool_down=True,
            n_task_evals=100,
            max_task_evals=100
        )
        samples.append(selected)

    # Node 0 should dominate selections
    node0_rate = samples.count(0) / len(samples)
    assert node0_rate > 0.7  # Should be mostly exploitation

def test_thompson_sample_empty_list():
    """Verify handling of empty evaluation list"""
    evaluations = []

    selected = thompson_sample(
        evaluations=evaluations,
        alpha=0.5,
        beta=1.0,
        cool_down=False,
        n_task_evals=0,
        max_task_evals=100
    )

    # Should return 0 as default
    assert selected == 0
