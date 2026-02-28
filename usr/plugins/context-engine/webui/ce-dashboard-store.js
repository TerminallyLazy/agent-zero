import { createStore } from "/js/AlpineStore.js";
import * as API from "/js/api.js";
import { store as notificationStore } from "/components/notifications/notification-store.js";

const SEARCH_API = "/plugins/context-engine/search";
const STATUS_API = "/plugins/context-engine/status";
const INDEX_API = "/plugins/context-engine/index";

function justToast(text, type = "info", timeout = 5000) {
  notificationStore.addFrontendToastOnly(type, text, "", timeout / 1000);
}

const ceDashboardStore = {
  // Search state
  searchQuery: "",
  searchResults: [],
  searchLanguage: "",
  searchPathFilter: "",
  searchLimit: 10,
  searching: false,
  searchError: null,

  // Status state
  connected: false,
  statusInfo: null,
  statusLoading: false,
  statusError: null,

  // Index state
  indexPath: "",
  indexing: false,
  indexError: null,

  // Pagination
  currentPage: 1,
  itemsPerPage: 10,

  // Active tab
  activeTab: "search",

  init() {},

  async onOpen() {
    await this.checkStatus();
  },

  cleanup() {
    this.searchResults = [];
    this.searchQuery = "";
    this.searchError = null;
    this.statusInfo = null;
    this.statusError = null;
    this.indexError = null;
    this.currentPage = 1;
  },

  // --- Status ---

  async checkStatus() {
    this.statusLoading = true;
    this.statusError = null;
    try {
      const response = await API.callJsonApi(STATUS_API, {});
      if (response.ok) {
        this.connected = true;
        this.statusInfo = response;
      } else {
        this.connected = false;
        this.statusError = response.error || "Failed to connect";
      }
    } catch (e) {
      this.connected = false;
      this.statusError = e.message || "Connection failed";
    } finally {
      this.statusLoading = false;
    }
  },

  // --- Search ---

  async search() {
    const query = this.searchQuery.trim();
    if (!query) return;

    this.searching = true;
    this.searchError = null;
    this.currentPage = 1;

    try {
      const payload = {
        query,
        limit: this.searchLimit,
      };
      if (this.searchLanguage) payload.language = this.searchLanguage;
      if (this.searchPathFilter) payload.path_filter = this.searchPathFilter;

      const response = await API.callJsonApi(SEARCH_API, payload);
      if (response.ok) {
        this.searchResults = response.results || [];
      } else {
        this.searchError = response.error || "Search failed";
        this.searchResults = [];
      }
    } catch (e) {
      this.searchError = e.message || "Search failed";
      this.searchResults = [];
    } finally {
      this.searching = false;
    }
  },

  clearSearch() {
    this.searchQuery = "";
    this.searchLanguage = "";
    this.searchPathFilter = "";
    this.searchResults = [];
    this.searchError = null;
    this.currentPage = 1;
  },

  // --- Indexing ---

  async triggerIndex() {
    const path = this.indexPath.trim();
    if (!path) {
      justToast("Please enter a path to index", "warning");
      return;
    }

    this.indexing = true;
    this.indexError = null;

    try {
      const response = await API.callJsonApi(INDEX_API, { path });
      if (response.ok) {
        justToast(response.message || "Indexing started", "success");
        this.indexPath = "";
        // Refresh status after indexing
        await this.checkStatus();
      } else {
        this.indexError = response.error || "Indexing failed";
        justToast(this.indexError, "error");
      }
    } catch (e) {
      this.indexError = e.message || "Indexing failed";
      justToast(this.indexError, "error");
    } finally {
      this.indexing = false;
    }
  },

  // --- Pagination ---

  get totalPages() {
    return Math.max(1, Math.ceil(this.searchResults.length / this.itemsPerPage));
  },

  get paginatedResults() {
    const start = (this.currentPage - 1) * this.itemsPerPage;
    return this.searchResults.slice(start, start + this.itemsPerPage);
  },

  nextPage() {
    if (this.currentPage < this.totalPages) this.currentPage++;
  },

  prevPage() {
    if (this.currentPage > 1) this.currentPage--;
  },

  // --- Utilities ---

  copySnippet(text) {
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard
        .writeText(text)
        .then(() => justToast("Copied to clipboard", "success"))
        .catch(() => this.fallbackCopy(text));
    } else {
      this.fallbackCopy(text);
    }
  },

  fallbackCopy(text) {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.left = "-999999px";
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand("copy");
      justToast("Copied to clipboard", "success");
    } catch {
      justToast("Failed to copy", "error");
    }
    document.body.removeChild(ta);
  },

  getScoreBadgeClass(score) {
    if (score >= 0.8) return "score-high";
    if (score >= 0.5) return "score-medium";
    return "score-low";
  },

  formatScore(score) {
    if (typeof score !== "number") return "—";
    return (score * 100).toFixed(0) + "%";
  },
};

const store = createStore("ceDashboardStore", ceDashboardStore);

export { store };
