# Eden: Clinical Inboxologist Agent Design

**Date:** 2025-12-02
**Status:** Approved for Implementation
**Author:** Brainstorming Session

---

## 1. Vision

**Eden** is an autonomous clinical inbox agent for solo practitioners with delegated autonomy. The physician sets policies upfront, and Eden handles 90%+ of inbox tasks autonomously, escalating only edge cases.

### Core Paradigm

```
┌─────────────────────────────────────────────────────────────┐
│                     PHYSICIAN                                │
│  Sets policies │ Reviews escalations │ Approves drafts      │
└──────────────────────────┬──────────────────────────────────┘
                           │
                    ┌──────▼──────┐
                    │    EDEN     │
                    │  (Agent)    │
                    └──────┬──────┘
                           │
     ┌─────────┬───────────┼───────────┬─────────┐
     ▼         ▼           ▼           ▼         ▼
┌─────────┐┌─────────┐┌─────────┐┌─────────┐┌─────────┐
│  Labs   ││Messages ││ Refills ││Referrals││  Prior  │
│         ││         ││         ││         ││  Auth   │
└─────────┘└─────────┘└─────────┘└─────────┘└─────────┘
                           │
                    ┌──────▼──────┐
                    │  Dr.Chrono  │
                    │    EMR      │
                    └─────────────┘
```

### Key Behaviors

1. **Confidence-Based Autonomy**: Auto-handles tasks above threshold (default 85%)
2. **Smart Clustering**: Related items grouped by patient/context
3. **Physician Style Matching**: Learns communication patterns from examples
4. **Policy Evolution**: Natural language policies refined by feedback patterns
5. **Scheduled Digests**: Daily summaries via in-app, email, and push

---

## 2. Task Categories (All In-Scope for MVP)

| Category | Description | Autonomy Level |
|----------|-------------|----------------|
| **Lab Results** | Analyze, personalize, send to patients | High (normal results auto-send) |
| **Patient Messages** | Email/portal communication | Medium (drafts for clinical Qs) |
| **Med Refills** | Evaluate and draft approvals | Low (always human approval) |
| **Referrals** | Specialist letters, coordination | Medium |
| **Prior Auth** | Insurance authorization workflows | Medium |
| **Scheduling** | Appointment requests | High |
| **Billing Inquiries** | Insurance/billing questions | High |
| **Internal Messages** | Staff coordination | Medium |

---

## 3. UI Design: Command Center

### Design Philosophy

**Command Center** - Agent-focused interface where the physician "supervises" Eden. Shows activity stream, confidence levels, what's autonomous vs. pending.

### Layout

```
┌──────────────────────────────────────────────────────────────────────────┐
│ ┌─────────┐                                          ┌────┐ ┌────┐ ┌────┐│
│ │  EDEN   │  Command Center                          │ 🔔 │ │ ⚙️ │ │ 👤 ││
│ └─────────┘                                          └────┘ └────┘ └────┘│
├────────────────┬─────────────────────────────────────────────────────────┤
│                │                                                         │
│  ┌──────────┐  │  ┌─────────────────────────────────────────────────┐   │
│  │ CLUSTERS │  │  │  📊 Daily Summary Bar                           │   │
│  │ ──────── │  │  │  Auto: 47 │ Pending: 8 │ Escalated: 2          │   │
│  │ 👤 J.Doe │  │  └─────────────────────────────────────────────────┘   │
│  │   Lab ✓  │  │                                                         │
│  │   Msg ⏳ │  │  ┌─────────────────────────────────────────────────┐   │
│  │          │  │  │  CLUSTER: John Doe                    85% ▼    │   │
│  │ 👤 S.Lee │  │  │  ┌─────────────────────────────────────────┐   │   │
│  │   Refill │  │  │  │ 🧪 Lipid Panel - Normal               ✓ │   │   │
│  │          │  │  │  │ Auto-sent: "Hi John, good news..."     │   │   │
│  │ ──────── │  │  │  └─────────────────────────────────────────┘   │   │
│  │ CATEGORY │  │  │  ┌─────────────────────────────────────────┐   │   │
│  │ ──────── │  │  │  │ 💬 Portal Message            ⏳ 72%    │   │   │
│  │ 🧪 Labs  │  │  │  │ "Question about medication timing"     │   │   │
│  │ 💊 Refill│  │  │  │ [Approve Draft] [Edit] [Escalate]      │   │   │
│  │ 💬 Msgs  │  │  │  └─────────────────────────────────────────┘   │   │
│  │ 📋 Refer │  │  └─────────────────────────────────────────────────┘   │
│  │ 📄 Auth  │  │                                                         │
│  │          │  │  ┌─────────────────────────────────────────────────┐   │
│  └──────────┘  │  │  CLUSTER: Sarah Lee                    91% ▼   │   │
│                │  │  ...                                            │   │
│  ┌──────────┐  │  └─────────────────────────────────────────────────┘   │
│  │ ACTIVITY │  │                                                         │
│  │ ──────── │  │                                                         │
│  │ Eden is  │  │                                                         │
│  │ processing│  │                                                         │
│  │ 3 items..│  │                                                         │
│  └──────────┘  │                                                         │
│                │                                                         │
└────────────────┴─────────────────────────────────────────────────────────┘
```

