import { createStore } from "/js/AlpineStore.js";
import { getNamespacedClient } from "/js/websocket.js";
import { callJsonApi } from "/js/api.js";

const EVT_SUB   = "swarm_subscribe";
const EVT_UNSUB = "swarm_unsubscribe";
const EVT_PUSH  = "swarm_push";

const socket = getNamespacedClient("/ws");
socket.addHandlers(["ws_webui"]);

const proto = {
    agents: [],
    panelOpen: false,
    composingFor: null,
    composeText: "",
    _initialized: false,
    _parentCtxId: "",

    async init() {
        if (this._initialized) return;
        this._initialized = true;
        this._parentCtxId = this._readParentCtxId();
        await this._subscribe();
        socket.on(EVT_PUSH, (data) => {
            if (data && Array.isArray(data.agents)) this.agents = data.agents;
        });
        socket.on("connect", async () => { await this._subscribe(); });
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
            const resp = await socket.emit(EVT_SUB, { parent_context_id: this._parentCtxId });
            // Some impls return ack; if agents arrive on push, this no-ops harmlessly
            if (resp && Array.isArray(resp.agents)) this.agents = resp.agents;
        } catch (_) {
            // fall back to one-shot fetch
            try {
                const r = await callJsonApi("/api/swarm_status", { parent_context_id: this._parentCtxId });
                if (r && Array.isArray(r.agents)) this.agents = r.agents;
            } catch (_) {}
        }
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
            await callJsonApi("/api/swarm_send_message", {
                agent_name: name, content, unblock,
            });
        } catch (_) {}
    },

    async cancelAgent(name) {
        try {
            await callJsonApi("/api/swarm_cancel", { agent_name: name });
        } catch (_) {}
    },

    async clearCompleted() {
        try {
            await callJsonApi("/api/swarm_clear_completed", {
                parent_context_id: this._parentCtxId,
            });
        } catch (_) {}
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
