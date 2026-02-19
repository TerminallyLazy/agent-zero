# Prompt Stomper Plugin — Design Document

## Overview

Prompt Stomper is an Agent Zero plugin that detects and blocks prompt injection attacks — both direct (user-submitted jailbreaks) and indirect (malicious instructions hidden in documents, web pages, and tool outputs). It uses a fast, local pattern-matching and heuristic scoring engine with no external API dependencies.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Block mode | Hard block at High severity | LLM never sees injection payload |
| Scan scope | User messages + tool outputs | Covers both direct and indirect attacks |
| Detection engine | Pattern + heuristic (local) | Fast, zero latency, no token cost, no external deps |
| Canary tokens | Per-session random tokens in system prompt | Detects system prompt leakage in LLM output |
| Agent tool | `scan_content` tool | Agent can explicitly request safety scans |
| UI | Full dashboard modal (3 tabs) + toast notifications | Status/log, settings, pattern editor |
| Severity model | 4-tier (Safe/Low/Medium/High) | Adapted from Prompt Shields simplified model |

## Attack Categories

### Direct Attacks (User Prompt Injection)

| Category | Description |
|----------|-------------|
| `system_rule_change` | Attempts to override, ignore, or forget system instructions |
| `conversation_mockup` | Fake conversation turns embedded in a single message to confuse the model |
| `role_play_hijack` | Persona replacement attacks ("You are now DAN...") |
| `encoding_attack` | Base64, ROT13, URL encoding, hex escapes to hide instructions |

### Indirect Attacks (Document Injection)

| Category | Description |
|----------|-------------|
| `content_manipulation` | Instructions embedded in fetched documents to falsify or manipulate content |
| `data_exfiltration` | Hidden instructions to leak data to external URLs or emails |
| `privilege_escalation` | Attempts to gain unauthorized system access via embedded instructions |
| `availability_attack` | Instructions to make the agent unusable or produce garbage output |

## Severity Levels

| Level | Name | Score Range | Action |
|-------|------|-------------|--------|
| 0 | Safe | 0.0 - 0.2 | Pass through |
| 1 | Low | 0.2 - 0.5 | Log event, pass through |
| 2 | Medium | 0.5 - 0.8 | Log + warn in UI |
| 3 | High | 0.8 - 1.0 | Hard block + toast notification |

## Plugin File Structure

```
plugins/prompt_stomper/
├── extensions/
│   ├── python/
│   │   ├── user_message_ui/
│   │   │   └── _05_prompt_stomper.py          # Direct injection shield (earliest intercept)
│   │   ├── tool_execute_after/
│   │   │   └── _05_document_scanner.py        # Indirect injection shield (tool outputs)
│   │   ├── message_loop_prompts_after/
│   │   │   └── _05_history_scanner.py         # Context history scan
│   │   ├── system_prompt/
│   │   │   └── _05_stomper_instructions.py    # System prompt hardening + canary injection
│   │   └── response_stream_chunk/
│   │       └── _05_canary_monitor.py          # Canary token leak detection in LLM output
│   └── webui/
│       └── sidebar-quick-actions-main-start/
│           └── stomper-button.html             # Sidebar shield icon button
├── api/
│   ├── stomper_status.py                       # GET current status + scan stats
│   ├── stomper_settings.py                     # GET/POST plugin settings
│   ├── stomper_log.py                          # GET detection event log (paginated)
│   └── stomper_patterns.py                     # CRUD custom detection patterns
├── tools/
│   └── scan_content.py                         # Agent-invokable content scan tool
├── helpers/
│   ├── scanner.py                              # Core detection engine
│   ├── patterns.py                             # Pattern registry (built-in + custom)
│   └── stomper_log.py                          # Detection event storage and retrieval
├── prompts/
│   ├── stomper.system_hardening.md             # System prompt hardening fragment
│   └── tool.scan_content.md                    # Tool description for agent prompt
├── webui/
│   ├── stomper-dashboard.html                  # Main dashboard modal (3-tab layout)
│   ├── stomper-dashboard-store.js              # Dashboard state + polling
│   ├── stomper-settings.html                   # Settings panel component
│   ├── stomper-settings-store.js               # Settings read/write
│   ├── stomper-log.html                        # Real-time detection log viewer
│   ├── stomper-log-store.js                    # Log viewer state + auto-refresh
│   ├── stomper-pattern-editor.html             # Custom pattern editor
│   └── stomper-pattern-editor-store.js         # Pattern CRUD + live regex testing
└── data/
    ├── default_patterns.json                   # ~50 built-in detection patterns
    └── severity_levels.json                    # Severity tier threshold configuration
```

## Detection Engine Design (`helpers/scanner.py`)

### Scanner API

