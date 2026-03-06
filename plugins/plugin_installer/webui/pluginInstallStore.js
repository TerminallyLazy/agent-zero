import { createStore } from "/js/AlpineStore.js";
import * as api from "/js/api.js";
import { showConfirmDialog } from "/js/confirmDialog.js";

const PLUGIN_API = "plugins/plugin_installer/plugin_install";
const PER_PAGE = 20;

const SECURITY_WARNING = {
  title: "Security Warning",
  message: `
    <p><strong>Installing plugins from untrusted sources may pose security risks:</strong></p>
    <ul style="margin: 0.75em 0; padding-left: 1.5em;">
      <li>Malicious code execution</li>
      <li>Exposure of sensitive data</li>
      <li>System compromise</li>
    </ul>
    <p style="margin-top: 0.75em;">Only install plugins from sources you trust.</p>
  `,
  type: "warning",
  confirmText: "Install Anyway",
  cancelText: "Cancel",
};

const model = {
  // ZIP install state
  zipFile: null,
  zipFileName: "",

  // Git install state
  gitUrl: "",
  gitToken: "",

  // Index state
  index: null,
  installedPlugins: [],
  search: "",
  page: 1,
  sortBy: "stars",
  selectedPlugin: null,

  // Shared state
  loading: false,
  loadingMessage: "",
  error: "",
  result: null,

  // Tab state
  activeTab: "store",

  setTab(tab) {
    this.activeTab = tab;
    this.error = "";
    this.result = null;
  },

  // ── ZIP Install ──────────────────────────────

  handleFileUpload(event) {
    const file = event.target.files[0];
    if (!file) return;
    this.zipFile = file;
    this.zipFileName = file.name;
    this.error = "";
    this.result = null;
  },

  async installZip() {
    if (!this.zipFile) {
      this.error = "Please select a ZIP file first";
      return;
    }

    const confirmed = await showConfirmDialog(SECURITY_WARNING);
    if (!confirmed) return;

    try {
      this.loading = true;
      this.loadingMessage = "Installing plugin from ZIP...";
      this.error = "";
      this.result = null;

      const formData = new FormData();
      formData.append("action", "install_zip");
      formData.append("plugin_file", this.zipFile);

      const response = await api.fetchApi(PLUGIN_API, {
        method: "POST",
        body: formData,
      });

      const data = await response.json();
      if (!data.success) {
        this.error = data.error || "Installation failed";
        return;
      }

      this.result = data;
      if (window.toastFrontendSuccess) {
        window.toastFrontendSuccess(
          `Plugin "${data.title || data.plugin_name}" installed`,
          "Plugin Installer"
        );
      }
      this._refreshPluginList();
    } catch (e) {
      this.error = `Installation error: ${e.message}`;
    } finally {
      this.loading = false;
      this.loadingMessage = "";
    }
  },

  // ── Git Install ──────────────────────────────

  async installGit() {
    const url = (this.gitUrl || "").trim();
    if (!url) {
      this.error = "Please enter a Git URL";
      return;
    }

    const confirmed = await showConfirmDialog(SECURITY_WARNING);
    if (!confirmed) return;

    try {
      this.loading = true;
      this.loadingMessage = "Cloning repository...";
      this.error = "";
      this.result = null;

      const data = await api.callJsonApi(PLUGIN_API, {
        action: "install_git",
        git_url: url,
        git_token: this.gitToken || "",
      });

      if (!data.success) {
        this.error = data.error || "Clone failed";
        return;
      }

      this.result = data;
      if (window.toastFrontendSuccess) {
        window.toastFrontendSuccess(
          `Plugin "${data.title || data.plugin_name}" installed`,
          "Plugin Installer"
        );
      }
      this._refreshPluginList();
    } catch (e) {
      this.error = `Clone error: ${e.message}`;
    } finally {
      this.loading = false;
      this.loadingMessage = "";
    }
  },

  // ── Index Browse ─────────────────────────────

  async fetchIndex() {
    try {
      this.loading = true;
      this.loadingMessage = "Loading plugin index...";
      this.error = "";
      this.index = null;

      const data = await api.callJsonApi(PLUGIN_API, {
        action: "fetch_index",
      });

      if (!data.success) {
        this.error = data.error || "Failed to load index";
        return;
      }

      this.index = data.index;
      this.installedPlugins = data.installed_plugins || [];
      this.page = 1;
    } catch (e) {
      this.error = `Failed to load plugin index: ${e.message}`;
    } finally {
      this.loading = false;
      this.loadingMessage = "";
    }
  },

  get pluginsList() {
    if (!this.index?.plugins) return [];
    return Object.entries(this.index.plugins).map(([key, val]) => ({
      key,
      ...val,
      installed: this.installedPlugins.includes(key),
    }));
  },

  get filteredPlugins() {
    let list = this.pluginsList;
    const q = (this.search || "").toLowerCase().trim();
    if (q) {
      list = list.filter(
        (p) =>
          (p.title || "").toLowerCase().includes(q) ||
          (p.description || "").toLowerCase().includes(q) ||
          (p.key || "").toLowerCase().includes(q) ||
          (p.tags || []).some((t) => t.toLowerCase().includes(q))
      );
    }
    if (this.sortBy === "stars") {
      list.sort((a, b) => (b.stars || 0) - (a.stars || 0));
    } else {
      list.sort((a, b) =>
        (a.title || a.key).localeCompare(b.title || b.key)
      );
    }
    return list;
  },

  get totalPages() {
    return Math.max(1, Math.ceil(this.filteredPlugins.length / PER_PAGE));
  },

  get paginatedPlugins() {
    const start = (this.page - 1) * PER_PAGE;
    return this.filteredPlugins.slice(start, start + PER_PAGE);
  },

  setPage(p) {
    this.page = Math.max(1, Math.min(p, this.totalPages));
  },

  openDetail(plugin) {
    this.selectedPlugin = plugin;
    this.error = "";
    this.result = null;
    this.installedPluginInfo = null;
    if (plugin.installed) {
      this.fetchInstalledPluginInfo(plugin.key);
    }
    window.openModal?.("../plugins/plugin_installer/webui/install-detail.html");
  },

  async installFromIndex(plugin) {
    if (!plugin?.github) {
      this.error = "No GitHub URL available for this plugin";
      return;
    }

    const confirmed = await showConfirmDialog(SECURITY_WARNING);
    if (!confirmed) return;

    try {
      this.loading = true;
      this.loadingMessage = `Installing ${plugin.title || plugin.key}...`;
      this.error = "";
      this.result = null;

      const data = await api.callJsonApi(PLUGIN_API, {
        action: "install_git",
        git_url: plugin.github,
      });

      if (!data.success) {
        this.error = data.error || "Installation failed";
        return;
      }

      this.result = data;
      if (!this.installedPlugins.includes(plugin.key)) {
        this.installedPlugins.push(plugin.key);
      }
      plugin.installed = true;

      if (window.toastFrontendSuccess) {
        window.toastFrontendSuccess(
          `Plugin "${data.title || data.plugin_name}" installed`,
          "Plugin Installer"
        );
      }
      this._refreshPluginList();
    } catch (e) {
      this.error = `Installation error: ${e.message}`;
    } finally {
      this.loading = false;
      this.loadingMessage = "";
    }
  },

  // ── Installed Plugin Info ─────────────────────

  installedPluginInfo: null,
  installedPluginInfoLoading: false,

  async fetchInstalledPluginInfo(pluginKey) {
    this.installedPluginInfo = null;
    this.installedPluginInfoLoading = true;
    try {
      const response = await api.callJsonApi("plugins_list", {
        filter: { custom: true, builtin: true, search: "" },
      });
      const plugins = Array.isArray(response.plugins) ? response.plugins : [];
      this.installedPluginInfo = plugins.find(
        (p) => p.name === pluginKey
      ) || null;
    } catch (e) {
      this.installedPluginInfo = null;
    } finally {
      this.installedPluginInfoLoading = false;
    }
  },

  manageOpenPlugin() {
    const info = this.installedPluginInfo;
    if (!info?.name || !info?.has_main_screen) return;
    window.openModal?.(`/plugins/${info.name}/webui/main.html`);
  },

  async manageOpenConfig() {
    const pls = Alpine.store("pluginListStore");
    if (pls?.openPluginConfig && this.installedPluginInfo) {
      await pls.openPluginConfig(this.installedPluginInfo);
    }
  },

  async manageOpenDoc(doc) {
    const pls = Alpine.store("pluginListStore");
    if (pls?.openPluginDoc && this.installedPluginInfo) {
      await pls.openPluginDoc(this.installedPluginInfo, doc);
    }
  },

  manageOpenInfo() {
    const pls = Alpine.store("pluginListStore");
    if (pls?.openPluginInfo && this.installedPluginInfo) {
      pls.openPluginInfo(this.installedPluginInfo);
    }
  },

  async manageDeletePlugin() {
    const pls = Alpine.store("pluginListStore");
    if (pls?.deletePlugin && this.installedPluginInfo) {
      await pls.deletePlugin(this.installedPluginInfo);
      // Mark as no longer installed in the index view
      if (this.selectedPlugin) {
        this.selectedPlugin.installed = false;
        const idx = this.installedPlugins.indexOf(this.selectedPlugin.key);
        if (idx !== -1) this.installedPlugins.splice(idx, 1);
      }
      this.installedPluginInfo = null;
    }
  },

  // ── Shared ───────────────────────────────────

  resetZip() {
    this.zipFile = null;
    this.zipFileName = "";
    this.error = "";
    this.result = null;
  },

  resetGit() {
    this.gitUrl = "";
    this.gitToken = "";
    this.error = "";
    this.result = null;
  },

  resetIndex() {
    this.search = "";
    this.page = 1;
    this.sortBy = "stars";
    this.error = "";
    this.result = null;
    this.selectedPlugin = null;
  },

  _refreshPluginList() {
    window.dispatchEvent(new CustomEvent("plugin-modal-closed"));
  },

  truncate(text, max) {
    if (!text || text.length <= max) return text || "";
    return text.substring(0, max) + "...";
  },
};

const store = createStore("pluginInstallStore", model);
export { store };
