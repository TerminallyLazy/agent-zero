import { createStore } from "/js/AlpineStore.js";
import { callJsonApi } from "/js/api.js";
import { getContext } from "/index.js";

const PLUGIN_NAME = "dspy_rlm";
const API_BASE = "/plugins/dspy_rlm";
const MIN_REFRESH_SECONDS = 1;
const DEFAULT_REFRESH_SECONDS = 8;
const STATUS_REQUEST_TIMEOUT_MS = 10000;

const DEFAULT_SUMMARY = {
  event_count: 0,
  loop_count: 0,
  tool_count: 0,
  success_rate: 0,
  top_tools: [],
  latest_objective: "",
  latest_response: "",
  latest_ts: "",
};

const DEFAULT_STATE = {
  optimization_running: false,
  optimization_status: "idle",
  optimization_count: 0,
  attempts_total: 0,
  attempts_since_optimization: 0,
  last_optimization_at: "",
  last_optimization_error: "",
  last_guidance: "",
  last_guidance_at: "",
  optimization_result: {},
  optimization_requested_by: "",
  optimization_status_message: "",
  optimization_queue: "",
};

const DEFAULT_SCHEDULER = {
  // SQLite-backed workers coordinate on one host only.
  mode: "local_multiprocess",
  target_workers: 1,
  running_workers: 0,
  active_worker_ids: [],
  jobs: {},
  samples: {},
  guidance_rows: 0,
  sample_rows: 0,
  context_states: 0,
  queue_limit: 0,
  running_jobs: [],
  recent_jobs: [],
  stop_requested: false,
};

function toInt(value, fallback = 0) {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  if (Number.isFinite(parsed)) {
    return parsed;
  }
  return fallback;
}

function toFloat(value, fallback = 0) {
  const parsed = Number.parseFloat(String(value ?? ""));
  if (Number.isFinite(parsed)) {
    return parsed;
  }
  return fallback;
}

function toBool(value, fallback = false) {
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value !== 0;
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    return ["1", "true", "yes", "on", "enabled"].includes(normalized);
  }
  return fallback;
}

function coerceArray(value) {
  return Array.isArray(value) ? value : [];
}

function toStringSafe(value) {
  return String(value ?? "");
}

function normalizePercent(value) {
  return `${Math.max(0, Math.min(100, Math.round(toFloat(value, 0) * 100)))}%`;
}

