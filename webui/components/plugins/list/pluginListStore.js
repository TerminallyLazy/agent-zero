import { createStore } from "/js/AlpineStore.js";
import * as api from "/js/api.js";
import "/components/plugins/plugin-settings-store.js";
import {
  store as notificationStore,
  defaultPriority,
} from "/components/notifications/notification-store.js";

// define the model object holding data and functions
const model = {
  loading: false,
  plugins: [],
  selectedPlugin: null,
  activeTab: "custom",

  async init() {
    await this.setTab('custom');
    if (this.plugins.length === 0) {
        await this.setTab('builtin');
    }
  },

  async loadPluginList(filter) {
    this.loading = true;
    this.selectedPlugin = null;
    try {
      const response = await api.callJsonApi("plugins_list", { filter });
      this.plugins = Array.isArray(response.plugins) ? response.plugins : [];
    } catch (e) {
      this.plugins = [];
      showErrorNotification(e, "Failed to load plugins list");
    } finally {
      this.loading = false;
    }
  },

  async setTab(tab) {
    this.activeTab = tab === "builtin" ? "builtin" : "custom";
    const filter =
      this.activeTab === "builtin"
        ? { builtin: true, custom: false, search: "" }
        : { builtin: false, custom: true, search: "" };
    await this.loadPluginList(filter);
  },

  async refresh() {
    await this.setTab(this.activeTab);
  },

  openPlugin(plugin) {
    if (!plugin?.name || !plugin?.has_main_screen) return;
    window.openModal?.(`/plugins/${plugin.name}/webui/main.html`);
  },

  async openPluginConfig(plugin) {
    if (!plugin?.name || !plugin?.has_config_screen) return;
    try {
      const pluginSettingsStore = Alpine.store("pluginSettings");
      if (!pluginSettingsStore?.open) {
        throw new Error("Plugin settings store is unavailable.");
      }
      await pluginSettingsStore.open(plugin.name);
      window.openModal?.("components/plugins/plugin-settings.html");
    } catch (e) {
      showErrorNotification(e, "Failed to open plugin config");
    }
  },

  openPluginInfo(plugin) {
    if (!plugin) return;
    this.selectedPlugin = plugin;
    window.openModal?.("components/plugins/plugin-info.html");
  },

  async deletePlugin(plugin) {
    if (!plugin?.path) return;

    if (!plugin.is_custom) {
      showErrorNotification(
        new Error("Only custom plugins can be deleted from this modal."),
        "Delete blocked",
      );
      return;
    }

    try {
      const response = await api.callJsonApi("delete_work_dir_file", {
        path: plugin.path,
        currentPath: "/",
      });
      if (response?.error) {
        throw new Error(response.error);
      }
      if (window.toastFrontendSuccess) {
        window.toastFrontendSuccess("Plugin deleted", "Plugins");
      }
      await this.refresh();
    } catch (e) {
      showErrorNotification(e, "Failed to delete plugin");
    }
  },
};

function showErrorNotification(error, heading) {
    const text = error.message || error.text || JSON.stringify(error);
  notificationStore.frontendError(
    text,
    heading,
    3,
    "pluginsList",
    defaultPriority,
    true,
  );
}

// convert it to alpine store
const store = createStore("pluginListStore", model);

// export for use in other files
export { store };
