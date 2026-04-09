/* Headless Mode config page store — plain script, not ES module.
   Uses globalThis.* directly (not captured at top level) to avoid
   load-order fragility with index.js initialization. */

const _API_BASE = "/api/plugins/headless_mode/";

window.createHeadlessConfigModel = (context, config) => ({
  // --- Health check ---
  healthChecking: false,
  healthResult: null,

  // --- Dependency check ---
  depsChecking: false,
  depsResult: null,

  // --- Execute panel ---
  executing: false,
  executeMessage: "",
  executeEphemeral: true,
  executeContextId: "",
  executeResult: null,

  // --- Command builder (independent toggles) ---
  cmdMessage: "",
  cmdContextId: "",
  cmdInteractive: false,
  cmdJsonOutput: false,
  cmdEphemeral: false,

  // --- Lifecycle ---
  init() {
    this.healthResult = config.last_health_check || null;
    this.depsResult = config.last_dependency_check || null;
  },

  // --- API helper ---
  async apiCall(endpoint, data) {
    try {
      const resp = await globalThis.fetchApi(_API_BASE + endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify(data || {}),
      });
      if (!resp.ok) {
        const text = await resp.text();
        throw new Error(text || `HTTP ${resp.status}`);
      }
      return await resp.json();
    } catch (e) {
      globalThis.toastFrontendError(e.message || "API call failed", "Headless Mode");
      return { ok: false, error: e.message || "API call failed" };
    }
  },

  // --- Health check ---
  async runHealthCheck() {
    this.healthChecking = true;
    try {
      const result = await this.apiCall("health_check", {});
      this.healthResult = result;
      if (result.ok) {
        globalThis.toastFrontendSuccess("Health check passed", "Headless Mode");
      } else {
        globalThis.toastFrontendError(result.details || "Health check failed", "Headless Mode");
      }
    } finally {
      this.healthChecking = false;
    }
  },

  // --- Dependency check ---
  async runDependencyCheck() {
    this.depsChecking = true;
    try {
      const result = await this.apiCall("dependency_status", {});
      this.depsResult = result;
      if (result.ok) {
        globalThis.toastFrontendSuccess("All dependencies OK", "Headless Mode");
      } else {
        const failed = (result.results || []).filter((r) => !r.ok).map((r) => r.name);
        globalThis.toastFrontendError("Issues: " + failed.join(", "), "Headless Mode");
      }
    } finally {
      this.depsChecking = false;
    }
  },

  // --- Execute ---
  async executeHeadlessRun() {
    const msg = this.executeMessage.trim();
    if (!msg) {
      globalThis.toastFrontendError("Message cannot be empty", "Headless Mode");
      return;
    }
    this.executing = true;
    this.executeResult = null;
    try {
      const result = await this.apiCall("run_message", {
        message: msg,
        ephemeral: this.executeEphemeral,
        context_id: this.executeContextId || "",
      });
      this.executeResult = result;
      if (result.ok) {
        globalThis.toastFrontendSuccess("Message executed", "Headless Mode");
      }
    } finally {
      this.executing = false;
    }
  },

  // --- Command builder ---
  get generatedCommand() {
    const parts = ["python3 -m usr.plugins.headless_mode.cli"];
    if (this.cmdInteractive) {
      parts.push("--interactive");
    } else if (this.cmdMessage.trim()) {
      parts.push("--message", JSON.stringify(this.cmdMessage.trim()));
    }
    if (this.cmdJsonOutput) {
      parts.push("--output-format json");
    }
    if (this.cmdContextId.trim()) {
      parts.push("--context", this.cmdContextId.trim());
    }
    if (this.cmdEphemeral) {
      parts.push("--ephemeral");
    }
    return parts.join(" ");
  },

  async copyCommand() {
    try {
      await navigator.clipboard.writeText(this.generatedCommand);
      globalThis.toastFrontendSuccess("Command copied to clipboard", "Headless Mode");
    } catch {
      globalThis.toastFrontendError("Failed to copy — check browser permissions", "Headless Mode");
    }
  },

  // --- Helpers ---
  relativeTime(isoString) {
    if (!isoString) return "Never";
    const diff = Date.now() - new Date(isoString).getTime();
    const seconds = Math.floor(diff / 1000);
    if (seconds < 60) return "just now";
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
  },
});