function normalizeConfig(raw = {}) {
  const cfg = typeof raw === "object" && raw ? raw : {};
  const trace = cfg.trace_capture && typeof cfg.trace_capture === "object" ? cfg.trace_capture : {};
  const optimization = cfg.optimization && typeof cfg.optimization === "object" ? cfg.optimization : {};
  const scheduler = cfg.scheduler && typeof cfg.scheduler === "object" ? cfg.scheduler : {};
  const matrix = cfg.matrix && typeof cfg.matrix === "object" ? cfg.matrix : {};
  const evaluator = cfg.evaluator && typeof cfg.evaluator === "object" ? cfg.evaluator : {};
  const prompt = cfg.prompt && typeof cfg.prompt === "object" ? cfg.prompt : {};
  const rlm = cfg.rlm && typeof cfg.rlm === "object" ? cfg.rlm : {};
  const promptOptimization = cfg.prompt_optimization && typeof cfg.prompt_optimization === "object" ? cfg.prompt_optimization : {};

  return {
    ...cfg,
    enabled: toBool(cfg.enabled, false),
    instrumentation_enabled: toBool(cfg.instrumentation_enabled, false),
    status_refresh_seconds: toInt(cfg.status_refresh_seconds, DEFAULT_REFRESH_SECONDS),
    auto_optimize_enabled: toBool(cfg.auto_optimize_enabled, toBool(optimization.auto_optimize, false)),
    optimization_interval_messages: toInt(cfg.optimization_interval_messages, toInt(optimization.auto_optimize_interval_messages, 12)),
    optimization_min_samples: toInt(cfg.optimization_min_samples, toInt(optimization.min_samples_for_promotion, 10)),
    optimization_trace_window: toInt(cfg.optimization_trace_window, toInt(trace.max_events_per_context, 220)),
    optimization_cooldown_hours: toInt(cfg.optimization_cooldown_hours, toInt(optimization.cooldown_hours, 6)),
    trace_retention_limit: toInt(cfg.trace_retention_limit, toInt(trace.event_ttl_seconds, 604800)),
    trace_enabled: toBool(cfg.trace_enabled, toBool(cfg.instrumentation_enabled, false)),
    enable_dspy_optimizer: toBool(cfg.enable_dspy_optimizer, toBool(optimization.enable_dspy_optimizer, false)),
    gepa_steps: toInt(cfg.gepa_steps, toInt(optimization.ge_pa_steps, 3)),
    gepa_threads: toInt(cfg.gepa_threads, toInt(optimization.ge_pa_threads, 2)),
    ge_pa_steps: toInt(cfg.ge_pa_steps, toInt(cfg.gepa_steps, 3)),
    ge_pa_threads: toInt(cfg.ge_pa_threads, toInt(cfg.gepa_threads, 2)),
    optimization_preview_limit: toInt(cfg.optimization_preview_limit, toInt(optimization.optimization_preview_limit, 20)),
    dependencies: cfg.dependencies && typeof cfg.dependencies === "object" ? cfg.dependencies : {},
    rlm: {
      ...rlm,
      enabled: toBool(rlm.enabled, true),
      model_configured: toBool(rlm.model_configured, false),
    },
    prompt_optimization: {
      ...promptOptimization,
      enabled: toBool(promptOptimization.enabled, false),
      capture_approved: toBool(promptOptimization.capture_approved ?? promptOptimization.allow_prompt_capture, false),
      target_mode: toStringSafe(promptOptimization.target_mode || "guidance_overlay"),
      activation_mode: toStringSafe(promptOptimization.activation_mode || "manual"),
      canary_percentage: toInt(promptOptimization.canary_percentage, 10),
    },
    scheduler: {
      mode: toStringSafe(cfg.scheduler_mode || scheduler.mode || "local_multiprocess"),
      max_workers: toInt(cfg.scheduler_max_workers, toInt(scheduler.max_workers, 2)),
      poll_interval_seconds: toInt(cfg.scheduler_poll_interval_seconds, toInt(scheduler.poll_interval_seconds, 3)),
      job_lease_seconds: toInt(cfg.scheduler_job_lease_seconds, toInt(scheduler.job_lease_seconds, 45)),
      max_retries: toInt(cfg.scheduler_max_retries, toInt(scheduler.max_retries, 2)),
      heartbeat_seconds: toInt(cfg.scheduler_heartbeat_seconds, toInt(scheduler.heartbeat_seconds, 8)),
      stale_worker_seconds: toInt(cfg.scheduler_stale_worker_seconds, toInt(scheduler.stale_worker_seconds, 180)),
      scheduler_lock_ttl_seconds: toInt(cfg.scheduler_lock_ttl_seconds, toInt(scheduler.scheduler_lock_ttl_seconds, 30)),
      enforce_single_tenant_per_context: toBool(cfg.scheduler_enforce_single_tenant_per_context, toBool(scheduler.enforce_single_tenant_per_context, false)),
      backoff_base_seconds: toInt(cfg.scheduler_backoff_base_seconds, toInt(scheduler.backoff_base_seconds, 2)),
    },
    optimization: {
      ...optimization,
      enabled: toBool(optimization.enabled, false),
      auto_optimize: toBool(optimization.auto_optimize, false),
      auto_optimize_interval_messages: toInt(optimization.auto_optimize_interval_messages, 12),
      min_samples_for_promotion: toInt(optimization.min_samples_for_promotion, 10),
      cooldown_hours: toInt(optimization.cooldown_hours, 6),
      max_samples_per_objective: toInt(optimization.max_samples_per_objective, 40),
      confidence_floor: toFloat(optimization.confidence_floor, 0.7),
      global_score_threshold: toFloat(optimization.global_score_threshold, 0.8),
      ge_pa_steps: toInt(cfg.gepa_steps, toInt(cfg.ge_pa_steps, toInt(optimization.ge_pa_steps, 3))),
      ge_pa_threads: toInt(cfg.gepa_threads, toInt(cfg.ge_pa_threads, toInt(optimization.ge_pa_threads, 2))),
      enable_dspy_optimizer: toBool(cfg.enable_dspy_optimizer, toBool(optimization.enable_dspy_optimizer, false)),
      enable_replay_audit: toBool(optimization.enable_replay_audit, true),
      replay_set_size: toInt(optimization.replay_set_size, 6),
      replay_tolerable_regression: toFloat(optimization.replay_tolerable_regression, 0.1),
    },
    matrix: {
      ...matrix,
      version: matrix.version || "2.0",
      shell: { ...(matrix.shell || {}), enabled: toBool(matrix?.shell?.enabled, true) },
      tool_retrieval: { ...(matrix.tool_retrieval || {}), enabled: toBool(matrix?.tool_retrieval?.enabled, true) },
      reasoning: { ...(matrix.reasoning || {}), enabled: toBool(matrix?.reasoning?.enabled, true) },
      decision_making: { ...(matrix.decision_making || {}), enabled: toBool(matrix?.decision_making?.enabled, true) },
    },
    evaluator: {
      ...evaluator,
      enable_semantic_judge: toBool(evaluator.enable_semantic_judge, false),
      semantic_loop_batch_size: toInt(evaluator.semantic_loop_batch_size, 8),
      risk_threshold: toFloat(evaluator.risk_threshold, 0.25),
      enable_replay_audit: toBool(evaluator.enable_replay_audit, true),
      max_replay_depth: toInt(evaluator.max_replay_depth, 6),
      policy_breach_keywords: coerceArray(evaluator.policy_breach_keywords).length
        ? evaluator.policy_breach_keywords
        : toStringSafe(evaluator.policy_breach_keywords)
          .split(/[\n,]/)
          .map((item) => item.trim())
          .filter(Boolean),
      preferred_dspy_model: toStringSafe(evaluator.preferred_dspy_model),
    },
    prompt: {
      inject_guidance: toBool(prompt.inject_guidance, false),
      inject_even_without_guidance: toBool(prompt.inject_even_without_guidance, false),
      max_injected_chars: toInt(prompt.max_injected_chars, 1800),
      fallback_guidance: toStringSafe(prompt.fallback_guidance),
    },
  };
}

