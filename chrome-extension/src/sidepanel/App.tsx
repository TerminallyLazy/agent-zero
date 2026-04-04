import { useEffect, useRef, useState } from "preact/hooks";

import { connectSidePanelPort, sendRuntimeMessage } from "../lib/extension";
import type {
  AttachmentPayload,
  BackgroundState,
  BrowserTabSummary,
  DomSnapshot,
  PageContext,
  ScreenshotPreview,
} from "../lib/types";
import { DEFAULT_CONFIG } from "../lib/types";
import { MessageList } from "./MessageList";

type PageToolKey = "page" | "dom" | "screenshot";
type ToolUiState = Record<PageToolKey, { loading: boolean; error: string }>;

const initialState: BackgroundState = {
  ready: false,
  connectionError: "",
  lastStatus: "Loading…",
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

const initialToolState = (): ToolUiState => ({
  page: { loading: false, error: "" },
  dom: { loading: false, error: "" },
  screenshot: { loading: false, error: "" },
});

const PROMPT_PRESETS = [
  "Summarize what matters on this page.",
  "What can I click or fill out here?",
  "Explain this screen like I'm new to it.",
];

const fileToAttachment = (file: File): Promise<AttachmentPayload> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error);
    reader.onload = () => {
      const result = String(reader.result || "");
      const [, base64 = ""] = result.split(",", 2);
      resolve({ filename: file.name, base64 });
    };
    reader.readAsDataURL(file);
  });

const formatUrl = (value: string): string => {
  try {
    const parsed = new URL(value);
    return `${parsed.host}${parsed.pathname === "/" ? "" : parsed.pathname}`;
  } catch {
    return value;
  }
};