### View Modes

1. **Clusters View** (default): Tasks grouped by patient, sorted by priority
2. **Lanes View**: Kanban columns by category (Labs | Refills | Messages | etc.)
3. **Summary View**: Daily digest dashboard with stats

### Interaction Model

- **Confidence scores visible** on every task/cluster
- **Expandable reasoning** - click to see Eden's decision chain
- **Quick actions**: Approve, Edit, Escalate, Reject

---

## 4. Visual Design System

### Color Palette

**No pink/purple/blue gradients.** Clinical-grade, calm, authoritative.

| Role | Color | Hex |
|------|-------|-----|
| Background | Off-white | `#F8F7F5` |
| Surface | White | `#FFFFFF` |
| Primary Text | Charcoal | `#1A1A1A` |
| Secondary Text | Slate | `#64748B` |
| Border | Light gray | `#E2E2E0` |
| Eden Active | Deep teal | `#0D9488` |
| Success/Auto | Forest green | `#15803D` |
| Pending/Review | Amber | `#D97706` |
| Escalated/Alert | Rust | `#DC2626` |
| Neutral Action | Slate | `#475569` |

### Confidence Visualization

```
90-100%  ████████████  Forest green - Auto-handled
75-89%   ████████░░░░  Teal - High confidence
60-74%   ██████░░░░░░  Amber - Review recommended
<60%     ████░░░░░░░░  Rust - Escalated
```

### Typography

- **Headings**: Inter 600, 18-24px
- **Body**: Inter 400, 14-16px
- **Labels**: Inter 500, 12px
- **Monospace** (reasoning): JetBrains Mono 400, 13px

---

## 5. Frontend Architecture

### Tech Stack

- **Alpine.js** - Reactive UI (matches Agent Zero)
- **Tailwind CSS** - Utility-first styling
- **Headless UI components** - Accessible primitives

### Directory Structure

```
eden_ui/
├── index.html
├── css/
│   └── eden.css
├── js/
│   ├── app.js
│   ├── api.js
│   └── stores/
│       ├── clusters.js
│       ├── tasks.js
│       ├── policies.js
│       ├── activity.js
│       └── summary.js
├── components/
│   ├── layout/
│   ├── clusters/
│   ├── lanes/
│   ├── tasks/
│   ├── reasoning/
│   ├── policies/
│   ├── summary/
│   └── settings/
└── public/
```

---