function normalizeTraceSummary(raw = {}) {
  // The status API emits only { tool, count }. Keep this strict so a malformed
  // or older response cannot turn arbitrary objects/text into UI telemetry.
  const rows = coerceArray(raw.top_tools)
    .filter((item) => item && typeof item === "object" && !Array.isArray(item))
    .map((item) => ({
      tool: toStringSafe(item.tool || "unknown"),
      count: Math.max(0, toInt(item.count, 0)),
    }));

  const summary = {
    ...DEFAULT_SUMMARY,
    ...raw,
    top_tools: rows,
    event_count: toInt(raw.event_count, 0),
    loop_count: toInt(raw.loop_count, 0),
    tool_count: toInt(raw.tool_count, 0),
    success_rate: Math.max(0, Math.min(1, toFloat(raw.success_rate, 0))),
  };
  return summary;
}

function normalizeScheduler(raw = {}) {
  const scheduler = raw?.scheduler && typeof raw.scheduler === "object" ? raw.scheduler : {};
  const base = {
    ...DEFAULT_SCHEDULER,
    ...raw,
    jobs: raw?.jobs && typeof raw.jobs === "object" ? raw.jobs : {},
    samples: raw?.samples && typeof raw.samples === "object" ? raw.samples : {},
    target_workers: toInt(raw.target_workers, 1),
    running_workers: toInt(raw.running_workers, 0),
    active_worker_ids: coerceArray(raw.active_worker_ids).map(toStringSafe),
    queue_limit: toInt(raw.queue_limit, 0),
    guidance_rows: toInt(raw.guidance_rows, 0),
    sample_rows: toInt(raw.sample_rows, 0),
    context_states: toInt(raw.context_states, 0),
    stop_requested: toBool(raw.stop_requested, false),
    running_jobs: coerceArray(raw.running_jobs),
    recent_jobs: coerceArray(raw.recent_jobs),
  };

  // There is no multi-host scheduler in this plugin. "single" is a valid
  // worker count configuration, not a different deployment topology.
  base.mode = "local_multiprocess";
  return base;
}

function normalizeContextSamples(raw = {}) {
  return {
    counts: raw?.counts && typeof raw.counts === "object" ? raw.counts : {},
    confidence: raw?.confidence && typeof raw.confidence === "object" ? raw.confidence : {},
  };
}

