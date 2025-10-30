# python/helpers/hgm_thompson.py
import numpy as np
from typing import List

def thompson_sample(
    evaluations: List[List[int]],
    alpha: float,
    beta: float,
    cool_down: bool,
    n_task_evals: int,
    max_task_evals: int
) -> int:
    """
    Select a node using Thompson Sampling with Beta distributions.

    Thompson Sampling is a Bayesian approach for balancing exploration
    and exploitation. Each node's success rate is modeled as a Beta
    distribution, and we sample from each to make decisions.

    Args:
        evaluations: List of evaluation results for each node (1=success, 0=failure)
        alpha: Base alpha parameter for Beta distribution (controls prior)
        beta: Base beta parameter for Beta distribution (controls prior)
        cool_down: Whether to apply cooling (reduce exploration over time)
        n_task_evals: Current number of task evaluations
        max_task_evals: Maximum number of task evaluations

    Returns:
        Index of selected node

    Reference:
        Thompson, W. R. (1933). On the likelihood that one unknown
        probability exceeds another in view of the evidence of two samples.
        Biometrika, 25(3/4), 285-294.
    """
    if not evaluations:
        return 0

    # Calculate cooling factor if enabled
    cooling_factor = 1.0
    if cool_down and max_task_evals > 0:
        # Progressively reduce exploration as we approach max_task_evals
        progress = n_task_evals / max_task_evals
        # Exponential cooling: exploration reduces faster near the end
        cooling_factor = np.exp(-3 * progress)  # At 100%, factor ≈ 0.05

    # Sample from Beta distribution for each node
    samples = []
    for evals in evaluations:
        if not evals:
            # No evaluations yet - use prior
            successes = 0
            failures = 0
        else:
            successes = sum(evals)
            failures = len(evals) - successes

        # Beta distribution parameters
        # Higher alpha/beta = stronger prior (less exploration)
        alpha_param = alpha + successes
        beta_param = beta + failures

        # Apply cooling to make sampling more deterministic
        if cooling_factor < 1.0:
            # Scale parameters up to reduce variance
            scale = 1.0 / cooling_factor
            alpha_param *= scale
            beta_param *= scale

        # Sample from Beta(alpha_param, beta_param)
        sample = np.random.beta(alpha_param, beta_param)
        samples.append(sample)

    # Select node with highest sample
    selected_idx = int(np.argmax(samples))
    return selected_idx

def calculate_ucb(
    evaluations: List[List[int]],
    exploration_constant: float = 2.0
) -> int:
    """
    Upper Confidence Bound (UCB) selection as an alternative to Thompson Sampling.

    UCB1 algorithm balances exploitation (mean reward) with exploration
    (uncertainty about estimates).

    Args:
        evaluations: List of evaluation results for each node
        exploration_constant: Controls exploration vs exploitation trade-off

    Returns:
        Index of selected node
    """
    if not evaluations:
        return 0

    total_evals = sum(len(evals) for evals in evaluations)
    if total_evals == 0:
        # No evaluations yet - select randomly
        return np.random.randint(0, len(evaluations))

    ucb_scores = []
    for evals in evaluations:
        if not evals:
            # Unvisited nodes get infinite score (explore first)
            ucb_scores.append(float('inf'))
        else:
            mean = sum(evals) / len(evals)
            n = len(evals)
            exploration = exploration_constant * np.sqrt(np.log(total_evals) / n)
            ucb = mean + exploration
            ucb_scores.append(ucb)

    return int(np.argmax(ucb_scores))
