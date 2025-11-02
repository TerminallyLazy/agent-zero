**HGM Self-Improvement Tool**

Huxley-Gödel Machine (HGM) self-improvement system for evolving agent capabilities through tree-based evolutionary search.

**Arguments:**
- `operation` (string, required): The HGM operation to perform
  - "initialize": Setup initial agent version and create root node
  - "expand": Create new agent variant from promising node
  - "evaluate": Evaluate agent on tasks
  - "run": Execute self-improvement loop (expand/evaluate cycles)
  - "status": Report current tree statistics
- `output_dir` (string, required for initialize/run): Directory for HGM outputs and state
- `git_dir` (string, required for expand/run): Repository directory path
- `base_commit` (string, required for initialize): Initial commit hash
- `total_tasks` (list, required for initialize/run): List of task IDs for evaluation
- `config` (dict or HGMConfig, optional): Configuration parameters
  - `max_task_evals`: Maximum task evaluations (default: 1000)
  - `max_workers`: Number of parallel workers (default: 4)
  - `alpha`: Expand/evaluate decision parameter (default: 0.5)
  - `beta`: Thompson Sampling parameter (default: 1.0)
- `iterations` (integer, for run): Number of expand/evaluate cycles (default: 10)
- `node_id` (integer, for expand/evaluate): Target node ID
- `num_tasks` (integer, for evaluate): Number of tasks to evaluate (default: 1)

**Operations:**

1. **initialize**: Setup HGM system
   - Creates root node from base commit
   - Initializes tree structure
   - Stores configuration

2. **expand**: Generate new agent variant
   - Selects promising node using Thompson Sampling
   - Creates improvement patch using diagnostic tools
   - Applies patch and commits new version
   - Returns new node ID

3. **evaluate**: Test agent performance
   - Evaluates agent on selected tasks
   - Updates node utility measures
   - Caches results

4. **run**: Automated self-improvement
   - Executes expand/evaluate cycles
   - Applies alpha decision rule (expand vs evaluate)
   - Reports progress after each iteration

5. **status**: Get current state
   - Reports tree statistics
   - Shows node count and evaluations
   - Displays configuration

**Workflow Example:**
```json
{
  "thoughts": [
    "I want to improve my agent using HGM",
    "First, initialize the system with fast preset"
  ],
  "tool_name": "hgm_self_improve_tool",
  "tool_args": {
    "operation": "initialize",
    "output_dir": "./hgm_output",
    "git_dir": "/path/to/agent/repo",
    "base_commit": "abc123",
    "total_tasks": ["task_001", "task_002", "task_003"],
    "config": {
      "max_task_evals": 100,
      "max_workers": 2,
      "alpha": 0.3
    }
  }
}
```

```json
{
  "thoughts": [
    "Now run the self-improvement loop",
    "Let it explore and evaluate for 20 iterations"
  ],
  "tool_name": "hgm_self_improve_tool",
  "tool_args": {
    "operation": "run",
    "iterations": 20,
    "git_dir": "/path/to/agent/repo",
    "total_tasks": ["task_001", "task_002", "task_003"]
  }
}
```

**Configuration Presets:**
- Fast: `HGMConfig.create_fast()` - 100 evals, 1 worker, alpha=0.3
- Default: `HGMConfig.create_default()` - 1000 evals, 4 workers, alpha=0.5
- Thorough: `HGMConfig.create_thorough()` - 5000 evals, 8 workers, alpha=0.7, pruning enabled

**Important Notes:**
- HGM maintains state in agent.data under keys starting with 'hgm_'
- Results are cached to avoid re-evaluation
- Use status operation to monitor progress
- The run operation is autonomous - it will continue until max_task_evals reached
- Each expand creates a new git commit representing an agent variant