export function App() {
  const [state, setState] = useState<BackgroundState>(initialState);
  const [draft, setDraft] = useState("");
  const [projectName, setProjectName] = useState("");
  const [manualAttachments, setManualAttachments] = useState<AttachmentPayload[]>([]);
  const [pageContext, setPageContext] = useState<PageContext | null>(null);
  const [domSnapshot, setDomSnapshot] = useState<DomSnapshot | null>(null);
  const [screenshotPreview, setScreenshotPreview] = useState<ScreenshotPreview | null>(null);
  const [toolState, setToolState] = useState<ToolUiState>(initialToolState);
  const [busy, setBusy] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const lastInjectedDraftRef = useRef("");
  const previousTabIdRef = useRef<number | null>(null);

  useEffect(() => {
    void sendRuntimeMessage<{ ok: boolean; state: BackgroundState }>({ type: "get_state" }).then((result) => {
      if (result.ok) {
        setState(result.state);
        setProjectName(result.state.config.defaultProject || "");
      }
    });

    const port = connectSidePanelPort();
    const handleMessage = (message: { type: string; state: BackgroundState }) => {
      if (message.type === "state") {
        setState(message.state);
      }
    };
    port.onMessage.addListener(handleMessage);
    return () => port.disconnect();
  }, []);

  useEffect(() => {
    if (state.composeDraft && state.composeDraft !== lastInjectedDraftRef.current) {
      setDraft(state.composeDraft);
      lastInjectedDraftRef.current = state.composeDraft;
    }
  }, [state.composeDraft]);

  useEffect(() => {
    if (previousTabIdRef.current !== null && previousTabIdRef.current !== state.activeTabId) {
      setPageContext(null);
      setDomSnapshot(null);
      setScreenshotPreview(null);
      setToolState(initialToolState());
    }
    previousTabIdRef.current = state.activeTabId;
  }, [state.activeTabId]);

  const setupReady = Boolean(state.config.baseUrl.trim() && state.config.apiKey.trim());
  const activeTab = state.tabs.find((tab) => tab.active) || null;
  const pendingEnhancements = [
    pageContext ? "Page details" : "",
    domSnapshot ? "Interactive elements" : "",
    screenshotPreview ? "Screenshot" : "",
    manualAttachments.length ? `${manualAttachments.length} file${manualAttachments.length === 1 ? "" : "s"}` : "",
  ].filter(Boolean);
  const resolvedMessage =
    draft.trim() ||
    (pendingEnhancements.length ? "Help me understand this page and what I should do next." : "");

  const setToolLoading = (tool: PageToolKey, loading: boolean) => {
    setToolState((current) => ({
      ...current,
      [tool]: {
        ...current[tool],
        loading,
        error: loading ? "" : current[tool].error,
      },
    }));
  };

  const setToolError = (tool: PageToolKey, error: unknown) => {
    setToolState((current) => ({
      ...current,
      [tool]: {
        loading: false,
        error: String(error || "Something went wrong."),
      },
    }));
  };

  const clearEnhancements = () => {
    setPageContext(null);
    setDomSnapshot(null);
    setScreenshotPreview(null);
    setManualAttachments([]);
    setToolState(initialToolState());
  };

  const submitMessage = async () => {
    setBusy(true);
    try {
      const attachments = [...manualAttachments];
      if (screenshotPreview) {
        attachments.push({ filename: screenshotPreview.filename, base64: screenshotPreview.base64 });
      }

      await sendRuntimeMessage({
        type: "send_message",
        payload: {
          message: resolvedMessage,
          projectName,
          pageContext,
          domSnapshot,
          attachments,
        },
      });
      setDraft("");
      lastInjectedDraftRef.current = "";
      setManualAttachments([]);
      clearEnhancements();
    } finally {
      setBusy(false);
    }
  };

  const togglePageDetails = async () => {
    if (pageContext) {
      setPageContext(null);
      setToolState((current) => ({ ...current, page: { loading: false, error: "" } }));
      return;
    }

    setToolLoading("page", true);
    try {
      const result = await sendRuntimeMessage<{ ok: boolean; pageContext: PageContext }>({ type: "preview_page_context" });
      setPageContext(result.pageContext);
      setToolState((current) => ({ ...current, page: { loading: false, error: "" } }));
    } catch (error) {
      setToolError("page", error);
    }
  };

  const toggleDomSnapshot = async () => {
    if (domSnapshot) {
      setDomSnapshot(null);
      setToolState((current) => ({ ...current, dom: { loading: false, error: "" } }));
      return;
    }

    setToolLoading("dom", true);
    try {
      const result = await sendRuntimeMessage<{ ok: boolean; domSnapshot: DomSnapshot }>({
        type: "preview_dom",
        maxNodes: 18,
      });
      setDomSnapshot(result.domSnapshot);
      setToolState((current) => ({ ...current, dom: { loading: false, error: "" } }));
    } catch (error) {
      setToolError("dom", error);
    }
  };

  const toggleScreenshot = async () => {
    if (screenshotPreview) {
      setScreenshotPreview(null);
      setToolState((current) => ({ ...current, screenshot: { loading: false, error: "" } }));
      return;
    }

    setToolLoading("screenshot", true);
    try {
      const result = await sendRuntimeMessage<{ ok: boolean; screenshot: ScreenshotPreview }>({ type: "preview_screenshot" });
      setScreenshotPreview(result.screenshot);
      setToolState((current) => ({ ...current, screenshot: { loading: false, error: "" } }));
    } catch (error) {
      setToolError("screenshot", error);
    }
  };

  const onPickFiles = async (event: Event) => {
    const target = event.currentTarget as HTMLInputElement;
    const files = Array.from(target.files || []);
    const loaded = await Promise.all(files.map((file) => fileToAttachment(file)));
    setManualAttachments((current) => [...current, ...loaded]);
    target.value = "";
  };

  const focusTab = async (tab: BrowserTabSummary) => {
    await sendRuntimeMessage({ type: "focus_browser_tab", tabId: tab.tab_id });
  };

  const removeAttachment = (filename: string) => {
    setManualAttachments((current) => current.filter((attachment) => attachment.filename !== filename));
  };

  return (
    <div className="panel-shell">
      <header className="panel-header">
        <div className="header-copy">
          <div className="eyebrow">Agent Zero Chrome</div>
          <h1>Browser Assistant</h1>
          <p>
            {activeTab
              ? `Working with ${activeTab.title || "your current tab"}`
              : "Open a regular browser tab and ask Agent Zero for help."}
          </p>
        </div>

        <div className="header-actions">
          <div className={`status-pill ${state.connectionError ? "error" : "ok"}`}>
            {state.connectionError ? "Needs attention" : state.lastStatus}
          </div>
          <button className="secondary-button" onClick={() => chrome.runtime.openOptionsPage()}>
            Open Setup
          </button>
        </div>
      </header>

      {!setupReady ? (
        <section className="setup-card">
          <div>
            <div className="section-label">Before you start</div>
            <h2>Finish the one-time setup</h2>
            <p>Add your Agent Zero address and API token once, then this panel can talk to your local app automatically.</p>
          </div>
          <div className="setup-actions">
            <button className="primary-button" onClick={() => chrome.runtime.openOptionsPage()}>
              Open guided setup
            </button>
          </div>
        </section>
      ) : null}

      <section className="overview-grid">
        <article className="overview-card">
          <div className="section-label">Current page</div>
          <h2>{activeTab?.title || "No page selected"}</h2>
          <p>{activeTab?.url ? formatUrl(activeTab.url) : "Switch to a normal website to capture page details."}</p>
          <div className="overview-meta">
            <span>{state.tabs.length} open tab{state.tabs.length === 1 ? "" : "s"}</span>
            <span>{state.contextId ? "Chat connected" : "New chat"}</span>
          </div>
        </article>

        <article className="overview-card">
          <div className="section-label">Included with next message</div>
          <h2>{pendingEnhancements.length ? pendingEnhancements.join(" • ") : "Just your message"}</h2>
          <p>
            {pendingEnhancements.length
              ? "Everything selected below will be bundled into the next request."
              : "Choose page details, interactive elements, a screenshot, or files before sending."}
          </p>
          {pendingEnhancements.length ? (
            <button className="text-button" onClick={() => clearEnhancements()}>
              Clear extras
            </button>
          ) : null}
        </article>
      </section>

      <section className="tool-section">
        <div className="section-heading">
          <div>
            <div className="section-label">Page tools</div>
            <h2>Choose exactly what to include</h2>
          </div>
          <button className="secondary-button" onClick={() => void sendRuntimeMessage({ type: "refresh" })}>
            Refresh state
          </button>
        </div>

        <div className="tool-grid">
          <button
            className={`tool-card ${pageContext ? "active" : ""}`}
            disabled={busy}
            onClick={() => void togglePageDetails()}
          >
            <div className="tool-card-header">
              <strong>Page details</strong>
              <span>{toolState.page.loading ? "Loading…" : pageContext ? "Included" : "Off"}</span>
            </div>
            <p>Adds the page title, URL, selected text, and meta description to your next message.</p>
            <small>Click again to remove it.</small>
          </button>

          <button
            className={`tool-card ${domSnapshot ? "active" : ""}`}
            disabled={busy}
            onClick={() => void toggleDomSnapshot()}
          >
            <div className="tool-card-header">
              <strong>Interactive elements</strong>
              <span>{toolState.dom.loading ? "Scanning…" : domSnapshot ? "Included" : "Off"}</span>
            </div>
            <p>Collects the main buttons, links, and fields so Agent Zero can reason about what you can do next.</p>
            <small>Click again to remove it.</small>
          </button>

          <button
            className={`tool-card ${screenshotPreview ? "active" : ""}`}
            disabled={busy}
            onClick={() => void toggleScreenshot()}
          >
            <div className="tool-card-header">
              <strong>Screenshot</strong>
              <span>{toolState.screenshot.loading ? "Capturing…" : screenshotPreview ? "Included" : "Off"}</span>
            </div>
            <p>Attaches a screenshot of the current tab so the agent can see the page as you do.</p>
            <small>Click again to remove it.</small>
          </button>
        </div>

        {toolState.page.error ? <div className="inline-error">{toolState.page.error}</div> : null}
        {toolState.dom.error ? <div className="inline-error">{toolState.dom.error}</div> : null}
        {toolState.screenshot.error ? <div className="inline-error">{toolState.screenshot.error}</div> : null}

        <div className="preview-grid">
          {pageContext ? (
            <article className="preview-card">
              <div className="preview-label">Page details</div>
              <h3>{pageContext.title || "Untitled page"}</h3>
              <p>{formatUrl(pageContext.url)}</p>
              {pageContext.metaDescription ? <p>{pageContext.metaDescription}</p> : null}
              {pageContext.selectedText ? (
                <blockquote>{pageContext.selectedText.slice(0, 180)}</blockquote>
              ) : (
                <p>No text is selected on the page right now.</p>
              )}
            </article>
          ) : null}

          {domSnapshot ? (
            <article className="preview-card">
              <div className="preview-label">Interactive elements</div>
              <h3>{domSnapshot.nodes.length} elements ready</h3>
              <ul className="node-list">
                {domSnapshot.nodes.slice(0, 6).map((node) => (
                  <li key={node.node_id}>
                    <strong>{node.label || node.aria_label || node.text || node.placeholder || node.tag}</strong>
                    <span>{node.tag}{node.type ? ` • ${node.type}` : ""}</span>
                  </li>
                ))}
              </ul>
            </article>
          ) : null}

          {screenshotPreview ? (
            <article className="preview-card screenshot-card">
              <div className="preview-label">Screenshot</div>
              <img src={screenshotPreview.dataUrl} alt="Current tab preview" />
            </article>
          ) : null}
        </div>
      </section>

      <section className="tabs-panel">
        <div className="section-label">Open tabs</div>
        <div className="tabs-strip">
          {state.tabs.map((tab) => (
            <button key={tab.tab_id} className={`tab-chip ${tab.active ? "active" : ""}`} onClick={() => void focusTab(tab)}>
              <span>{tab.title || "(untitled tab)"}</span>
              <small>{formatUrl(tab.url) || `#${tab.tab_id}`}</small>
            </button>
          ))}
        </div>
      </section>

      <section className="composer">
        <div className="section-heading compact">
          <div>
            <div className="section-label">Ask Agent Zero</div>
            <h2>Keep it simple</h2>
          </div>
          <button className="secondary-button" onClick={() => fileInputRef.current?.click()}>
            Add files
          </button>
        </div>

        <div className="preset-row">
          {PROMPT_PRESETS.map((preset) => (
            <button key={preset} className="preset-chip" onClick={() => setDraft(preset)}>
              {preset}
            </button>
          ))}
        </div>

        <label className="field">
          <span>Project</span>
          <select value={projectName} onChange={(event) => setProjectName((event.currentTarget as HTMLSelectElement).value)}>
            <option value="">Use the default project</option>
            {state.projects.map((project) => (
              <option key={project.name} value={project.name}>
                {project.title || project.name}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>Your message</span>
          <textarea
            placeholder="Ask in plain English. If you only selected page tools, Send will use a helpful default request."
            value={draft}
            onInput={(event) => setDraft((event.currentTarget as HTMLTextAreaElement).value)}
          />
        </label>

        <div className="attachment-row">
          {manualAttachments.map((attachment) => (
            <button key={attachment.filename} className="attachment-pill" onClick={() => removeAttachment(attachment.filename)}>
              {attachment.filename}
            </button>
          ))}
          {screenshotPreview ? (
            <button className="attachment-pill" onClick={() => setScreenshotPreview(null)}>
              Screenshot ready
            </button>
          ) : null}
        </div>

        <div className="composer-footer">
          <div className="footer-actions">
            <button className="secondary-button" onClick={() => void sendRuntimeMessage({ type: "reset_chat" })}>
              Reset chat
            </button>
            <button className="text-button" onClick={() => void sendRuntimeMessage({ type: "terminate_chat" })}>
              End chat
            </button>
          </div>

          <button className="primary-button" disabled={busy || !resolvedMessage} onClick={() => void submitMessage()}>
            {busy ? "Sending…" : "Send"}
          </button>
        </div>

        <input ref={fileInputRef} type="file" multiple hidden onChange={onPickFiles} />
      </section>

      {state.connectionError ? <div className="error-banner">{state.connectionError}</div> : null}

      <MessageList items={state.messages} />
    </div>
  );
}
