import { createStore } from "/js/AlpineStore.js";
import { getNamespacedClient } from "/js/websocket.js";
import { callJsonApi } from "/js/api.js";
import { renderSafeMarkdown } from "/js/safe-markdown.js";

const EVT_SUB   = "swarm_subscribe";
const EVT_UNSUB = "swarm_unsubscribe";
const EVT_PUSH  = "swarm_push";

const POLL_INTERVAL_MS = 1500;

const socket = getNamespacedClient("/ws");
socket.addHandlers(["ws_webui"]);

const proto = {
    agents: [],
    panelOpen: true,
    composingFor: null,
    composeText: "",
    expandedFor: {},        // map agent_name -> bool
    _initialized: false,
    _parentCtxId: "",
    _pollTimer: null,
    _wsBound: false,

    async init() {
        if (this._initialized) return;
        this._initialized = true;
        this._parentCtxId = this._readParentCtxId();

        // 1. Register push handler BEFORE subscribing so we don't lose events.
        if (!this._wsBound) {
            this._wsBound = true;
            try {
                socket.on(EVT_PUSH, (data) => {
                    if (data && Array.isArray(data.agents)) this.agents = data.agents;
                });
                socket.on("connect", () => { this._subscribe(); });
            } catch (_) {}
        }

        // 2. Subscribe (best-effort; failures are silent and the poll keeps us alive).
        await this._subscribe();

        // 3. Polling fallback. Runs every POLL_INTERVAL_MS regardless of WS state.
        //    Cheap (~1 KB JSON), guarantees the panel reflects backend state even when
        //    the push channel is down.
        await this._poll();
        if (!this._pollTimer) {
            this._pollTimer = setInterval(() => this._poll(), POLL_INTERVAL_MS);
        }
    },

    _readParentCtxId() {
        try {
            return (typeof globalThis.getContext === "function" && globalThis.getContext()) || "";
        } catch (_) {
            return "";
        }
    },

    async _subscribe() {
        try {
            await socket.emit(EVT_SUB, { parent_context_id: this._parentCtxId });
        } catch (_) {}
    },

    async _poll() {
        // Re-read parent ctx in case the user switched chat contexts.
        this._parentCtxId = this._readParentCtxId();
        try {
            const r = await callJsonApi("/plugins/a0_swarm/swarm_status", {
                parent_context_id: this._parentCtxId,
            });
            if (r && Array.isArray(r.agents)) this.agents = r.agents;
        } catch (_) {}
    },

    get activeAgents() {
        return this.agents.filter(a => !["done", "failed", "cancelled"].includes(a.status));
    },
    get completedAgents() {
        return this.agents.filter(a => ["done", "failed", "cancelled"].includes(a.status));
    },
    get hasAgents() { return this.agents.length > 0; },

    statusClass(s) { return "status-" + s; },
    unreadCount(a) {
        return (a.messages || []).filter(m => !m.read && m.sender !== "orchestrator").length;
    },

    isExpanded(name) { return !!this.expandedFor[name]; },
    toggleExpand(name) {
        this.expandedFor = { ...this.expandedFor, [name]: !this.expandedFor[name] };
        if (this.expandedFor[name]) this.markRead(name);
    },

    /**
     * Derive a 1-8 slot index from agent_name "SA{parent}_{slot}".
     * Falls back to a stable hash if the name doesn't match.
     */
    slotIndex(name) {
        const m = /^SA\d+_(\d+)$/.exec(name || "");
        if (m) return ((parseInt(m[1], 10) - 1) % 8) + 1;
        let h = 0;
        for (let i = 0; i < (name || "").length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
        return (h % 8) + 1;
    },

    /**
     * Material-symbols glyph per slot. Distinct, role-evocative, not
     * status-coloured (status is shown by the pill + progress bar).
     */
    slotIcon(name) {
        const icons = [
            "psychology",        // 1 — cognition / planner
            "science",           // 2 — analysis
            "engineering",       // 3 — builder
            "auto_stories",      // 4 — researcher / reading
            "terminal",          // 5 — code
            "support_agent",     // 6 — helper
            "troubleshoot",      // 7 — debugger
            "inventory_2",       // 8 — generalist
        ];
        return icons[this.slotIndex(name) - 1] || "smart_toy";
    },

    openCompose(name)  { this.composingFor = name; this.composeText = ""; if (!this.expandedFor[name]) this.toggleExpand(name); },
    closeCompose()     { this.composingFor = null; this.composeText = ""; },
    togglePanel()      { this.panelOpen = !this.panelOpen; },
    markRead(name) {
        const a = this.agents.find(x => x.agent_name === name);
        if (a) (a.messages || []).forEach(m => m.read = true);
    },

    async sendMessage(name, unblock = false) {
        const content = (this.composeText || "").trim();
        if (!content) return;
        this.closeCompose();
        try {
            await callJsonApi("/plugins/a0_swarm/swarm_send_message", {
                agent_name: name, content, unblock,
            });
        } catch (_) {}
        // Refresh immediately so the user sees their message land.
        this._poll();
    },

    async cancelAgent(name) {
        try {
            await callJsonApi("/plugins/a0_swarm/swarm_cancel", { agent_name: name });
        } catch (_) {}
        this._poll();
    },

    async clearCompleted() {
        try {
            await callJsonApi("/plugins/a0_swarm/swarm_clear_completed", {
                parent_context_id: this._parentCtxId,
            });
        } catch (_) {}
        this._poll();
    },

    /**
     * Render markdown to sanitized HTML for use with x-html.
     *
     * Post-processing: marked treats lists with blank lines between
     * items as "loose" and wraps each <li> body in a <p>, which
     * inflates vertical spacing past anything CSS can fix without
     * fighting the cascade. We unwrap those single-<p>-only list
     * items in the parsed DOM before returning the HTML, so the
     * output behaves like a tight list.
     */
    renderMd(text) {
        if (!text) return "";
        try {
            const html = renderSafeMarkdown(text);
            const tmpl = document.createElement("template");
            tmpl.innerHTML = html;
            for (const li of tmpl.content.querySelectorAll("li")) {
                // If the <li>'s element children are exactly one <p> (text
                // nodes around it OK), promote the <p>'s children up.
                const elementChildren = Array.from(li.children);
                if (elementChildren.length === 1 && elementChildren[0].tagName === "P") {
                    const p = elementChildren[0];
                    while (p.firstChild) p.parentNode.insertBefore(p.firstChild, p);
                    p.remove();
                }
            }
            return tmpl.innerHTML;
        } catch (_) {
            try { return renderSafeMarkdown(text); } catch (_) { return ""; }
        }
    },

    relativeTime(iso) {
        if (!iso) return "";
        const d = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
        if (d < 60)   return `${d}s ago`;
        if (d < 3600) return `${Math.floor(d/60)}m ago`;
        return `${Math.floor(d/3600)}h ago`;
    },
};

export const swarmStore = createStore("swarmStore", proto);
