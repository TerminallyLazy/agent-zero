import type { BackgroundState, BrowserTabSummary, ExtensionConfig, LogItem, ProjectSummary } from "../lib/types";
import { DEFAULT_CONFIG } from "../lib/types";

const STORAGE_KEY = "agent-zero-chrome-background";

type PersistedState = Pick<BackgroundState, "browserSessionId" | "composeDraft" | "contextId" | "activeTabId" | "config">;

const ports = new Set<chrome.runtime.Port>();

let state: BackgroundState = {
  ready: false,
  connectionError: "",
  lastStatus: "Idle",
  panelConnected: false,
  browserSessionId: "",
  contextId: "",
  activeTabId: null,
  tabs: [],
  messages: [],
  projects: [],
  composeDraft: "",
  config: DEFAULT_CONFIG,
};

const createId = (): string => {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `session-${Date.now()}`;
};

const persistedShape = (): PersistedState => ({
  browserSessionId: state.browserSessionId,
  composeDraft: state.composeDraft,
  contextId: state.contextId,
  activeTabId: state.activeTabId,
  config: state.config,
});

async function persistState(): Promise<void> {
  await chrome.storage.local.set({ [STORAGE_KEY]: persistedShape() });
}

function broadcast(): void {
  for (const port of ports) {
    port.postMessage({ type: "state", state });
  }
}

export async function initializeState(): Promise<BackgroundState> {
  const loaded = (await chrome.storage.local.get(STORAGE_KEY))[STORAGE_KEY] as Partial<PersistedState> | undefined;
  state = {
    ...state,
    ...loaded,
    config: { ...DEFAULT_CONFIG, ...(loaded?.config || {}) },
    browserSessionId: loaded?.browserSessionId || createId(),
    ready: true,
  };
  await persistState();
  broadcast();
  return state;
}

export function getState(): BackgroundState {
  return state;
}

export async function patchState(patch: Partial<BackgroundState>): Promise<BackgroundState> {
  state = {
    ...state,
    ...patch,
    config: patch.config ? { ...state.config, ...patch.config } : state.config,
  };
  await persistState();
  broadcast();
  return state;
}

export async function setConfig(config: Partial<ExtensionConfig>): Promise<BackgroundState> {
  return patchState({ config: { ...state.config, ...config } });
}

export async function setMessages(messages: LogItem[]): Promise<void> {
  state = { ...state, messages };
  broadcast();
}

export async function setTabs(tabs: BrowserTabSummary[], activeTabId: number | null): Promise<void> {
  state = { ...state, tabs, activeTabId };
  await persistState();
  broadcast();
}

export async function setProjects(projects: ProjectSummary[]): Promise<void> {
  state = { ...state, projects };
  broadcast();
}

export function attachPort(port: chrome.runtime.Port): void {
  ports.add(port);
  state = { ...state, panelConnected: true };
  port.postMessage({ type: "state", state });
  broadcast();
  port.onDisconnect.addListener(() => {
    ports.delete(port);
    state = { ...state, panelConnected: ports.size > 0 };
    broadcast();
  });
}