```python
@dataclass
class ScanResult:
    is_attack: bool              # True if any pattern matched above threshold
    severity: int                # 0-3 (Safe/Low/Medium/High)
    score: float                 # 0.0-1.0 composite score
    attack_type: str | None      # "direct" or "indirect" or None
    categories: list[str]        # matched category names
    matched_patterns: list[dict] # details: pattern name, regex, weight, match text
    text_snippet: str            # excerpt of the offending text (for logging)

class Scanner:
    def __init__(self, patterns: PatternRegistry, settings: dict):
        self.patterns = patterns
        self.settings = settings

    def scan_user_prompt(self, text: str) -> ScanResult:
        """Scan a user-submitted message for direct injection attacks."""
        ...

    def scan_document(self, text: str, source: str = "") -> ScanResult:
        """Scan third-party content for indirect injection attacks."""
        ...
```

### Detection Signals (how scoring works)

1. **Regex patterns** — Each pattern has a compiled regex, a weight (0.0-1.0), and a category. A match adds `weight` to the composite score.

2. **Structural heuristics** — Detect conversation-mockup structures (lines matching `User:`, `Assistant:`, `System:` turn patterns), encoded blocks (base64 strings > 20 chars, hex sequences), role-assignment language ("you are now", "pretend to be", "act as").

3. **Keyword density** — Score based on density of injection-related keywords ("ignore", "disregard", "pretend", "jailbreak", "bypass", "override", "DAN", "system prompt") relative to total message length. High density in short messages scores higher.

4. **Score aggregation** — Weighted sum of all signal scores, clamped to [0.0, 1.0]. Severity tier derived from configurable thresholds.

### Pattern Registry (`helpers/patterns.py`)

- Loads built-in patterns from `data/default_patterns.json` at startup
- Loads custom patterns from plugin settings storage
- Patterns are compiled once and cached
- Each pattern: `{ name, category, regex, weight, enabled, builtin }`
- Built-in patterns can be toggled but not deleted
- Custom patterns support full CRUD

## Extension Integration

### Data Flow

```
User message
  → user_message_ui extension
  → Scanner.scan_user_prompt()
  ├─ High severity → BLOCK: replace message with notice, toast notification, log event
  ├─ Medium severity → WARN: log warning to UI process group, pass message
  └─ Safe/Low → pass through normally

Agent calls tool (web search, file read, etc.)
  → tool returns result
  → tool_execute_after extension
  → Scanner.scan_document()
  ├─ High severity → SANITIZE: replace tool output with warning, log event
  ├─ Medium severity → WARN: inject warning alongside tool result
  └─ Safe/Low → pass through normally

System prompt assembled
  → system_prompt extension
  → inject hardening instructions + canary token into system prompt

LLM generates response
  → response_stream_chunk extension
  → canary_monitor checks each chunk for canary token
  ├─ Token found → TRUNCATE response, emit warning, log event
  └─ Not found → pass through
```

### Extension: `user_message_ui/_05_prompt_stomper.py`

Earliest interception point. Fires in the API layer before the message reaches the agent. Receives a mutable `data` dict with `data["message"]`. On High severity detection, replaces the message with `"[MESSAGE BLOCKED: prompt injection detected]"`.

### Extension: `tool_execute_after/_05_document_scanner.py`

Fires after every tool execution. Receives `kwargs` with the tool response. Scans the response text for indirect injection. On High severity, replaces the tool output with a sanitized version.

### Extension: `system_prompt/_05_stomper_instructions.py`

Injects a hardening fragment from `prompts/stomper.system_hardening.md` into the system prompt. Generates a per-session canary token (random alphanumeric string) and embeds it in the system prompt with instructions to never output it.

### Extension: `response_stream_chunk/_05_canary_monitor.py`

Monitors each chunk of LLM output. Maintains a rolling buffer of recent chunks. If the canary token appears in the buffer, the system prompt was leaked. Emits an error log and attempts to truncate the response.

### Extension: `message_loop_prompts_after/_05_history_scanner.py`

Scans any new entries in the conversation history for injection patterns. This catches content that was added to history by other extensions or through non-standard paths.

## Agent Tool: `scan_content`

Gives the agent an explicit tool to scan arbitrary text content for injection attacks.

```python
class ScanContent(Tool):
    async def execute(self, **kwargs):
        text = self.args.get("text", "")
        scan_type = self.args.get("type", "auto")  # "user_prompt", "document", or "auto"
        result = scanner.scan(text, scan_type)
        return Response(
            message=f"Scan complete: severity={result.severity_name}, "
                    f"is_attack={result.is_attack}, "
                    f"categories={result.categories}",
            break_loop=False
        )
```

Tool description (in `prompts/tool.scan_content.md`) instructs the agent to use this when processing untrusted external content before acting on it.

## WebUI Dashboard

