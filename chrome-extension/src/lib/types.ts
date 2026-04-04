export interface ExtensionConfig {
  baseUrl: string;
  apiKey: string;
  defaultProject: string;
  chatPollMs: number;
  commandPollMs: number;
  sessionPollMs: number;
}

export interface ProjectSummary {
  name: string;
  title: string;
  description?: string;
  color?: string;
}

export interface BrowserTabSummary {
  tab_id: number;
  window_id?: number | null;
  url: string;
  title: string;
  active: boolean;
  focused: boolean;
}

export interface BridgeCommand {
  command_id: string;
  browser_session_id: string;
  verb: string;
  payload: Record<string, unknown>;
  target_tab_id?: number | null;
  timeout_seconds: number;
  status: string;
  attempts: number;
}

export interface SessionSnapshot {
  browser_session_id: string;
  context_id: string;
  active_tab_id?: number | null;
  pending_commands: number;
  capabilities?: Record<string, unknown>;
  tabs: BrowserTabSummary[];
}

export interface PageContext {
  url: string;
  title: string;
  selectedText: string;
  metaDescription: string;
}

export interface DomNodeSummary {
  node_id: string;
  tag: string;
  text: string;
  placeholder: string;
  type: string;
  aria_label: string;
  label: string;
}

export interface DomSnapshot {
  url: string;
  title: string;
  nodes: DomNodeSummary[];
}

export interface AttachmentPayload {
  filename: string;
  base64: string;
}

export interface ScreenshotPreview extends AttachmentPayload {
  dataUrl: string;
}

export interface LogItem {
  no: number;
  id?: string | null;
  type: string;
  heading?: string;
  content?: unknown;
  kvps?: Record<string, unknown> | null;
  timestamp?: number;
  agentno?: number;
}

export interface ModelSummary {
  provider: string;
  provider_label: string;
  name: string;
  display_name: string;
}

export interface ModelPresetSummary {
  name: string;
  summary: string;
  chat: ModelSummary;
  utility: ModelSummary;
}

export interface ModelStateSummary {
  allow_override: boolean;
  override: Record<string, unknown> | null;
  active_preset: string | null;
  models: {
    chat: ModelSummary;
    utility: ModelSummary;
    embedding: ModelSummary;
  };
  presets: ModelPresetSummary[];
}

export interface ConversationItem {
  id: string;
  logNo: number;
  role: "user" | "assistant";
  text: string;
  attachments: string[];
  pending?: boolean;
  timestamp?: number;
}

export interface ActivityItem {
  id: string;
  logNo: number;
  type: string;
  title: string;
  detail: string;
  timestamp?: number;
}

export interface BackgroundState {
  ready: boolean;
  connectionError: string;
  lastStatus: string;
  panelConnected: boolean;
  browserSessionId: string;
  contextId: string;
  activeTabId: number | null;
  tabs: BrowserTabSummary[];
  messages: LogItem[];
  conversation: ConversationItem[];
  activity: ActivityItem[];
  progress: string;
  isResponding: boolean;
  modelState: ModelStateSummary | null;
  pendingPresetName: string;
  projects: ProjectSummary[];
  composeDraft: string;
  config: ExtensionConfig;
}

export interface SendMessagePayload {
  message: string;
  projectName?: string;
  includePageContext?: boolean;
  includeScreenshotAttachment?: boolean;
  pageContext?: PageContext | null;
  domSnapshot?: DomSnapshot | null;
  attachments?: AttachmentPayload[];
}

export const DEFAULT_CONFIG: ExtensionConfig = {
  baseUrl: "http://localhost:50001",
  apiKey: "",
  defaultProject: "",
  chatPollMs: 1500,
  commandPollMs: 1200,
  sessionPollMs: 2000,
};