function normalizeMatrix(raw = {}) {
  const bucketMatrix = {};
  const bucketScores = raw?.bucket_scores && typeof raw.bucket_scores === "object" ? raw.bucket_scores : {};
  const bucketCounts = raw?.bucket_counts && typeof raw.bucket_counts === "object" ? raw.bucket_counts : {};

  const rows = raw?.bucket_matrix && typeof raw.bucket_matrix === "object" ? raw.bucket_matrix : {};
  for (const [bucket, values] of Object.entries(rows)) {
    const normalized = values && typeof values === "object" ? values : {};
    bucketMatrix[bucket] = {
      rows: toInt(normalized.rows, 0),
      semantic_match: toFloat(normalized.semantic_match, 0),
      command_safety: toFloat(normalized.command_safety, 0),
      execution_reliability: toFloat(normalized.execution_reliability, 0),
      evidence_recall: toFloat(normalized.evidence_recall, 0),
      evidence_precision: toFloat(normalized.evidence_precision, 0),
      answer_quality: toFloat(normalized.answer_quality, 0),
      policy_compliance: toFloat(normalized.policy_compliance, 0),
    };
  }

  return {
    ...{
      bucket_scores: {},
      bucket_counts: {},
      overall: {},
      bucket_matrix: {},
    },
    bucket_scores: bucketScores,
    bucket_counts: bucketCounts,
    overall: raw?.overall && typeof raw.overall === "object" ? raw.overall : {},
    bucket_matrix: bucketMatrix,
  };
}

function normalizeContextState(raw = {}) {
  return {
    ...DEFAULT_STATE,
    ...raw,
    optimization_running: toBool(raw.optimization_running, false),
    optimization_count: toInt(raw.optimization_count, 0),
    attempts_total: toInt(raw.attempts_total, 0),
    attempts_since_optimization: toInt(raw.attempts_since_optimization, 0),
  };
}

function normalizeJob(raw = {}) {
  return {
    job_key: toStringSafe(raw.job_key),
    context_id: toStringSafe(raw.context_id),
    objective_id: toStringSafe(raw.objective_id),
    objective_bucket: toStringSafe(raw.objective_bucket),
    objective_signature: toStringSafe(raw.objective_signature),
    status: toStringSafe(raw.status || "pending"),
    attempts: toInt(raw.attempts, 0),
    max_retries: toInt(raw.max_retries, 0),
    created_at: toFloat(raw.created_at, 0),
    updated_at: toFloat(raw.updated_at, 0),
    last_error: toStringSafe(raw.last_error),
    lease_owner: toStringSafe(raw.lease_owner),
    lease_expires_at: toFloat(raw.lease_expires_at, 0),
    payload: raw.payload && typeof raw.payload === "object" ? raw.payload : {},
    result: raw.result && typeof raw.result === "object" ? raw.result : null,
  };
}

function clamp01(value) {
  const n = toFloat(value, 0);
  return Math.max(0, Math.min(1, n));
}

function parseContextId() {
  const fromUrl = new URLSearchParams(window.location.search || "").get("ctxid");
  let current = "";
  try {
    current = typeof window.getContext === "function" ? window.getContext() : "";
  } catch (_) {
    current = "";
  }
  let available = "";
  try {
    const chats = window.Alpine?.store?.("chats");
    available = chats?.selected || chats?.contexts?.[0]?.id || "";
  } catch (_) {
    available = "";
  }
  return String(fromUrl || current || available || "");
}

function withTimeout(promise, timeoutMs, message) {
  let timeoutId;
  const timeout = new Promise((_, reject) => {
    timeoutId = setTimeout(() => reject(new Error(`${message} (${timeoutMs}ms)`)), timeoutMs);
  });
  return Promise.race([promise, timeout]).finally(() => {
    if (timeoutId) {
      clearTimeout(timeoutId);
    }
  });
}

function formatError(error) {
  if (typeof error === "string") return error;
  if (error instanceof Error) return error.message;
  return String(error || "");
}

function parseDate(value) {
  if (!value) return null;
  const parsed = Date.parse(String(value));
  return Number.isFinite(parsed) ? parsed : null;
}