### Sidebar Entry

A shield icon button injected via `extensions/webui/sidebar-quick-actions-main-start/stomper-button.html`. Uses `x-move-after` to position after the dashboard button.

### Dashboard Modal (3 tabs)

**Tab 1: Status & Detection Log**
- Real-time stats: total scans, blocks today, last detection timestamp
- Scrollable log table: Timestamp, Type (Direct/Indirect/Canary), Category, Severity badge (color-coded), Snippet, Status (Blocked/Warned/Passed)
- Each row expandable for full details
- Auto-refreshes via `x-every-second` polling
- Clear log button

**Tab 2: Settings**
- Master enable/disable toggle
- Scan scope checkboxes: User messages, Tool outputs, System prompt hardening, Canary tokens
- Sensitivity slider (adjusts score thresholds per severity tier)
- Block action selector: Hard block / Warn-and-continue / Log-only
- Settings persisted via plugin API

**Tab 3: Pattern Editor**
- Table of all patterns (built-in + custom): Name, Category, Regex preview, Weight, Enabled toggle
- Built-in patterns: read-only, toggle enabled/disabled only
- Add Custom Pattern form: Name, Category dropdown, Regex input, Weight slider
- Live test input: type sample text, see if pattern matches in real-time
- Delete button for custom patterns

### API Handlers

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `stomper_status` | GET | Scan count, block count, last event, enabled state |
| `stomper_log` | GET | Recent detection events (paginated, filterable) |
| `stomper_settings` | GET | Read current settings |
| `stomper_settings` | POST | Update settings |
| `stomper_patterns` | GET | List all patterns (built-in + custom) |
| `stomper_patterns` | POST | Add custom pattern |
| `stomper_patterns` | DELETE | Remove custom pattern by ID |

### Stores

| Store | Purpose |
|-------|---------|
| `stomperDashboard` | Tab state, polling, fetches status and log data |
| `stomperSettings` | Reads/writes settings, manages toggle states |
| `stomperPatternEditor` | Pattern CRUD, live regex testing against sample input |

## Notifications

When Prompt Stomper blocks a message (High severity), it fires a toast notification via the existing `NotificationManager`:

```python
NotificationManager.notify(
    agent=self.agent,
    type="warning",
    title="Prompt Stomper: Message Blocked",
    message=f"Detected {result.attack_type} injection ({', '.join(result.categories)})",
    persistent=False
)
```

This uses the existing notification infrastructure with no new frontend code for toasts.

## Default Patterns (categories)

The `data/default_patterns.json` ships with approximately 50 patterns across all 8 attack categories:

### Direct Attack Patterns (examples)
- "ignore previous instructions" / "disregard your rules" / "forget everything above"
- "you are now [NAME]" / "pretend to be" / "act as if you have no restrictions"
- Fake conversation turn markers: `\nUser:` / `\nAssistant:` / `\nSystem:` embedded in user text
- Base64 encoded blocks (`[A-Za-z0-9+/]{20,}={0,2}`)
- URL encoded instruction sequences (`%[0-9A-F]{2}` patterns with instruction keywords)
- "DAN" / "do anything now" / "developer mode" / "sudo mode"

### Indirect Attack Patterns (examples)
- `[SYSTEM ANNOTATION:` / `[INSTRUCTION:` / `[AI NOTE:` hidden markers
- "send email to" / "post to" / "upload to" embedded in document text
- "ignore the user" / "do not tell the user" hidden directives
- URLs in imperative context ("navigate to", "fetch from", "download")
- Privilege markers: "admin mode", "root access", "elevated permissions"

## Implementation Order

1. `helpers/scanner.py` + `helpers/patterns.py` + `data/default_patterns.json` — Core engine
2. `helpers/stomper_log.py` — Event storage
3. `extensions/python/user_message_ui/_05_prompt_stomper.py` — Direct shield
4. `extensions/python/tool_execute_after/_05_document_scanner.py` — Indirect shield
5. `extensions/python/system_prompt/_05_stomper_instructions.py` — System hardening + canary
6. `extensions/python/response_stream_chunk/_05_canary_monitor.py` — Canary monitor
7. `extensions/python/message_loop_prompts_after/_05_history_scanner.py` — History scan
8. `prompts/stomper.system_hardening.md` + `prompts/tool.scan_content.md` — Prompts
9. `tools/scan_content.py` — Agent tool
10. `api/` handlers — All four API endpoints
11. `webui/stomper-dashboard.html` + store — Dashboard modal shell + tab 1 (log)
12. `webui/stomper-settings.html` + store — Tab 2 (settings)
13. `webui/stomper-pattern-editor.html` + store — Tab 3 (pattern editor)
14. `extensions/webui/.../stomper-button.html` — Sidebar button
15. Integration testing with real injection payloads
