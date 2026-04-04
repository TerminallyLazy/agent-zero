import type {
  AttachmentPayload,
  BridgeCommand,
  BrowserTabSummary,
  ExtensionConfig,
  LogItem,
  ProjectSummary,
  SessionSnapshot,
} from "./types";

const jsonHeaders = (apiKey: string): HeadersInit => ({
  "Content-Type": "application/json",
  "X-API-KEY": apiKey,
});

export const normalizeBaseUrl = (value: string): string => {
  const trimmed = value.trim().replace(/\/+$/, "");
  if (!trimmed) {
    return "";
  }
  return trimmed.endsWith("/api") ? trimmed.slice(0, -4) : trimmed;
};

const joinUrl = (baseUrl: string, path: string): string => {
  return `${normalizeBaseUrl(baseUrl)}${path.startsWith("/") ? path : `/${path}`}`;
};

async function requestJson<T>(baseUrl: string, apiKey: string, path: string, init: RequestInit): Promise<T> {
  const response = await fetch(joinUrl(baseUrl, path), init);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

export class AgentZeroClient {
  constructor(private readonly config: ExtensionConfig) {}

  sendMessage(
    message: string,
    options: {
      contextId?: string;
      attachments?: AttachmentPayload[];
      projectName?: string;
      waitForResponse?: boolean;
    } = {},
  ): Promise<{ context_id: string; response?: string; accepted?: boolean; status?: string }> {
    return requestJson(this.config.baseUrl, this.config.apiKey, "/api/api_message", {
      method: "POST",
      headers: jsonHeaders(this.config.apiKey),
      body: JSON.stringify({
        message,
        context_id: options.contextId || undefined,
        attachments: options.attachments || [],
        project_name: options.projectName || undefined,
        lifetime_hours: 24,
        wait_for_response: options.waitForResponse !== false,
      }),
    });
  }

  getLogs(contextId: string): Promise<{ context_id: string; log: { items: LogItem[] } }> {
    return requestJson(this.config.baseUrl, this.config.apiKey, "/api/api_log_get", {
      method: "POST",
      headers: jsonHeaders(this.config.apiKey),
      body: JSON.stringify({ context_id: contextId, length: 200 }),
    });
  }

  resetChat(contextId: string): Promise<{ ok?: boolean; success?: boolean }> {
    return requestJson(this.config.baseUrl, this.config.apiKey, "/api/api_reset_chat", {
      method: "POST",
      headers: jsonHeaders(this.config.apiKey),
      body: JSON.stringify({ context_id: contextId }),
    });
  }

  terminateChat(contextId: string): Promise<{ ok?: boolean; success?: boolean }> {
    return requestJson(this.config.baseUrl, this.config.apiKey, "/api/api_terminate_chat", {
      method: "POST",
      headers: jsonHeaders(this.config.apiKey),
      body: JSON.stringify({ context_id: contextId }),
    });
  }

  upsertSession(payload: {
    browserSessionId: string;
    contextId?: string;
    activeTabId?: number | null;
    tabs: BrowserTabSummary[];
    capabilities?: Record<string, unknown>;
  }): Promise<{ ok: boolean; session: SessionSnapshot }> {
    return requestJson(this.config.baseUrl, this.config.apiKey, "/api/plugins/chrome_extension/session_upsert", {
      method: "POST",
      headers: jsonHeaders(this.config.apiKey),
      body: JSON.stringify({
        browser_session_id: payload.browserSessionId,
        context_id: payload.contextId || "",
        active_tab_id: payload.activeTabId ?? null,
        tabs: payload.tabs,
        capabilities: payload.capabilities || {},
      }),
    });
  }

  pullCommand(browserSessionId: string): Promise<{ ok: boolean; command: BridgeCommand | null; session: SessionSnapshot | null }> {
    return requestJson(this.config.baseUrl, this.config.apiKey, "/api/plugins/chrome_extension/command_pull", {
      method: "POST",
      headers: jsonHeaders(this.config.apiKey),
      body: JSON.stringify({ browser_session_id: browserSessionId }),
    });
  }

  pushCommandResult(payload: {
    browserSessionId: string;
    commandId: string;
    status: "completed" | "failed";
    result?: Record<string, unknown>;
    error?: string;
    activeTabId?: number | null;
    tabs?: unknown[];
  }): Promise<{ ok: boolean }> {
    return requestJson(this.config.baseUrl, this.config.apiKey, "/api/plugins/chrome_extension/command_result", {
      method: "POST",
      headers: jsonHeaders(this.config.apiKey),
      body: JSON.stringify({
        browser_session_id: payload.browserSessionId,
        command_id: payload.commandId,
        status: payload.status,
        result: payload.result || {},
        error: payload.error || "",
        active_tab_id: payload.activeTabId ?? null,
        tabs: payload.tabs || [],
      }),
    });
  }

  listProjects(): Promise<{ ok: boolean; projects: ProjectSummary[] }> {
    return requestJson(this.config.baseUrl, this.config.apiKey, "/api/plugins/chrome_extension/projects", {
      method: "POST",
      headers: jsonHeaders(this.config.apiKey),
      body: JSON.stringify({}),
    });
  }
}
