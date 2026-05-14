import { createStore } from "/js/AlpineStore.js";
import { getNamespacedClient } from "/js/websocket.js";
import { callJsonApi } from "/js/api.js";

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

    openCompose(name)  { this.composingFor = name; this.composeText = ""; },
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

    relativeTime(iso) {
        if (!iso) return "";
        const d = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
        if (d < 60)   return `${d}s ago`;
        if (d < 3600) return `${Math.floor(d/60)}m ago`;
        return `${Math.floor(d/3600)}h ago`;
    },
};

export const swarmStore = createStore("swarmStore", proto);
