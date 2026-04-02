import { createStore } from "/js/AlpineStore.js";
import { callJsonApi } from "/js/api.js";
import {
  toastFrontendError,
  toastFrontendInfo,
  toastFrontendSuccess,
} from "/components/notifications/notification-store.js";

const STATE_ENDPOINT = "/plugins/agent_harness/state";
const RUN_ENDPOINT = "/plugins/agent_harness/run";
const MEMORY_QUEUE_ENDPOINT = "/plugins/agent_harness/memory_queue";
const TITLE = "Agent Harness";
const POLL_MS = 5000;

function currentContextId() {
  return globalThis.getContext?.() || "";
}

function dashboardDefaults() {
  return {
    show_status_ui: true,
    default_deep_mode: "pro",
    memory_curation_enabled: true,
  };
}

function errorMessage(error) {
  return error instanceof Error ? error.message : String(error);
}

export const store = createStore("agentHarness", {
  _mounted: 0,
  _loaded: false,
  _timer: null,
  _inflight: null,

  isLoading: false,
  isActing: false,
  error: "",

  dashboard: dashboardDefaults(),
  currentRun: null,
  pendingCheckpoints: [],
  memoryQueue: [],
  recentRules: [],
  latestVerification: null,

  phaseLabel(phase) {
    return (
      {
        idle: "Idle",
        inspect: "Inspect",
        plan: "Plan",
        implement: "Implement",
        verify: "Verify",
        repair: "Repair",
        blocked: "Blocked",
        summarize: "Summarize",
        complete: "Complete",
      }[phase] || phase || "Idle"
    );
  },

  statusButtonLabel() {
    if (!this.currentRun) return "Harness";
    return `${String(this.currentRun.mode || "").toUpperCase()} · ${this.phaseLabel(this.currentRun.phase)}`;
  },

  async onMount() {
    this._mounted += 1;
    await this.loadState();
    this._ensurePolling();
  },

  cleanup() {
    this._mounted = Math.max(0, this._mounted - 1);
    if (this._mounted === 0 && this._timer) {
      clearInterval(this._timer);
      this._timer = null;
    }
  },

  _ensurePolling() {
    if (this._timer) return;
    this._timer = setInterval(() => {
      void this.loadState({ silent: true });
    }, POLL_MS);
  },

  async loadState({ silent = false } = {}) {
    const contextId = currentContextId();
    if (!contextId) {
      this.currentRun = null;
      this.pendingCheckpoints = [];
      this.memoryQueue = [];
      this.latestVerification = null;
      return null;
    }

    if (this._inflight) {
      return await this._inflight;
    }

    const request = (async () => {
      if (!silent) this.isLoading = true;
      this.error = "";
      try {
        const response = await callJsonApi(STATE_ENDPOINT, { context_id: contextId });
        this.dashboard = { ...dashboardDefaults(), ...(response?.dashboard || {}) };
        this.currentRun = response?.run || null;
        this.pendingCheckpoints = Array.isArray(response?.pending_checkpoints)
          ? response.pending_checkpoints
          : [];
        this.memoryQueue = Array.isArray(response?.pending_memory_candidates)
          ? response.pending_memory_candidates
          : [];
        this.recentRules = Array.isArray(response?.recent_rules) ? response.recent_rules : [];
        this.latestVerification = response?.latest_verification || null;
        this._loaded = true;
        return response;
      } catch (error) {
        this.error = errorMessage(error);
        if (!silent) {
          void toastFrontendError(`Failed to load harness state: ${this.error}`, TITLE);
        }
        return null;
      } finally {
        if (!silent) this.isLoading = false;
        this._inflight = null;
      }
    })();

    this._inflight = request;
    return await request;
  },

  async refresh() {
    await this.loadState();
    toastFrontendInfo("Harness state refreshed.", TITLE);
  },

  async _runAction(endpoint, payload, successMessage = "") {
    const contextId = currentContextId();
    if (!contextId) {
      void toastFrontendError("No active chat context is selected.", TITLE);
      return null;
    }

    this.isActing = true;
    try {
      const result = await callJsonApi(endpoint, { context_id: contextId, ...payload });
      if (successMessage) {
        toastFrontendSuccess(successMessage, TITLE);
      }
      await this.loadState({ silent: true });
      return result;
    } catch (error) {
      void toastFrontendError(errorMessage(error), TITLE);
      return null;
    } finally {
      this.isActing = false;
    }
  },

  async startRun(mode) {
    const defaultObjective = this.currentRun?.objective || "Active coding task";
    const objective = window.prompt("Harness objective", defaultObjective);
    if (objective === null) return;

    const trimmedObjective = objective.trim() || defaultObjective;
    await this._runAction(
      RUN_ENDPOINT,
      {
        action: "start",
        mode: mode || this.dashboard.default_deep_mode || "pro",
        objective: trimmedObjective,
      },
      `Started ${String(mode || this.dashboard.default_deep_mode || "pro").toUpperCase()} mode.`,
    );
  },

  async stopRun() {
    if (!window.confirm("Stop the current harness run?")) return;
    await this._runAction(RUN_ENDPOINT, { action: "stop" }, "Harness run stopped.");
  },

  async decideCheckpoint(checkpointId, decision) {
    const actionLabel = decision === "approved" ? "approved" : "rejected";
    await this._runAction(
      RUN_ENDPOINT,
      {
        action: "checkpoint_decide",
        checkpoint_id: checkpointId,
        decision,
      },
      `Checkpoint ${actionLabel}.`,
    );
  },

  async acceptCandidate(candidateId, scope) {
    await this._runAction(
      MEMORY_QUEUE_ENDPOINT,
      {
        action: "accept",
        candidate_id: candidateId,
        scope: scope || "project",
      },
      "Harness memory accepted.",
    );
  },

  async rejectCandidate(candidateId) {
    await this._runAction(
      MEMORY_QUEUE_ENDPOINT,
      {
        action: "reject",
        candidate_id: candidateId,
      },
      "Harness memory rejected.",
    );
  },
});