function formatTimeAgo(value) {
  const parsed = parseDate(value);
  if (!parsed) return "";
  const now = Date.now();
  const deltaMs = Math.max(0, now - parsed);
  const seconds = Math.floor(deltaMs / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function contextStateFromResult(raw = {}) {
  if (!raw || typeof raw !== "object") return {};
  return {
    objective_signature: toStringSafe(raw.objective_signature),
    promotion_decision: toStringSafe(raw.promotion_decision),
    status: toStringSafe(raw.status),
    reason: toStringSafe(raw.reason),
  };
}

function pickLatestResult(contextState = {}, latestJobs = []) {
  if (contextState.optimization_result && typeof contextState.optimization_result === "object") {
    return contextState.optimization_result;
  }

  if (latestJobs.length > 0 && latestJobs[0]?.result && typeof latestJobs[0].result === "object") {
    return latestJobs[0].result;
  }

  return {};
}

function resolveJobStatusLabel(job = {}) {
  const status = toStringSafe(job.status || "").toLowerCase();
  if (!status) return "unknown";
  if (status === "succeeded") return "succeeded";
  if (status === "running") return "running";
  if (status === "pending") return "queued";
  if (status === "failed") return "failed";
  return status;
}

export const store = createStore("dspyRlm", {
  statusLoaded: false,
  loading: false,
  actionInFlight: false,
  runtimeInitialized: false,
  refreshMs: DEFAULT_REFRESH_SECONDS * 1000,
  contextId: "",
  pluginName: PLUGIN_NAME,
  pluginPath: API_BASE,
  lastError: "",
  statusMessage: "",

  dependencies: {
    gepa_worker_ready: false,
    lock_manifest: "requirements-gepa.lock",
    missing_count: 0,
    hash_complete: false,
    setup_mode: "manual_explicit_setup_only",
  },
  config: {},
  contextState: {},
  traceSummary: { ...DEFAULT_SUMMARY },
  scheduler: { ...DEFAULT_SCHEDULER },
  contextSamples: { counts: {}, confidence: {} },
  objectiveMatrix: {
    bucket_scores: {},
    bucket_counts: {},
    overall: {},
    bucket_matrix: {},
  },
  recentJobs: [],
  activeJobs: [],
  optimizationResult: null,

  _refreshTimer: null,
  _refreshSeq: 0,
  _statusTimer: null,

  get autoOptimizeEnabled() {
    return toBool(this.config?.auto_optimize_enabled, false);
  },

  get dependencyClass() {
    return this.dependencies?.gepa_worker_ready ? "status-badge--ok" : "status-badge--warn";
  },

  get dependencyStateClass() {
    return this.dependencyClass;
  },

  get dependenciesLabel() {
    if (this.dependencies?.gepa_worker_ready) return "GEPA worker ready";
    if (!this.dependencies?.hash_complete) return "GEPA worker setup requires refreshed dependency pins";
    const missing = Math.max(0, toInt(this.dependencies?.missing_count, 0));
    return missing ? `GEPA worker dependencies missing (${missing})` : "GEPA worker not ready";
  },

  // Retain this alias for extensions that used the older singular label.
  get dependencyLabel() {
    return this.dependenciesLabel;
  },

  get autoOptimizeLabel() {
    return toBool(this.autoOptimizeEnabled, false)
      ? "On"
      : "Off";
  },

  get objectiveModeLabel() {
    return this.optimizationMode;
  },

  get totalAttempts() {
    return toStringSafe(toInt(this.contextState?.attempts_total, 0));
  },

  get attemptsSinceOptimization() {
    return toStringSafe(toInt(this.contextState?.attempts_since_optimization, 0));
  },

  get cooldownLabel() {
    const cooldownHours = toInt(this.config?.optimization_cooldown_hours, 0);
    const status = this.contextState?.optimization_status || "idle";
    if (status === "running") {
      return "running";
    }
    if (cooldownHours <= 0) {
      return "disabled";
    }
    const lastOptimizationAt = parseDate(this.contextState?.last_optimization_at);
    if (!lastOptimizationAt) {
      return "warm-up";
    }
    const elapsedMs = Math.max(0, Date.now() - lastOptimizationAt);
    const elapsedHours = elapsedMs / 3_600_000;
    const remaining = Math.max(0, cooldownHours - elapsedHours);
    if (remaining <= 0.01) {
      return "ready";
    }
    return `${remaining.toFixed(1)} h`;
  },

  get configuredRefreshLabel() {
    const refreshSeconds = Math.max(1, toInt(this.config?.status_refresh_seconds, DEFAULT_REFRESH_SECONDS));
    return `${refreshSeconds}s refresh`;
  },

  get objectiveReadiness() {
    return this.readiness;
  },

  get optimizationStatus() {
    return toStringSafe(this.contextState?.optimization_status || "idle");
  },

  get lastGuidance() {
    return toStringSafe(this.contextState?.last_guidance);
  },

  get lastGuidanceDate() {
    const updated = this.contextState?.last_guidance_at;
    if (!updated) return "never";
    const formatted = formatTimeAgo(updated);
    return formatted ? `${formatted} ago` : "never";
  },

  get optimizationClass() {
    const status = toStringSafe(this.contextState?.optimization_status).toLowerCase();
    if (!this.contextState?.optimization_running) {
      if (status === "success") return "status-badge--ok";
      if (status === "rejected" || status === "error" || status === "candidate_rejected") return "status-badge--danger";
      return "status-badge--warn";
    }

    return "status-badge--running";
  },

  get optimizationMode() {
    const prompt = this.config?.prompt_optimization || {};
    if (toBool(prompt.enabled, false) && prompt.target_mode !== "guidance_overlay") {
      const target = prompt.target_mode === "assembled_prompt" ? "assembled prompt" : "prompt components";
      return `GEPA ${target} · ${prompt.activation_mode || "manual"}`;
    }
    if (!toBool(this.config?.enable_dspy_optimizer, false)) return "Heuristic mode";
    return toBool(this.config?.rlm?.enabled, false) ? "GEPA + RLM mode" : "GEPA mode";
  },

  get statusBanner() {
    if (!this.contextId) return "Pick a context id to inspect optimization state";
    if (!this.autoOptimizeEnabled) return "Auto-optimization is currently disabled";
    return this.readiness.label;
  },

  get readiness() {
    if (!this.autoOptimizeEnabled) {
      return {
        state: "off",
        label: "Auto-optimization disabled",
      };
    }

    if (this.contextState?.optimization_running) {
      return {
        state: "running",
        label: "Optimization running",
      };
    }

    const needed = Math.max(0, toInt(this.config?.optimization_min_samples, 10) - toInt(this.contextState?.attempts_total, 0));
    if (needed > 0) {
      return {
        state: "warming",
        label: `${needed} more loop samples required before next cycle`,
      };
    }

    return {
      state: "ready",
      label: "Ready to queue next optimization",
    };
  },

  get schedulerMode() {
    const mode = toStringSafe(this.scheduler?.mode || "local_multiprocess");
    return mode === "local_multiprocess" ? "Local" : mode.replaceAll("_", " ");
  },

  get schedulerWorkersLabel() {
    return `${toInt(this.scheduler?.running_workers, 0)}/${toInt(this.scheduler?.target_workers, 0)}`;
  },

  get jobCounts() {
    const jobs = this.scheduler?.jobs || {};
    return {
      pending: toInt(jobs.pending, 0),
      running: toInt(jobs.running, 0),
      failed: toInt(jobs.failed, 0),
      succeeded: toInt(jobs.succeeded, 0),
      queued: toInt(jobs.queued, 0),
      total: toInt(jobs.pending, 0) + toInt(jobs.running, 0) + toInt(jobs.failed, 0) + toInt(jobs.succeeded, 0) + toInt(jobs.queued, 0),
    };
  },

  get schedulerHealth() {
    return `running ${this.jobCounts.running} · queued ${this.jobCounts.pending} · failed ${this.jobCounts.failed}`;
  },

  get matrixBuckets() {
    const bucketMatrix = this.objectiveMatrix?.bucket_matrix || {};
    return Object.entries(bucketMatrix)
      .map(([bucket, row]) => ({
        bucket,
        rows: toInt(row.rows, 0),
        overall: clamp01(row.semantic_match),
        semanticMatch: clamp01(row.semantic_match),
        commandSafety: clamp01(row.command_safety),
        executionReliability: clamp01(row.execution_reliability),
        evidenceRecall: clamp01(row.evidence_recall),
        evidencePrecision: clamp01(row.evidence_precision),
        answerQuality: clamp01(row.answer_quality),
        policyCompliance: clamp01(row.policy_compliance),
        bucketScore: clamp01((this.objectiveMatrix?.bucket_scores || {})[bucket] || 0),
      }))
      .filter((entry) => entry.bucketScore > 0 || entry.rows > 0)
      .sort((a, b) => b.bucketScore - a.bucketScore);
  },

  get matrixSummary() {
    return this.matrixBuckets.map((entry) => ({
      label: entry.bucket,
      score: entry.bucketScore,
      count: entry.rows,
      scoreLabel: normalizePercent(entry.bucketScore),
    }));
  },

  get objectiveSamplesDistribution() {
    return this.contextSamples?.counts && typeof this.contextSamples.counts === "object"
      ? this.contextSamples.counts
      : {};
  },

  get formattedSamplesByBucket() {
    return Object.entries(this.objectiveSamplesDistribution)
      .map(([bucket, count]) => ({ bucket, count: toInt(count, 0) }))
      .sort((a, b) => b.count - a.count);
  },

  get lastOptimizationResult() {
    return this.optimizationResult || this.contextState?.optimization_result || null;
  },

  get latestRunStatus() {
    const decision = this.lastOptimizationResult?.promotion_decision || "pending";
    return {
      mode: this.lastOptimizationResult?.mode || "idle",
      status: this.lastOptimizationResult?.status || "not_run",
      decision,
      reason: this.lastOptimizationResult?.reason || this.lastOptimizationResult?.optimization_status || "",
      version: this.lastOptimizationResult?.guidance_version || "",
      startedAt: this.lastOptimizationResult?.started_at || this.contextState?.last_optimization_at || "",
    };
  },

  get topTools() {
    const tools = coerceArray(this.traceSummary?.top_tools);
    const maxCount = tools.reduce((max, item) => Math.max(max, toInt(item?.count, 0)), 0) || 1;
    return tools.map((item) => ({
      tool: toStringSafe(item.tool || item.name || "unknown"),
      count: toInt(item.count, 0),
      barWidth: normalizePercent(toInt(item.count, 0) / maxCount),
    }));
  },

  get statusRows() {
    return coerceArray(this.recentJobs).map(normalizeJob);
  },

  hasRecentEvents() {
    return coerceArray(this.topTools).length > 0;
  },

  latestToolRows() {
    return this.topTools.map((item) => ({
      toolName: toStringSafe(item.tool),
      count: toInt(item.count, 0),
      width: item.barWidth,
    }));
  },

  async initRuntime() {
    if (this.runtimeInitialized) return;
    this.runtimeInitialized = true;
    this.contextId = parseContextId();
    await this.refreshStatus({ force: true, suppressError: true });
    this._scheduleRefresh();
  },

  _clearStatusMessage() {
    clearTimeout(this._statusTimer);
    this._statusTimer = setTimeout(() => {
      this.statusMessage = "";
    }, 3500);
  },

  setStatusMessage(message) {
    this.statusMessage = String(message || "");
    clearTimeout(this._statusTimer);
    if (!this.statusMessage) return;
    this._clearStatusMessage();
  },

  async refreshStatus({ force = false, suppressError = false } = {}) {
    if (!force && this.loading) return;
    this.lastError = "";
    if (!this.contextId) this.contextId = parseContextId();
    if (!this.contextId) {
      this.loading = false;
      if (!suppressError) this.lastError = "Create or select a chat context to inspect optimization state";
      return;
    }
    if (!force) this.loading = true;

    try {
      const payload = await withTimeout(
        callJsonApi(`${API_BASE}/status`, {
          context_id: String(this.contextId || "").trim(),
        }),
        STATUS_REQUEST_TIMEOUT_MS,
        "Status request timed out",
      );

      if (payload?.context_id) {
        this.contextId = String(payload.context_id || this.contextId || "");
      }

      this.config = normalizeConfig(payload?.config || {});
      this.dependencies = {
        gepa_worker_ready: toBool(payload?.dependencies?.gepa_worker_ready, false),
        lock_manifest: toStringSafe(payload?.dependencies?.lock_manifest || "requirements-gepa.lock"),
        missing_count: Math.max(0, toInt(payload?.dependencies?.missing_count, 0)),
        hash_complete: toBool(payload?.dependencies?.hash_complete, false),
        setup_mode: toStringSafe(payload?.dependencies?.setup_mode || "isolated_worker_venv"),
      };
      this.contextState = normalizeContextState(payload?.context_state || {});
      this.traceSummary = normalizeTraceSummary(payload?.trace_summary || {});
      this.scheduler = normalizeScheduler(payload?.scheduler || {});
      this.contextSamples = normalizeContextSamples(payload?.context_samples || {});

      this.objectiveMatrix = normalizeMatrix(this.contextState?.optimization_result?.matrix_scores || {});

      this.recentJobs = coerceArray(payload?.recent_jobs || this.scheduler?.recent_jobs || []);
      this.activeJobs = coerceArray(this.scheduler?.running_jobs || []).map(normalizeJob);
      this.recentJobs = this.recentJobs.map((row) => ({
        ...normalizeJob(row),
        status: resolveJobStatusLabel(row),
      }));

      this.optimizationResult = pickLatestResult(this.contextState, this.recentJobs);
      this.statusLoaded = true;

      const refreshSeconds = Math.max(MIN_REFRESH_SECONDS, toInt(this.config?.status_refresh_seconds, DEFAULT_REFRESH_SECONDS));
      this.refreshMs = refreshSeconds * 1000;
      this._scheduleRefresh();
    } catch (error) {
      if (!suppressError) {
        this.lastError = formatError(error);
      } else {
        this.lastError = this.lastError || formatError(error);
      }
      this.statusLoaded = this.statusLoaded || force;
    } finally {
      this.loading = false;
    }
  },

  _scheduleRefresh() {
    if (this._refreshTimer) {
      clearInterval(this._refreshTimer);
      this._refreshTimer = null;
    }

    const seq = ++this._refreshSeq;
    const intervalMs = Math.max(MIN_REFRESH_SECONDS * 1000, this.refreshMs || DEFAULT_REFRESH_SECONDS * 1000);
    this._refreshTimer = setInterval(() => {
      if (seq !== this._refreshSeq) return;
      void this.refreshStatus();
    }, intervalMs);
  },

  stopAutoRefresh() {
    if (this._refreshTimer) {
      clearInterval(this._refreshTimer);
      this._refreshTimer = null;
    }
    this._refreshSeq += 1;
  },

  async openConfig() {
    const { store } = await import("/components/plugins/plugin-settings-store.js");
    await store.openConfig(PLUGIN_NAME);
  },

  setContextId(eventOrValue) {
    const nextId = toStringSafe(eventOrValue?.target ? eventOrValue.target.value : eventOrValue || "").trim();
    if (!nextId) {
      this.lastError = "Enter a context id to load status";
      return;
    }
    this.contextId = nextId;
    this.lastError = "";
    void this.refreshStatus({ force: true });
  },

  async runOptimize() {
    return this._runOptimize(false);
  },

  async runOptimizeSync() {
    return this._runOptimize(true);
  },

  async _runOptimize(runSync = false) {
    if (!this.contextId) {
      this.lastError = "Context id is required";
      return;
    }

    this.lastError = "";
    this.actionInFlight = true;

    try {
      const response = await callJsonApi(`${API_BASE}/optimize`, {
        context_id: String(this.contextId),
        force: true,
        run_sync: runSync,
      });

      const scheduler = response?.scheduler || {};
      const result = response?.result || response?.optimization_result || this.contextState?.optimization_result || {};
      this.optimizationResult = result;
      this.setStatusMessage(`Optimization ${runSync ? "sync " : ""}${scheduler?.dispatched ? "dispatched" : "queued"}`);
      await this.refreshStatus({ force: true });
      return result;
    } catch (error) {
      this.lastError = formatError(error);
    } finally {
      this.actionInFlight = false;
    }

    return null;
  },

  statusClassFromValue(value) {
    const normalized = toStringSafe(value || "").toLowerCase();
    if (["success", "ok", "promoted", "running", "active", "pass"].includes(normalized)) {
      return "status-badge--ok";
    }
    if (["failed", "error", "rejected", "reject", "danger"].includes(normalized)) {
      return "status-badge--danger";
    }
    return "status-badge--warn";
  },

  formatPercent(value) {
    return normalizePercent(value);
  },

  formatTimeAgo(value) {
    return formatTimeAgo(value);
  },

  formatToolWidth(count, total) {
    const denominator = Math.max(1, toInt(total, 1));
    return `${Math.round((toInt(count, 0) / denominator) * 100)}%`;
  },

  jobStatusClass(status = "") {
    const normalized = String(status || "").toLowerCase();
    if (normalized === "running") return "status-badge--running";
    if (normalized === "failed") return "status-badge--danger";
    if (normalized === "succeeded" || normalized === "success") return "status-badge--ok";
    return "status-badge--warn";
  },

  matrixScoreClass(score) {
    const normalized = toFloat(score, 0);
    if (normalized >= 0.8) return "status-badge--ok";
    if (normalized >= 0.6) return "status-badge--warn";
    return "status-badge--danger";
  },
});
