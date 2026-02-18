import { createStore } from "/js/AlpineStore.js";
import * as API from "/js/api.js";

const ENDPOINT = "/api/plugins/edgequake/edgequake_query";
const VALID_MODES = ["naive", "local", "global", "hybrid", "mix", "bypass"];

const model = {
  // Query state
  queryText: "",
  mode: "hybrid",
  querying: false,

  // Result
  answer: "",
  sources: [],

  // History (session-scoped)
  history: [],

  // Error
  errorMessage: "",

  // Mode options for the dropdown
  modes: VALID_MODES,

  async execute() {
    const query = this.queryText.trim();
    if (!query) return;

    this.querying = true;
    this.errorMessage = "";
    this.answer = "";
    this.sources = [];
    try {
      const response = await API.callJsonApi(ENDPOINT, {
        action: "execute",
        query: query,
        mode: this.mode,
      });
      if (response && response.error) {
        this.errorMessage = response.error;
      } else {
        this.answer = response.answer || "";
        this.sources = response.sources || [];
        // Add to history
        this.history.unshift({
          query: query,
          mode: this.mode,
          answer: this.answer.substring(0, 200),
          timestamp: new Date().toLocaleTimeString(),
        });
        // Cap history at 50 entries
        if (this.history.length > 50) {
          this.history = this.history.slice(0, 50);
        }
      }
    } catch (e) {
      this.errorMessage = "Query failed: " + e.message;
    } finally {
      this.querying = false;
    }
  },

  loadFromHistory(item) {
    this.queryText = item.query;
    this.mode = item.mode;
  },

  clearHistory() {
    this.history = [];
  },

  destroy() {
    this.queryText = "";
    this.answer = "";
    this.sources = [];
    this.errorMessage = "";
    // History persists within session (not cleared on close)
  },
};

export const store = createStore("edgequakeQuery", model);
