from pathlib import Path

PLUGIN_NAME = "dspy_rlm"

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = PLUGIN_ROOT / "state"

# Durable state is authoritative. JSON files are compatibility/read-cache artifacts only.
STORE_FILE = STATE_DIR / "dspy_rlm_runtime.sqlite"
TRACE_FILE = STATE_DIR / "traces.jsonl"
STATE_FILE = STATE_DIR / "runtime_state.json"
COMPILED_STATE_FILE = STATE_DIR / "compiled_guidance.json"
