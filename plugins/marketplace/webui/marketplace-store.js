import { createStore } from "/js/AlpineStore.js";
import * as API from "/js/api.js";
import { closeModal } from "/js/modals.js";
import { store as notificationStore } from "/components/notifications/notification-store.js";

const MARKETPLACE_API = "/plugins/marketplace";

function toast(text, type = "info", timeout = 5000) {
    notificationStore.addFrontendToastOnly(type, text, "", timeout / 1000);
}

const marketplaceStore = {
    // Data
    plugins: [],
    filteredPlugins: [],

    // State
    loading: false,
    error: null,
    activeFilter: "all", // all | featured | popular | installed
    searchQuery: "",

    // Action in progress
    actionInProgress: {}, // { [pluginId]: "installing" | "uninstalling" | "toggling" }

    _initialized: false,

    init() {
        if (this._initialized) return;
        this._initialized = true;
    },

    async onOpen() {
        this.error = null;
        await this.fetchRegistry();
    },

    cleanup() {
        // Reset transient state
        this.actionInProgress = {};
    },

    // --- Data fetching ---

    async fetchRegistry() {
        this.loading = true;
        this.error = null;
        try {
            const resp = await API.callJsonApi(`${MARKETPLACE_API}/marketplace_registry`, {});
            if (resp.ok) {
                this.plugins = resp.plugins || [];
                this.applyFilter();
            } else {
                this.error = resp.error || "Failed to load registry.";
            }
        } catch (e) {
            this.error = "Failed to connect to registry.";
        } finally {
            this.loading = false;
        }
    },

    // --- Filtering ---

    applyFilter() {
        let list = [...this.plugins];

        // Search
        if (this.searchQuery.trim()) {
            const q = this.searchQuery.toLowerCase().trim();
            list = list.filter(p =>
                p.name.toLowerCase().includes(q) ||
                p.description.toLowerCase().includes(q) ||
                (p.tags || []).some(t => t.toLowerCase().includes(q))
            );
        }

        // Tab filter
        switch (this.activeFilter) {
            case "featured":
                list = list.filter(p => p.featured);
                break;
            case "popular":
                list = list.sort((a, b) => (b.install_count || 0) - (a.install_count || 0));
                break;
            case "installed":
                list = list.filter(p => p.status !== "available");
                break;
        }

        this.filteredPlugins = list;
    },

    setFilter(filter) {
        this.activeFilter = filter;
        this.applyFilter();
    },

    onSearchInput() {
        this.applyFilter();
    },

    // --- Actions ---

    async installPlugin(plugin) {
        if (this.actionInProgress[plugin.id]) return;
        this.actionInProgress[plugin.id] = "installing";
        // Force reactivity
        this.actionInProgress = { ...this.actionInProgress };

        try {
            const resp = await API.callJsonApi(`${MARKETPLACE_API}/marketplace_install`, {
                plugin_id: plugin.id,
                repo_url: plugin.repo_url,
                plugin_path: plugin.plugin_path,
                branch: plugin.branch || "",
            });
            if (resp.ok) {
                toast(`${plugin.name} installed successfully!`, "success");
                await this.fetchRegistry();
            } else {
                toast(`Install failed: ${resp.error || "Unknown error"}`, "error");
            }
        } catch (e) {
            toast("Install failed. Check your connection.", "error");
        } finally {
            delete this.actionInProgress[plugin.id];
            this.actionInProgress = { ...this.actionInProgress };
        }
    },

    async uninstallPlugin(plugin) {
        if (this.actionInProgress[plugin.id]) return;
        this.actionInProgress[plugin.id] = "uninstalling";
        this.actionInProgress = { ...this.actionInProgress };

        try {
            const resp = await API.callJsonApi(`${MARKETPLACE_API}/marketplace_uninstall`, {
                plugin_id: plugin.id,
            });
            if (resp.ok) {
                toast(`${plugin.name} uninstalled.`, "info");
                await this.fetchRegistry();
            } else {
                toast(`Uninstall failed: ${resp.error || "Unknown error"}`, "error");
            }
        } catch (e) {
            toast("Uninstall failed.", "error");
        } finally {
            delete this.actionInProgress[plugin.id];
            this.actionInProgress = { ...this.actionInProgress };
        }
    },

    async togglePlugin(plugin) {
        if (this.actionInProgress[plugin.id]) return;
        const newEnabled = plugin.status === "inactive";
        this.actionInProgress[plugin.id] = "toggling";
        this.actionInProgress = { ...this.actionInProgress };

        try {
            const resp = await API.callJsonApi(`${MARKETPLACE_API}/marketplace_toggle`, {
                plugin_id: plugin.id,
                enabled: newEnabled,
            });
            if (resp.ok) {
                toast(`${plugin.name} ${newEnabled ? "activated" : "deactivated"}.`, "info");
                await this.fetchRegistry();
            } else {
                toast(`Toggle failed: ${resp.error || "Unknown error"}`, "error");
            }
        } catch (e) {
            toast("Toggle failed.", "error");
        } finally {
            delete this.actionInProgress[plugin.id];
            this.actionInProgress = { ...this.actionInProgress };
        }
    },

    // --- Helpers ---

    isActionInProgress(pluginId) {
        return !!this.actionInProgress[pluginId];
    },

    getActionLabel(pluginId) {
        return this.actionInProgress[pluginId] || "";
    },
};

export const store = createStore("marketplace", marketplaceStore);
