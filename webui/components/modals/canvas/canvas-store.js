import { createStore } from "/js/AlpineStore.js";
import { callJsonApi } from "/js/api.js";

const model = {
  // State
  isRunning: false,
  url: null,
  port: null,
  workspace: null,
  browserReady: false,
  files: [],
  loading: false,
  error: null,
  closePromise: null,
  refreshIntervalId: null,

  /**
   * Open canvas modal and start workspace
   */
  async open(ctxid) {
    this.ctxid = ctxid || window.currentContextId;
    this.loading = true;
    this.error = null;

    try {
      // Start canvas workspace
      const result = await callJsonApi("/canvas", {
        action: "start",
        ctxid: this.ctxid,
        headless: true,
        auto_reload: true,
      });

      if (result.status === "ok") {
        this.isRunning = true;
        this.url = result.url;
        this.port = result.port;
        this.workspace = result.workspace;
        this.browserReady = result.browser_ready;

        // Open modal
        this.closePromise = window.openModal("modals/canvas/canvas-modal.html");

        // Setup cleanup on modal close
        if (this.closePromise && typeof this.closePromise.finally === "function") {
          this.closePromise.finally(() => {
            this.stopRefresh();
          });
        }

        // Start file list refresh
        this.startRefresh();

        // Load initial file list
        await this.loadFiles();
      } else {
        this.error = result.message || "Failed to start canvas";
      }
    } catch (e) {
      console.error("Canvas open error:", e);
      this.error = e.message || "Failed to open canvas";
    } finally {
      this.loading = false;
    }
  },

  /**
   * Close canvas and cleanup
   */
  async close() {
    this.stopRefresh();

    try {
      await callJsonApi("/canvas", {
        action: "stop",
        ctxid: this.ctxid,
      });
    } catch (e) {
      console.error("Canvas close error:", e);
    }

    this.resetState();

    // Close modal if open
    if (window.closeModal) {
      window.closeModal();
    }
  },

  /**
   * Get current status
   */
  async getStatus() {
    try {
      const result = await callJsonApi("/canvas", {
        action: "status",
        ctxid: this.ctxid,
      });

      if (result.status === "ok") {
        this.isRunning = result.running;
        this.url = result.url;
        this.port = result.port;
        this.workspace = result.workspace;
        this.browserReady = result.browser_ready;
      }

      return result;
    } catch (e) {
      console.error("Canvas status error:", e);
      return null;
    }
  },

  /**
   * Load file list from workspace
   */
  async loadFiles() {
    try {
      const result = await callJsonApi("/canvas", {
        action: "files",
        ctxid: this.ctxid,
      });

      if (result.status === "ok") {
        this.files = result.files || [];
      }
    } catch (e) {
      console.error("Canvas files error:", e);
    }
  },

  /**
   * Take screenshot
   */
  async screenshot(selector = null) {
    try {
      const result = await callJsonApi("/canvas", {
        action: "screenshot",
        ctxid: this.ctxid,
        selector: selector,
      });

      if (result.status === "ok") {
        return result.path;
      }

      return null;
    } catch (e) {
      console.error("Canvas screenshot error:", e);
      return null;
    }
  },

  /**
   * Navigate to path
   */
  async navigate(path) {
    try {
      const result = await callJsonApi("/canvas", {
        action: "navigate",
        ctxid: this.ctxid,
        path: path,
      });

      return result;
    } catch (e) {
      console.error("Canvas navigate error:", e);
      return null;
    }
  },

  /**
   * Reload iframe
   */
  reloadIframe() {
    const iframe = document.querySelector("#canvas-preview-iframe");
    if (iframe) {
      iframe.src = iframe.src;
    }
  },

  /**
   * Start auto-refresh for file list
   */
  startRefresh() {
    this.stopRefresh();
    this.refreshIntervalId = setInterval(() => {
      this.loadFiles();
    }, 2000);
  },

  /**
   * Stop auto-refresh
   */
  stopRefresh() {
    if (this.refreshIntervalId) {
      clearInterval(this.refreshIntervalId);
      this.refreshIntervalId = null;
    }
  },

  /**
   * Reset state
   */
  resetState() {
    this.isRunning = false;
    this.url = null;
    this.port = null;
    this.workspace = null;
    this.browserReady = false;
    this.files = [];
    this.loading = false;
    this.error = null;
  },

  /**
   * Get iframe URL with cache bust
   */
  getIframeUrl() {
    if (!this.url) return "";
    return `${this.url}?t=${Date.now()}`;
  },
};

export const store = createStore("canvasStore", model);
