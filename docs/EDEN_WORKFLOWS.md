# Eden Clinical Inboxologist - Workflow Documentation

## Table of Contents
1. [Happy Path Overview](#happy-path-overview)
2. [User Workflows](#user-workflows)
3. [API Reference](#api-reference)
4. [State Management](#state-management)
5. [MVP Feature Matrix](#mvp-feature-matrix)

---

## Happy Path Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        EDEN HAPPY PATH WORKFLOW                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. SETUP (One-time)                                                         │
│     ┌──────────┐    ┌──────────────┐    ┌─────────────┐                     │
│     │ Open     │───▶│ Enter API    │───▶│ Connect to  │                     │
│     │ Settings │    │ Credentials  │    │ Dr. Chrono  │                     │
│     └──────────┘    └──────────────┘    └─────────────┘                     │
│                                                ▼                             │
│  2. SYNC                                 ┌─────────────┐                     │
│     ┌──────────┐    ┌──────────────┐    │ OAuth Flow  │                     │
│     │ Click    │───▶│ Fetch from   │◀───│ Complete    │                     │
│     │ Sync     │    │ EMR          │    └─────────────┘                     │
│     └──────────┘    └──────────────┘                                        │
│                            ▼                                                 │
│  3. REVIEW          ┌──────────────┐                                        │
│     ┌──────────┐    │ AI Clusters  │    ┌─────────────┐                     │
│     │ View     │───▶│ & Confidence │───▶│ Review      │                     │
│     │ Clusters │    │ Scores       │    │ Reasoning   │                     │
│     └──────────┘    └──────────────┘    └─────────────┘                     │
│                                                ▼                             │
│  4. ACTION          ┌──────────────┐    ┌─────────────┐                     │
│     ┌──────────┐    │              │    │             │                     │
│     │ Approve  │───▶│ Execute via  │───▶│ Mark Done   │                     │
│     │ or Edit  │    │ EMR API      │    │             │                     │
│     └──────────┘    └──────────────┘    └─────────────┘                     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## User Workflows

### Workflow 1: First-Time Setup

**Goal:** Connect Eden to Dr. Chrono EMR

```
User Action                    UI State Change              API Call
─────────────────────────────────────────────────────────────────────────
1. Open Eden (/eden)          → Page loads                  None (static HTML)
                              → init() runs
                              → loadEMRCredentials()        POST /eden/emr_connect
                                                            {action: "get_credentials"}
                              → checkEMRStatus()            POST /eden/emr_connect
                                                            {action: "status"}

2. Click Settings gear        → showSettings = true         None

3. Enter Client ID            → emrCredentials.clientId     None (local state)
   Enter Client Secret        → emrCredentials.clientSecret None (local state)

4. Click "Save Credentials"   → savingCredentials = true    POST /eden/emr_connect
                                                            {action: "save_credentials",
                                                             client_id: "...",
                                                             client_secret: "..."}
                              → Secret masked to ••••

5. Click "Connect"            → Redirect to Dr. Chrono      POST /eden/emr_connect
                                                            {action: "connect"}
                                                            → Returns auth_url
                              → window.location = auth_url

6. User authorizes            → Dr. Chrono OAuth page       (External)
   in Dr. Chrono              → Redirects back to /eden?code=XXX

7. Page loads with code       → handleOAuthCallback()       POST /eden/emr_connect
                                                            {action: "callback",
                                                             code: "XXX"}
                              → emrConnected = true
                              → URL cleaned to /eden
                              → syncInbox() called          POST /eden/emr_connect
                                                            {action: "sync"}
```

**State After Workflow 1:**
```javascript
{
  emrConnected: true,
  emrCredentials: { clientId: "abc123", clientSecret: "••••••••" },
  clusters: [...fromEMR],
  recentActivity: ["Successfully connected to Dr. Chrono", "Synced X items"]
}
```

---

### Workflow 2: Daily Inbox Review

**Goal:** Review and process inbox items

```
User Action                    UI State Change              API Call
─────────────────────────────────────────────────────────────────────────
1. Open Eden (/eden)          → Page loads
                              → checkEMRStatus()            POST /eden/emr_connect
                                                            {action: "status"}
                              → loadData()                  GET /eden/clusters

2. View Clusters tab          → viewMode = "clusters"       None (already loaded)
   (default view)             → filteredClusters computed

3. Click patient cluster      → selectedClusterId = "..."   None
                              → Cluster card highlighted
                              → chatContext updated

4. Expand reasoning panel     → showReasoning = true        None
   (click info icon)          → Displays confidence factors

5. Review task details        → (read only)                 None
   - Title, summary
   - Draft content
   - Confidence breakdown
```

**UI Layout - Clusters View:**
```
┌──────────────────────────────────────────────────────────────────────────┐
│ [Eden Logo]  Command Center    Auto: 3  Pending: 2  Escalated: 1   [⚙️] │
├────────────────┬─────────────────────────────────────────────────────────┤
│ View Toggle    │                                                         │
│ [Clusters]     │  ┌─────────────────────────────────────────────────┐   │
│  Lanes         │  │ John Doe                              [87%] ▼  │   │
│  Summary       │  │ 2 items                                         │   │
│                │  ├─────────────────────────────────────────────────┤   │
│ Patient List   │  │ 🧪 Lipid Panel - Normal         [94%] ✓ Auto   │   │
│ ┌────────────┐ │  │    All values within range...                   │   │
│ │ John Doe   │ │  │    [Draft: "Hi John, great news..."]            │   │
│ │ 87% ●●     │ │  │                                    [ℹ️]         │   │
│ ├────────────┤ │  ├─────────────────────────────────────────────────┤   │
│ │ Sarah Lee  │ │  │ 💬 Portal Message              [72%] ⏳ Review  │   │
│ │ 91% ●      │ │  │    Patient asking about timing...               │   │
│ ├────────────┤ │  │                        [Approve] [Edit] [⚠️]   │   │
│ │ Michael C  │ │  │                                    [ℹ️]         │   │
│ │ 45% ⚠️     │ │  └─────────────────────────────────────────────────┘   │
│ └────────────┘ │                                                         │
│                │  ┌─────────────────────────────────────────────────┐   │
│ Eden Activity  │  │ Sarah Lee                             [91%] ▼  │   │
│ • Auto-sent... │  │ ...                                             │   │
│ • Drafted...   │  └─────────────────────────────────────────────────┘   │
└────────────────┴─────────────────────────────────────────────────────────┘
```

---

### Workflow 3: Approve a Task

**Goal:** Approve a pending task and execute the action

```
User Action                    UI State Change              API Call
─────────────────────────────────────────────────────────────────────────
1. Find pending task          → (navigate to cluster)       None

2. Review draft content       → Expand reasoning panel      None
   and reasoning              → Read confidence factors

3. Click "Approve"            → Task status changes         POST /eden/tasks
                                                            {id: "task-123",
                                                             action: "approve"}
                              → task.status = "completed"
                              → task.resolvedAt = now
                              → stats recalculated
                              → Activity feed updated

4. (Backend executes)         →                             (EMR API call)
   - Sends message to patient                               e.g., POST /messages
   - Or approves refill                                     or POST /medications
```

**State Changes:**
```javascript
// Before
task.status = "needs_review"
stats = { autoHandled: 3, pending: 2, escalated: 1 }

// After
task.status = "completed"
task.resolvedAt = "2024-12-02T..."
task.resolvedBy = "physician"
stats = { autoHandled: 3, pending: 1, escalated: 1 }
recentActivity.unshift({ type: "auto", message: "Approved X for Y" })
```

---

### Workflow 4: Edit and Approve

**Goal:** Modify a draft before approving

```
User Action                    UI State Change              API Call
─────────────────────────────────────────────────────────────────────────
1. Find task to edit          → (navigate)                  None

2. Click "Edit"               → Edit modal opens            None
                              → (CURRENTLY: shows alert)

3. Modify draft content       → Local state updates         None
   in textarea

4. Click "Save & Approve"     → Modal closes                PUT /eden/tasks/{id}
                                                            {draft_content: "...",
                                                             proposed_action: "..."}
                              →                             POST /eden/tasks
                                                            {id: "...",
                                                             action: "approve"}
                              → Task marked complete

   OR Click "Save Draft"      → Modal closes                PUT /eden/tasks/{id}
                              → Status stays pending         {draft_content: "..."}
```

---

### Workflow 5: Escalate a Task

**Goal:** Flag a task for physician attention

```
User Action                    UI State Change              API Call
─────────────────────────────────────────────────────────────────────────
1. Find concerning task       → (navigate)                  None

2. Click escalate icon (⚠️)   → task.status = "escalated"   POST /eden/tasks
                                                            {id: "...",
                                                             action: "escalate"}
                              → task.confidence capped ≤50%
                              → Cluster priority = 0
                              → Activity feed updated
```

---

### Workflow 6: Chat with Eden

**Goal:** Ask Eden questions about the inbox

```
User Action                    UI State Change              API Call
─────────────────────────────────────────────────────────────────────────
1. Click "Talk to Eden"       → showChat = true             None
                              → Chat panel slides in

2. Type message               → chatInput = "..."           None

3. Press Enter / Send         → chatMessages.push(user msg) POST /eden/chat
                              → isTyping = true             {message: "...",
                                                             context: {...},
                                                             history: [...]}

4. Response received          → isTyping = false
                              → chatMessages.push(ai msg)
                              → conversationHistory updated
                              → Scroll to bottom

5. Click quick action         → Same as typing that text    Same as above
   (Summarize/Priorities)
```

**Chat Context Sent to Backend:**
```javascript
{
  stats: { autoHandled: 3, pending: 2, escalated: 1, total: 6 },
  totalClusters: 4,
  pendingTasks: [
    { title: "...", category: "message", confidence: 72, patient: "John Doe" }
  ],
  escalatedTasks: [
    { title: "A1C Result", category: "lab", patient: "Michael Chen" }
  ],
  selectedCluster: { patient: {...}, tasks: [...] } | null,
  currentView: "clusters"
}
```

---

### Workflow 7: Sync Inbox

**Goal:** Manually refresh data from EMR

```
User Action                    UI State Change              API Call
─────────────────────────────────────────────────────────────────────────
1. Click sync button (🔄)     → syncing = true
                              → Button animates

2. If EMR connected:          →                             POST /eden/emr_connect
                                                            {action: "sync"}
   Response received          → loadData() called           GET /eden/clusters
                              → clusters updated
                              → categories recounted
                              → Activity updated

3. If EMR not connected:      →                             GET /eden/clusters
                              → Just refresh from backend
                              → Activity: "Data refreshed"

4. Complete                   → syncing = false
```

---

### Workflow 8: View Summary

**Goal:** See daily digest and analytics

```
User Action                    UI State Change              API Call
─────────────────────────────────────────────────────────────────────────
1. Click "Summary" tab        → viewMode = "summary"        GET /eden/summary
                                                            (optional, data already
                                                             computed from clusters)

2. View stats grid            → (read only)                 None
   - Auto-handled count
   - Pending count
   - Escalated count
   - Total today

3. View category breakdown    → (read only)                 None
   - Bar chart by category

4. View recent auto-handled   → (read only)                 None
   - List of 5 most recent
```

**Summary View Layout:**
```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Daily Summary                                   │
│                     Last updated: Dec 2, 2024 10:30 AM                  │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐        │
│  │     3      │  │     2      │  │     1      │  │     6      │        │
│  │ Auto-      │  │ Pending    │  │ Escalated  │  │ Total      │        │
│  │ handled    │  │ Review     │  │            │  │ Today      │        │
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘        │
├─────────────────────────────────────────────────────────────────────────┤
│  By Category                                                             │
│  🧪 Lab Results    ████████████████░░░░  3                              │
│  💬 Messages       ████████░░░░░░░░░░░░  2                              │
│  💊 Refills        ████░░░░░░░░░░░░░░░░  1                              │
├─────────────────────────────────────────────────────────────────────────┤
│  Recently Auto-Handled                                                   │
│  ✓ Lipid Panel - Normal (John Doe) - lab - 1h ago                       │
│  ✓ Annual Physical Request (Emily Rodriguez) - scheduling - 2h ago      │
│  ✓ Records Request (Emily Rodriguez) - message - 1.5h ago               │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## API Reference

### Endpoint Summary Table

| Endpoint | Method | Purpose | Request Body | Response |
|----------|--------|---------|--------------|----------|
| `/eden/clusters` | GET | List all patient clusters | Query: `?status=&category=` | `{clusters: [], count: N}` |
| `/eden/clusters/:id` | GET | Get single cluster | - | `{cluster: {...}}` |
| `/eden/tasks` | GET | List all tasks | Query: `?status=&category=` | `{tasks: [], count: N}` |
| `/eden/tasks` | POST | Task actions | `{id, action: "approve\|reject\|escalate"}` | `{success, task, message}` |
| `/eden/tasks/:id` | PUT | Edit task | `{draft_content, proposed_action}` | `{success, task}` |
| `/eden/summary` | GET | Daily digest | - | `{summary: {...}}` |
| `/eden/policies` | GET | List policies | - | `{policies: [], suggestions: []}` |
| `/eden/policies` | POST | Create policies | `{policies: "text"}` | `{success, policies: [], count}` |
| `/eden/policies/:id` | DELETE | Remove policy | - | `{success, message}` |
| `/eden/chat` | POST | AI chat | `{message, context, history}` | `{success, message, timestamp}` |
| `/eden/emr_connect` | POST | EMR operations | `{action: "..."}` | (varies by action) |

### EMR Connect Actions

| Action | Request | Response | Side Effects |
|--------|---------|----------|--------------|
| `connect` | `{action: "connect"}` | `{authorization_url}` | None |
| `callback` | `{action: "callback", code}` | `{success, redirect}` | Stores tokens |
| `sync` | `{action: "sync"}` | `{success, items_fetched, clusters_updated}` | Updates clusters |
| `status` | `{action: "status"}` | `{connected, emr_type, expires_at}` | None |
| `disconnect` | `{action: "disconnect"}` | `{success}` | Clears tokens |
| `save_credentials` | `{action: "save_credentials", client_id, client_secret}` | `{success}` | Writes to file |
| `get_credentials` | `{action: "get_credentials"}` | `{client_id, has_secret}` | None |

---

## State Management

### Frontend State (Alpine.js)

```javascript
// Location: eden_ui/index.html → Alpine.data('edenApp', () => ({...}))

{
  // ─── View State ───────────────────────────────
  viewMode: 'clusters' | 'lanes' | 'summary',
  selectedClusterId: string | null,
  showSettings: boolean,
  showNotifications: boolean,
  showChat: boolean,
  darkMode: boolean,

  // ─── Loading State ────────────────────────────
  syncing: boolean,
  isTyping: boolean,           // Chat typing indicator
  savingCredentials: boolean,

  // ─── Connection State ─────────────────────────
  emrConnected: boolean,

  // ─── Data ─────────────────────────────────────
  clusters: Cluster[],         // From API or MOCK_CLUSTERS
  categories: Category[],      // Derived from clusters
  activeCategories: string[],  // Filter state
  recentActivity: Activity[],  // Activity feed items
  notifications: Notification[],

  // ─── Chat State ───────────────────────────────
  chatInput: string,
  chatMessages: Message[],
  chatContext: string | null,  // "Viewing: John Doe (2 tasks)"
  conversationHistory: Message[],

  // ─── Settings ─────────────────────────────────
  confidenceThreshold: number, // 50-100
  notificationSettings: { email, push, sms },
  emrCredentials: { clientId, clientSecret },
  showClientSecret: boolean,
  policiesText: string,

  // ─── Computed (getters) ───────────────────────
  stats: { autoHandled, pending, escalated, total },
  filteredClusters: Cluster[], // Sorted by priority
}
```

### Backend State

```python
# Location: python/helpers/eden/clustering.py

class ClusteringService:
    _instance = None           # Singleton
    clusters: Dict[str, Cluster]  # patient_id → Cluster
    tasks: Dict[str, EdenTask]    # task_id → Task

# Location: python/api/eden/emr_connect.py

_emr_credentials: dict = {}    # In-memory token storage
CREDENTIALS_FILE = ".eden_credentials.json"  # Persisted API creds

# Location: python/helpers/eden/policy_engine.py

class PolicyEngine:
    _instance = None           # Singleton
    policies: List[CompiledPolicy]
```

### State Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           STATE FLOW                                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  FRONTEND (Alpine.js)              BACKEND (Python/Flask)                │
│  ═══════════════════              ════════════════════════               │
│                                                                          │
│  ┌──────────────┐                 ┌──────────────────────┐              │
│  │ User Action  │                 │ EMR (Dr. Chrono)     │              │
│  └──────┬───────┘                 └──────────┬───────────┘              │
│         │                                    │                           │
│         ▼                                    ▼                           │
│  ┌──────────────┐     fetch()      ┌──────────────────────┐             │
│  │ edenApp      │ ◀───────────────▶│ API Handlers         │             │
│  │ state        │                  │ (clusters, tasks,    │             │
│  └──────┬───────┘                  │  chat, emr_connect)  │             │
│         │                          └──────────┬───────────┘             │
│         │ Alpine                              │                          │
│         │ reactivity                          ▼                          │
│         ▼                          ┌──────────────────────┐             │
│  ┌──────────────┐                  │ Services             │             │
│  │ DOM Update   │                  │ - ClusteringService  │             │
│  └──────────────┘                  │ - PolicyEngine       │             │
│                                    │ - ConfidenceScorer   │             │
│                                    └──────────────────────┘             │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ localStorage                                                     │    │
│  │ - eden-dark-mode: "true" | "false"                              │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ .eden_credentials.json (server-side)                            │    │
│  │ - client_id, client_secret                                      │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## MVP Feature Matrix

### Core Features (Must Have)

| Feature | UI Component | API Endpoint | Backend Service | Status |
|---------|--------------|--------------|-----------------|--------|
| View clusters | Clusters view | `GET /eden/clusters` | ClusteringService | ✅ Done |
| View tasks | Task cards | (included in clusters) | ClusteringService | ✅ Done |
| Approve task | Approve button | `POST /eden/tasks` | ClusteringService + EMR | ⚠️ Partial |
| Escalate task | Escalate button | `POST /eden/tasks` | ClusteringService | ✅ Done |
| View reasoning | Expand panel | (client-side) | - | ✅ Done |
| EMR OAuth | Settings modal | `POST /eden/emr_connect` | DrChronoClient | ✅ Done |
| Sync inbox | Sync button | `POST /eden/emr_connect` | DrChronoAdapter | ⚠️ Partial |
| Dark mode | Toggle button | (localStorage) | - | ✅ Done |

### Secondary Features (Should Have)

| Feature | UI Component | API Endpoint | Backend Service | Status |
|---------|--------------|--------------|-----------------|--------|
| Edit task | Edit modal | `PUT /eden/tasks/:id` | ClusteringService | ❌ Stub |
| Chat with Eden | Chat panel | `POST /eden/chat` | LiteLLM | ✅ Done |
| Manage policies | Settings modal | `POST /eden/policies` | PolicyEngine | ⚠️ Partial |
| View summary | Summary view | `GET /eden/summary` | ClusteringService | ✅ Done |
| Lanes view | Lanes tab | (client-side) | - | ✅ Done |

### Nice to Have (Future)

| Feature | UI Component | API Endpoint | Status |
|---------|--------------|--------------|--------|
| Batch approve | Multi-select | `POST /eden/tasks/batch` | ❌ Not started |
| Notifications | Bell dropdown | WebSocket | ❌ Not started |
| Analytics | Dashboard | `GET /eden/analytics` | ❌ Not started |
| Multiple EMRs | Settings | - | ❌ Not started |

---

## Known Issues & TODOs

### Critical (Blocks MVP)

1. **EMR Actions Not Executing**
   - Location: `python/api/eden/tasks.py:_execute_task_action()`
   - Issue: All EMR adapter calls are commented out
   - Fix: Implement actual API calls to Dr. Chrono

2. **Dr. Chrono Client Incomplete**
   - Location: `python/helpers/eden/drchrono_client.py`
   - Issue: Many methods return mock data or are not tested
   - Fix: Complete implementation with real API testing

### Medium Priority

3. **Edit Task Modal Missing**
   - Location: `eden_ui/index.html:editTask()`
   - Current: Shows `alert()` placeholder
   - Fix: Build proper modal with textarea for draft editing

4. **Settings Not Persisted**
   - Location: Various settings in edenApp
   - Issue: Confidence threshold, notifications reset on reload
   - Fix: Add `GET/POST /eden/settings` endpoint

5. **No Database Layer**
   - Issue: All state is in-memory, lost on restart
   - Fix: Add SQLite or PostgreSQL persistence

### Low Priority

6. **Drag-Drop in Lanes View** - Not interactive
7. **Mobile Responsiveness** - Not optimized
8. **Error Boundaries** - No graceful error handling in UI

---

## File Reference

```
eden_ui/
├── index.html          # Main SPA (Alpine.js + Tailwind)

python/api/eden/
├── __init__.py
├── clusters.py         # GET /eden/clusters
├── tasks.py            # GET/POST/PUT /eden/tasks
├── summary.py          # GET /eden/summary
├── policies.py         # GET/POST/DELETE /eden/policies
├── chat.py             # POST /eden/chat
└── emr_connect.py      # POST /eden/emr_connect (multi-action)

python/helpers/eden/
├── __init__.py
├── models.py           # Data classes (Task, Cluster, Policy, etc.)
├── clustering.py       # ClusteringService singleton
├── emr_adapter.py      # EMRAdapter abstract + DrChronoAdapter
├── drchrono_client.py  # Dr. Chrono OAuth + API client
├── policy_engine.py    # PolicyEngine for natural language rules
└── confidence_scorer.py # ConfidenceScorer algorithm
```
