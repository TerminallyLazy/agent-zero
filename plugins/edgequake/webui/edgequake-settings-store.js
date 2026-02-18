import { createStore } from "/js/AlpineStore.js";
import * as API from "/js/api.js";

const model = {
  // Settings state
  base_url: "http://localhost:8080",
  api_key: "",
  workspace_id: "",
  tenant_id: "",
  timeout: 30,

  // UI state
  loading: false,
  connection_status: null, // null | "testing" | "connected" | "error"
  connection_info: "",
  show_api_key: false,

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
      }
    } catch (e) {
      console.error("EdgeQuake: failed to load settings:", e);
    } finally {
      this.loading = false;
    }
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

  destroy() {
    this.connection_status = null;
    this.connection_info = "";
    this.show_api_key = false;
  },
};

export const store = createStore("edgequakeSettings", model);
