import { createStore } from "/js/AlpineStore.js";
import { callJsonApi } from "/js/api.js";

const model = {
    activeTab: "log",  // "log", "settings", "patterns"
    status: null,
    loading: false,
    _initialized: false,

    init() {
        if (this._initialized) return;
        this._initialized = true;
    },

    async open() {
        this.loading = true;
        await this.refresh();
        this.loading = false;
    },

    async refresh() {
        try {
            const result = await callJsonApi("/stomper_status", {});
            this.status = result;
        } catch (e) {
            console.error("Stomper status fetch failed:", e);
        }
    },

    cleanup() {
        this.activeTab = "log";
        this.status = null;
    },

    setTab(tab) {
        this.activeTab = tab;
    },
};

export const store = createStore("stomperDashboard", model);
