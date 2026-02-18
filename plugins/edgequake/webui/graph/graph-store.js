import { createStore } from "/js/AlpineStore.js";
import * as API from "/js/api.js";

const ENDPOINT = "/api/plugins/edgequake/edgequake_graph";

const model = {
  // Search state
  searchKeyword: "",
  entities: [],
  searching: false,
  hasSearched: false,

  // Detail state (index-based to avoid Alpine proxy equality issues)
  selectedIndex: -1,

  // Stats
  stats: null,
  loadingStats: false,

  // Error
  errorMessage: "",

  async loadStats() {
    this.loadingStats = true;
    try {
      const response = await API.callJsonApi(ENDPOINT, { action: "stats" });
      if (response && response.error) {
        this.errorMessage = response.error;
      } else {
        this.stats = response;
      }
    } catch (e) {
      this.errorMessage = "Failed to load stats: " + e.message;
    } finally {
      this.loadingStats = false;
    }
  },

  async search() {
    const keyword = this.searchKeyword.trim();
    if (!keyword) return;

    this.searching = true;
    this.errorMessage = "";
    this.selectedIndex = -1;
    try {
      const response = await API.callJsonApi(ENDPOINT, {
        action: "search",
        keyword: keyword,
      });
      if (response && response.error) {
        this.errorMessage = response.error;
        this.entities = [];
      } else {
        this.entities = response.entities || [];
      }
    } catch (e) {
      this.errorMessage = "Search failed: " + e.message;
      this.entities = [];
    } finally {
      this.searching = false;
      this.hasSearched = true;
    }
  },

  selectEntity(idx) {
    this.selectedIndex = this.selectedIndex === idx ? -1 : idx;
  },

  destroy() {
    this.searchKeyword = "";
    this.entities = [];
    this.selectedIndex = -1;
    this.hasSearched = false;
    this.errorMessage = "";
    this.stats = null;
  },
};

export const store = createStore("edgequakeGraph", model);