## 6. Backend Architecture

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/eden/clusters` | GET | Fetch smart clusters |
| `/eden/tasks` | GET | List tasks (filterable) |
| `/eden/tasks/:id/approve` | POST | Approve action |
| `/eden/tasks/:id/reject` | POST | Reject action |
| `/eden/tasks/:id/edit` | PUT | Edit draft |
| `/eden/policies` | GET/POST | Policy CRUD |
| `/eden/summary` | GET | Daily digest |
| `/eden/emr/connect` | POST | OAuth flow |
| `/eden/emr/sync` | POST | Manual sync |

### Data Models

```python
@dataclass
class EdenTask:
    id: str
    category: TaskCategory  # LAB, MESSAGE, REFILL, etc.
    status: TaskStatus      # PENDING, AUTO_HANDLED, NEEDS_REVIEW, etc.
    confidence: float
    patient: Patient
    title: str
    summary: str
    proposed_action: str
    draft_content: str
    reasoning: list[str]

@dataclass
class Cluster:
    id: str
    patient: Patient
    tasks: list[EdenTask]
    avg_confidence: float
    priority: int
```

---

## 7. EMR Integration

### Approach

**Hybrid Pragmatic**: Direct Dr. Chrono integration first, refactor to adapter pattern when adding second EMR.

### Dr. Chrono OAuth Flow

1. User clicks "Connect EMR" in settings
2. Redirect to `drchrono.com/o/authorize/`
3. User authorizes, callback with code
4. Exchange code for access/refresh tokens
5. Store tokens securely, begin inbox sync

### EMR Adapter Interface

```python
class EMRAdapter(ABC):
    async def connect(self, credentials: dict) -> bool
    async def fetch_inbox_items(self, since: datetime) -> list[InboxItem]
    async def get_patient(self, patient_id: str) -> Patient
    async def send_message(self, patient_id: str, message: Message) -> bool
    async def update_chart(self, patient_id: str, update: ChartUpdate) -> bool
```

---

## 8. Confidence Scoring

### Factors

| Factor | Weight | Description |
|--------|--------|-------------|
| Task Clarity | 25% | How clear-cut is this task type? |
| Policy Match | 25% | Does an explicit policy apply? |
| Patient History | 20% | Sufficient context on patient? |
| Pattern Match | 15% | Similar cases handled before? |
| Risk Level | 15% | Downside of getting wrong? |

### Reasoning Chain

Eden generates human-readable reasoning:

```
Task: LAB for Sarah Johnson
✓ Clear-cut lab result with standard parameters
✓ Matches policy: "Auto-send normal lipid panels"
✓ Patient well-known, 12 visits, no flags
✓ Low risk: routine lab
→ Confidence: 94%
```

---

## 9. Policy Engine

### Natural Language Policies

```
"Always escalate abnormal A1C above 9"

"Auto-approve lisinopril refills for stable patients
 who have had a visit in the last 6 months"

"Never auto-send lab results containing 'malignancy'"

"Route all messages mentioning chest pain to escalation"
```

### Policy Evolution

1. Start with natural language policies
2. Eden parses into executable rules
3. Eden observes approve/reject patterns
4. Suggests rule refinements based on feedback

---

## 10. Notifications & Digest

### Channels

- **In-App**: Always-available summary dashboard
- **Email**: Configurable daily digest (morning/EOD)
- **Push/SMS**: Key stats and urgent escalations

### Digest Content

- Tasks auto-handled today
- Tasks pending review
- Escalations requiring attention
- Confidence calibration insights

---

## 11. Implementation Phases

### Phase 1: MVP

- OAuth connection to Dr. Chrono
- Command Center with Clusters + Lanes views
- Confidence scores + expandable reasoning
- Auto-handle vs. Needs Review queue
- Basic policy configuration
- Lab results workflow
- Patient message responses
- Med refill drafts (human approval)
- In-app daily summary
- Push/email notification setup

### Phase 2: Enhancement

- Full referral management
- Prior authorization workflows
- Physician style learning (training data)
- Advanced rule refinements from feedback
- Additional EMR adapters

---

## 12. Architecture Decision: Overlay Approach

Build `eden_ui/` alongside existing Agent Zero `webui/`. Reuse:

- Python backend (Flask, API handlers, agent loop)
- Tool system (add new EMR tools)
- Memory and context management

Replace only the frontend with Eden-specific Command Center. Extend Agent Zero's log types and API handlers for healthcare-specific semantics.
