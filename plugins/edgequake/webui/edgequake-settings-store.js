import { createStore } from "/js/AlpineStore.js";
import * as API from "/js/api.js";

const model = {
  // Settings state
  base_url: "http://localhost:8080",
  api_key: "",
  workspace_id: "",
  tenant_id: "",
  timeout: 30,

  // Phase 3: Pipeline settings
  auto_index: false,
  index_batch_size: 5,
  auto_recall: false,
  recall_timeout: 3,

  // UI state
  loading: false,
  connection_status: null, // null | "testing" | "connected" | "error"
  connection_info: "",
  show_api_key: false,

  // Server management state
  server_running: false,
  server_starting: false,
  server_stopping: false,
  docker_available: false,
  server_health: null,
  server_error: "",
  _statusPollTimer: null,

  async load() {
    this.loading = true;
    try {
      const response = await API.callJsonApi(
        "/api/plugins/edgequake/edgequake_settings",
        { action: "load" }
      );
      if (response && response.settings) {
        this.base_url = response.settings.base_url || "http://localhost:8080";
        this.api_key = response.settings.api_key || "";
        this.workspace_id = response.settings.workspace_id || "";
        this.tenant_id = response.settings.tenant_id || "";
        this.timeout = response.settings.timeout || 30;
        this.auto_index = response.settings.auto_index ?? false;
        this.index_batch_size = response.settings.index_batch_size ?? 5;
        this.auto_recall = response.settings.auto_recall ?? false;
        this.recall_timeout = response.settings.recall_timeout ?? 3;
      }
    } catch (e) {
      console.error("EdgeQuake: failed to load settings:", e);
    } finally {
      this.loading = false;
    }
    // Check server status on load
    this.checkServerStatus();
  },

  async save() {
    this.loading = true;
    try {
      const response = await API.callJsonApi(
        "/api/plugins/edgequake/edgequake_settings",
        {
          action: "save",
          settings: {
            base_url: this.base_url,
            api_key: this.api_key,
            workspace_id: this.workspace_id,
            tenant_id: this.tenant_id,
            timeout: this.timeout,
            auto_index: this.auto_index,
            index_batch_size: this.index_batch_size,
            auto_recall: this.auto_recall,
            recall_timeout: this.recall_timeout,
          },
        }
      );
      if (response && response.success) {
        window.closeModal("../plugins/edgequake/webui/edgequake-settings.html");
      } else if (response && response.error) {
        alert("Save failed: " + response.error);
      }
    } catch (e) {
      console.error("EdgeQuake: failed to save settings:", e);
      alert("Failed to save settings: " + e.message);
    } finally {
      this.loading = false;
    }
  },

  async testConnection() {
    this.connection_status = "testing";
    this.connection_info = "";
    try {
      const response = await API.callJsonApi(
        "/api/plugins/edgequake/edgequake_settings",
        {
          action: "test",
          settings: {
            base_url: this.base_url,
            api_key: this.api_key,
            workspace_id: this.workspace_id,
            tenant_id: this.tenant_id,
            timeout: this.timeout,
          },
        }
      );
      if (response && response.error) {
        this.connection_status = "error";
        this.connection_info = response.error;
      } else if (response && response.status) {
        this.connection_status = "connected";
        this.connection_info = `${response.status} | v${response.version} | ${response.storage_mode} | ${response.llm_provider_name}`;
      } else {
        this.connection_status = "error";
        this.connection_info = "Unexpected response";
      }
    } catch (e) {
      this.connection_status = "error";
      this.connection_info = e.message || "Connection failed";
    }
  },

  // --- Server management ---

  async generateKey() {
    try {
      const response = await API.callJsonApi(
        "/api/plugins/edgequake/edgequake_settings",
        { action: "generate_key" }
      );
      if (response && response.api_key) {
        this.api_key = response.api_key;
        this.show_api_key = true;
      }
    } catch (e) {
      console.error("EdgeQuake: failed to generate key:", e);
    }
  },

  async startServer() {
    this.server_starting = true;
    this.server_error = "";
    try {
      const response = await API.callJsonApi(
        "/api/plugins/edgequake/edgequake_settings",
        {
          action: "start_server",
          settings: {
            base_url: this.base_url,
            api_key: this.api_key,
          },
        }
      );
      if (response && response.error) {
        this.server_error = response.error;
        this.server_starting = false;
      } else {
        // Poll status until healthy or timeout
        this._startStatusPoll();
      }
    } catch (e) {
      this.server_error = e.message || "Failed to start server";
      this.server_starting = false;
    }
  },

  async stopServer() {
    this.server_stopping = true;
    this.server_error = "";
    try {
      const response = await API.callJsonApi(
        "/api/plugins/edgequake/edgequake_settings",
        { action: "stop_server" }
      );
      if (response && response.error) {
        this.server_error = response.error;
      } else {
        this.server_running = false;
        this.server_health = null;
      }
    } catch (e) {
      this.server_error = e.message || "Failed to stop server";
    } finally {
      this.server_stopping = false;
    }
  },

  async checkServerStatus() {
    try {
      const response = await API.callJsonApi(
        "/api/plugins/edgequake/edgequake_settings",
        { action: "server_status" }
      );
      if (response) {
        this.docker_available = response.docker_available ?? false;
        this.server_running = response.running ?? false;
        this.server_health = response.health;
        if (this.server_running && this.server_health) {
          this.server_starting = false;
        }
      }
    } catch (e) {
      console.error("EdgeQuake: failed to check server status:", e);
    }
  },

  _startStatusPoll() {
    this._stopStatusPoll();
    let attempts = 0;
    const maxAttempts = 40; // ~2 minutes at 3s intervals
    this._statusPollTimer = setInterval(async () => {
      attempts++;
      await this.checkServerStatus();
      if (this.server_running && this.server_health) {
        this.server_starting = false;
        this._stopStatusPoll();
      } else if (attempts >= maxAttempts) {
        this.server_starting = false;
        this.server_error = "Server did not become healthy within 2 minutes.";
        this._stopStatusPoll();
      }
    }, 3000);
  },

  _stopStatusPoll() {
    if (this._statusPollTimer) {
      clearInterval(this._statusPollTimer);
      this._statusPollTimer = null;
    }
  },

  destroy() {
    this._stopStatusPoll();
    this.connection_status = null;
    this.connection_info = "";
    this.show_api_key = false;
    this.server_starting = false;
    this.server_stopping = false;
    this.server_error = "";
  },
};

export const store = createStore("edgequakeSettings", model);
