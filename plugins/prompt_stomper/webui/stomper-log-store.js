import { createStore } from "/js/AlpineStore.js";
import { callJsonApi } from "/js/api.js";

const model = {
    events: [],
    loading: false,
    _initialized: false,

    init() {
        if (this._initialized) return;
        this._initialized = true;
    },

    async open() {
        await this.refresh();
    },

    async refresh() {
        this.loading = true;
        try {
            const result = await callJsonApi("/stomper_log", { limit: 100, offset: 0 });
            this.events = result.events || [];
        } catch (e) {
            console.error("Stomper log fetch failed:", e);
        }
        this.loading = false;
    },

    async clearLog() {
        try {
            await callJsonApi("/stomper_log", { action: "clear" });
            this.events = [];
        } catch (e) {
            console.error("Failed to clear log:", e);
        }
    },

    severityClass(severity) {
        const classes = { 0: "safe", 1: "low", 2: "medium", 3: "high" };
        return `severity-${classes[severity] || "safe"}`;
    },

    formatTime(timestamp) {
        if (!timestamp) return "";
        return new Date(timestamp * 1000).toLocaleString();
    },

    cleanup() {
        this.events = [];
    },
};

export const store = createStore("stomperLog", model);
