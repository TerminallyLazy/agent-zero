from typing import Dict

class ProvenanceRecorder:
    def __init__(self):
        self.graph: Dict[str, Dict] = {}

    def record_delegation(self, parent_task: Dict, child_task: Dict):
        parent_id = parent_task["task_id"]
        child_id = child_task["task_id"]
        if parent_id not in self.graph:
            self.graph[parent_id] = {"children": [], "task": parent_task}
        self.graph[parent_id]["children"].append(child_id)
        self.graph[child_id] = {"children": [], "task": child_task, "parent": parent_id}

    def get_trace(self, task_id: str) -> Dict:
        return self.graph.get(task_id, {})

    def human_readable(self, task_id: str, depth: int = 0) -> str:
        node = self.graph.get(task_id)
        if not node:
            return f"{'  ' * depth}- Unknown task {task_id}\n"
        out = f"{'  ' * depth}- Task {task_id} state={node['task'].get('state')} goal={node['task'].get('goal')}\n"
        for child in node.get("children", []):
            out += self.human_readable(child, depth + 1)
        return out