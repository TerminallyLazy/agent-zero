import { useEffect, useRef, useState } from "preact/hooks";

import { normalizeBaseUrl } from "../lib/api";
import { resolveModelButtonLabel } from "../lib/conversation";
import { connectSidePanelPort, sendRuntimeMessage } from "../lib/extension";
import type {
  AttachmentPayload,
  BackgroundState,
  DomSnapshot,
  ModelPresetSummary,
  PageContext,
  ScreenshotPreview,
} from "../lib/types";
import { DEFAULT_CONFIG } from "../lib/types";
import { FolderIcon, LogoIcon, ModelIcon, MoreIcon, PlusIcon, RefreshIcon, SendIcon, TrashIcon } from "./Icons";
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
  conversation: [],
  activity: [],
  progress: "",
  isResponding: false,
  modelState: null,
  pendingPresetName: "",
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
  "Summarize the most important parts of this page.",
  "Explain what I can do here in plain English.",
  "Tell me the safest next step to take on this screen.",
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

const formatPresetCaption = (preset: ModelPresetSummary): string => {
  return preset.summary || preset.chat.display_name || preset.chat.name;
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
  const [composerMenuOpen, setComposerMenuOpen] = useState(false);
  const [modelMenuOpen, setModelMenuOpen] = useState(false);
  const [projectMenuOpen, setProjectMenuOpen] = useState(false);
  const [moreMenuOpen, setMoreMenuOpen] = useState(false);
  const [expandedActivity, setExpandedActivity] = useState<Set<string>>(new Set());
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
    if (!state.contextId) {
      setProjectName(state.config.defaultProject || "");
    }
  }, [state.config.defaultProject, state.contextId]);

  useEffect(() => {
    if (previousTabIdRef.current !== null && previousTabIdRef.current !== state.activeTabId) {
      setPageContext(null);
      setDomSnapshot(null);
      setScreenshotPreview(null);
      setToolState(initialToolState());
    }
    previousTabIdRef.current = state.activeTabId;
  }, [state.activeTabId]);

  useEffect(() => {
    if (!modelMenuOpen && !projectMenuOpen && !moreMenuOpen && !composerMenuOpen) {
      return;
    }

    const closeMenus = () => {
      setModelMenuOpen(false);
      setProjectMenuOpen(false);
      setMoreMenuOpen(false);
      setComposerMenuOpen(false);
    };

    window.addEventListener("click", closeMenus);
    return () => window.removeEventListener("click", closeMenus);
  }, [modelMenuOpen, projectMenuOpen, moreMenuOpen, composerMenuOpen]);

  const setupReady = Boolean(state.config.baseUrl.trim() && state.config.apiKey.trim());
  const activeTab = state.tabs.find((tab) => tab.active) || null;
  const toolErrorMessage = [toolState.page.error, toolState.dom.error, toolState.screenshot.error].find(Boolean) || "";
  const selectedPresetName = state.contextId ? state.modelState?.active_preset || "" : state.pendingPresetName;
  const selectedExtras = [
    pageContext ? { key: "page", label: "Page details", onRemove: () => setPageContext(null) } : null,
    domSnapshot ? { key: "dom", label: "Interactive elements", onRemove: () => setDomSnapshot(null) } : null,
    screenshotPreview ? { key: "screenshot", label: "Screenshot", onRemove: () => setScreenshotPreview(null) } : null,
    ...manualAttachments.map((attachment) => ({
      key: attachment.filename,
      label: attachment.filename,
      onRemove: () => setManualAttachments((current) => current.filter((item) => item.filename !== attachment.filename)),
    })),
  ].filter((value): value is { key: string; label: string; onRemove: () => void } => Boolean(value));

  const resolvedMessage =
    draft.trim() ||
    (selectedExtras.length ? "Help me understand this page and tell me what to do next." : "");
  const statusText = state.connectionError || state.progress || state.lastStatus;
  const modelButtonLabel = resolveModelButtonLabel(state.modelState, state.pendingPresetName);
  const showProjectPicker = setupReady && !state.contextId && state.projects.length > 0;
  const selectedProject = state.projects.find((project) => project.name === projectName) || null;
  const projectButtonLabel = selectedProject?.title || selectedProject?.name || projectName || "No default project";

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
    setComposerMenuOpen(false);
  };

  const selectProject = (nextProjectName: string) => {
    setProjectName(nextProjectName);
    setProjectMenuOpen(false);
  };

  const submitMessage = async () => {
    if (!setupReady) {
      chrome.runtime.openOptionsPage();
      return;
    }

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
      clearEnhancements();
    } finally {
      setBusy(false);
    }
  };

  const togglePageDetails = async () => {
    if (pageContext) {
      setPageContext(null);
      setToolState((current) => ({ ...current, page: { loading: false, error: "" } }));
      setComposerMenuOpen(false);
      return;
    }

    setToolLoading("page", true);
    try {
      const result = await sendRuntimeMessage<{ ok: boolean; pageContext: PageContext }>({ type: "preview_page_context" });
      setPageContext(result.pageContext);
      setToolState((current) => ({ ...current, page: { loading: false, error: "" } }));
      setComposerMenuOpen(false);
    } catch (error) {
      setToolError("page", error);
    }
  };

  const toggleDomSnapshot = async () => {
    if (domSnapshot) {
      setDomSnapshot(null);
      setToolState((current) => ({ ...current, dom: { loading: false, error: "" } }));
      setComposerMenuOpen(false);
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
      setComposerMenuOpen(false);
    } catch (error) {
      setToolError("dom", error);
    }
  };

  const toggleScreenshot = async () => {
    if (screenshotPreview) {
      setScreenshotPreview(null);
      setToolState((current) => ({ ...current, screenshot: { loading: false, error: "" } }));
      setComposerMenuOpen(false);
      return;
    }

    setToolLoading("screenshot", true);
    try {
      const result = await sendRuntimeMessage<{ ok: boolean; screenshot: ScreenshotPreview }>({ type: "preview_screenshot" });
      setScreenshotPreview(result.screenshot);
      setToolState((current) => ({ ...current, screenshot: { loading: false, error: "" } }));
      setComposerMenuOpen(false);
    } catch (error) {
      setToolError("screenshot", error);
    }
  };

  const onPickFiles = async (event: Event) => {
    const target = event.currentTarget as HTMLInputElement;
    const files = Array.from(target.files || []);
    const loaded = await Promise.all(files.map((file) => fileToAttachment(file)));
    setManualAttachments((current) => [...current, ...loaded]);
    setComposerMenuOpen(false);
    target.value = "";
  };

  const refreshState = async () => {
    setBusy(true);
    try {
      setProjectMenuOpen(false);
      setModelMenuOpen(false);
      setMoreMenuOpen(false);
      await sendRuntimeMessage({ type: "refresh" });
    } finally {
      setBusy(false);
    }
  };

  const clearChatSurface = async () => {
    if (state.contextId) {
      setBusy(true);
      try {
        setProjectMenuOpen(false);
        setModelMenuOpen(false);
        setMoreMenuOpen(false);
        await sendRuntimeMessage({ type: "reset_chat" });
      } finally {
        setBusy(false);
      }
      return;
    }

    setDraft("");
    clearEnhancements();
  };

  const selectPreset = async (presetName: string) => {
    setBusy(true);
    try {
      await sendRuntimeMessage({ type: "select_preset", presetName });
      setModelMenuOpen(false);
    } finally {
      setBusy(false);
    }
  };

  const openModelSettings = async () => {
    const baseUrl = normalizeBaseUrl(state.config.baseUrl);
    if (!baseUrl) {
      chrome.runtime.openOptionsPage();
      return;
    }
    await chrome.tabs.create({ url: baseUrl });
    setMoreMenuOpen(false);
  };

  return (
    <div className="panel-shell">
      <header className="topbar">
        <div className="topbar-brand">
          <LogoIcon className="topbar-logo" />
        </div>

        <div className="topbar-actions">
          <button className="icon-button" title="Sync" aria-label="Sync" disabled={busy} onClick={() => void refreshState()}>
            <RefreshIcon className="button-icon" />
          </button>
          <button className="icon-button" title="Clear chat" aria-label="Clear chat" disabled={busy} onClick={() => void clearChatSurface()}>
            <TrashIcon className="button-icon" />
          </button>
          <div className="menu-anchor" onClick={(event) => event.stopPropagation()}>
            <button
              className={`icon-button ${moreMenuOpen ? "active" : ""}`}
              title="More actions"
              aria-label="More actions"
              aria-haspopup="menu"
              aria-expanded={moreMenuOpen}
              disabled={busy}
              onClick={() => {
                setMoreMenuOpen((current) => !current);
                setModelMenuOpen(false);
                setProjectMenuOpen(false);
                setComposerMenuOpen(false);
              }}
            >
              <MoreIcon className="button-icon" />
            </button>

            {moreMenuOpen ? (
              <div className="dropdown-menu overflow-menu">
                <button
                  className="dropdown-item"
                  onClick={() => {
                    setMoreMenuOpen(false);
                    chrome.runtime.openOptionsPage();
                  }}
                >
                  <span>Extension settings</span>
                  <small>Connection, defaults, and polling</small>
                </button>
                <button className="dropdown-item" onClick={() => void openModelSettings()}>
                  <span>Model settings</span>
                  <small>Open Agent Zero to adjust models and presets</small>
                </button>
                <button
                  className="dropdown-item"
                  onClick={() => {
                    setMoreMenuOpen(false);
                    void sendRuntimeMessage({ type: "reset_chat" });
                  }}
                >
                  <span>Reset chat</span>
                  <small>Clear the current conversation but keep this session</small>
                </button>
                <button
                  className="dropdown-item danger"
                  onClick={() => {
                    setMoreMenuOpen(false);
                    void sendRuntimeMessage({ type: "terminate_chat" });
                  }}
                >
                  <span>End chat</span>
                  <small>Close this session and start fresh next time</small>
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </header>

      <div className={`status-bar ${state.connectionError ? "error" : state.isResponding ? "live" : state.ready ? "ready" : ""}`}>
        <span className="status-dot" />
        <span className="status-copy">{statusText}</span>
        {activeTab?.url ? <span className="status-page">{formatUrl(activeTab.url)}</span> : null}
      </div>

      <main className="chat-stage">
        {!setupReady ? (
          <section className="empty-state setup-state">
            <div className="empty-kicker">One-time setup</div>
            <h1>Connect the extension to Agent Zero</h1>
            <p>Add your Agent Zero address and API token once, then the sidepanel can send messages and receive replies here.</p>
            <button className="primary-button" onClick={() => chrome.runtime.openOptionsPage()}>
              Open setup
            </button>
          </section>
        ) : state.conversation.length ? (
          <>
            <MessageList items={state.conversation} />
            {state.activity.length ? (
              <section className="activity-panel">
                <div className="activity-heading">Recent activity</div>
                <div className="activity-list">
                  {state.activity.slice(-3).map((item) => {
                    const isOpen = expandedActivity.has(item.id);
                    return (
                      <article key={item.id} className={`activity-item ${item.type} ${isOpen ? "expanded" : ""}`}>
                        <div
                          className="activity-item-header"
                          onClick={() =>
                            setExpandedActivity((prev) => {
                              const next = new Set(prev);
                              if (next.has(item.id)) next.delete(item.id);
                              else next.add(item.id);
                              return next;
                            })
                          }
                        >
                          <strong>{item.title}</strong>
                          <span className="activity-item-toggle">&#9660;</span>
                        </div>
                        <div className="activity-item-body">
                          <p>{item.detail}</p>
                        </div>
                      </article>
                    );
                  })}
                </div>
              </section>
            ) : null}
          </>
        ) : (
          <section className="empty-state">
            <div className="empty-kicker">Agent Zero Chrome</div>
            <h1>Browser Assistant</h1>
            <p>
              {activeTab
                ? `Ask about ${activeTab.title || "this page"} and optionally include page details, interactive elements, a screenshot, or files.`
                : "Open a regular browser tab, then ask Agent Zero for help in plain English."}
            </p>

            <div className="empty-meta">
              <span>{activeTab?.url ? formatUrl(activeTab.url) : "No page selected"}</span>
              <span>{state.contextId ? "Chat ready" : "New chat"}</span>
            </div>

            <div className="suggestion-row">
              {PROMPT_PRESETS.map((preset) => (
                <button key={preset} className="suggestion-chip" onClick={() => setDraft(preset)}>
                  {preset}
                </button>
              ))}
            </div>
          </section>
        )}
      </main>

      <footer className="composer-shell">
        {selectedExtras.length ? (
          <div className="selected-extra-row">
            {selectedExtras.map((extra) => (
              <button key={extra.key} className="selected-extra-pill" onClick={extra.onRemove}>
                {extra.label}
              </button>
            ))}
            <button className="text-button" onClick={() => clearEnhancements()}>
              Clear extras
            </button>
          </div>
        ) : null}

        {pageContext || domSnapshot || screenshotPreview ? (
          <div className="preview-row">
            {pageContext ? (
              <article className="preview-card">
                <span className="preview-label">Page details</span>
                <strong>{pageContext.title || "Untitled page"}</strong>
                <small>{formatUrl(pageContext.url)}</small>
              </article>
            ) : null}

            {domSnapshot ? (
              <article className="preview-card">
                <span className="preview-label">Interactive elements</span>
                <strong>{domSnapshot.nodes.length} items included</strong>
                <small>
                  {domSnapshot.nodes
                    .slice(0, 2)
                    .map((node) => node.label || node.aria_label || node.text || node.placeholder || node.tag)
                    .filter(Boolean)
                    .join(" • ") || "Buttons, links, and fields"}
                </small>
              </article>
            ) : null}

            {screenshotPreview ? (
              <article className="preview-card screenshot-preview">
                <span className="preview-label">Screenshot</span>
                <img src={screenshotPreview.dataUrl} alt="Current tab preview" />
              </article>
            ) : null}
          </div>
        ) : null}

        {toolErrorMessage ? <div className="inline-error">{toolErrorMessage}</div> : null}
        {state.connectionError ? <div className="inline-error">{state.connectionError}</div> : null}

        <div className="composer-card">
          <textarea
            className="composer-input"
            placeholder="Type your message here. If you only selected context, Send will use a helpful default request."
            value={draft}
            disabled={!setupReady || busy}
            onInput={(event) => setDraft((event.currentTarget as HTMLTextAreaElement).value)}
          />

          <div className="selection-badges">
            <div className="selection-badge">
              <ModelIcon className="badge-icon" />
              <span>{modelButtonLabel}</span>
            </div>
            {!state.contextId ? (
              <div className="selection-badge">
                <FolderIcon className="badge-icon" />
                <span>{projectButtonLabel}</span>
              </div>
            ) : null}
          </div>

          <div className="composer-toolbar">
            <div className="composer-left">
              <div className="menu-anchor" onClick={(event) => event.stopPropagation()}>
                <button
                  className={`attach-button ${composerMenuOpen ? "active" : ""}`}
                  title="Add page context or files"
                  aria-label="Add page context or files"
                  aria-haspopup="menu"
                  aria-expanded={composerMenuOpen}
                  disabled={!setupReady || busy}
                  onClick={() => {
                    setComposerMenuOpen((current) => !current);
                    setMoreMenuOpen(false);
                    setModelMenuOpen(false);
                    setProjectMenuOpen(false);
                  }}
                >
                  <PlusIcon className="button-icon" />
                </button>

                {composerMenuOpen ? (
                  <div className="dropdown-menu toolbar-menu attach-menu">
                    <button className={`dropdown-item ${pageContext ? "selected" : ""}`} onClick={() => void togglePageDetails()}>
                      <span>{toolState.page.loading ? "Loading page details…" : "Page details"}</span>
                      <small>{pageContext ? "Included with the next message" : "Title, URL, selection, and description"}</small>
                    </button>
                    <button className={`dropdown-item ${domSnapshot ? "selected" : ""}`} onClick={() => void toggleDomSnapshot()}>
                      <span>{toolState.dom.loading ? "Inspecting interactive elements…" : "Interactive elements"}</span>
                      <small>{domSnapshot ? "Included with the next message" : "Buttons, links, and fields from the page"}</small>
                    </button>
                    <button className={`dropdown-item ${screenshotPreview ? "selected" : ""}`} onClick={() => void toggleScreenshot()}>
                      <span>{toolState.screenshot.loading ? "Capturing screenshot…" : "Screenshot"}</span>
                      <small>{screenshotPreview ? "Included with the next message" : "Attach the current tab as an image"}</small>
                    </button>
                    <button className="dropdown-item" onClick={() => fileInputRef.current?.click()}>
                      <span>Add files</span>
                      <small>Attach local files before sending</small>
                    </button>
                  </div>
                ) : null}
              </div>

              <div className="composer-context">
                {selectedExtras.length ? `${selectedExtras.length} extras selected` : activeTab?.url ? formatUrl(activeTab.url) : "No page selected"}
              </div>
            </div>

            <div className="composer-right">
              {showProjectPicker ? (
                <div className="menu-anchor" onClick={(event) => event.stopPropagation()}>
                  <button
                    className={`picker-button ${projectMenuOpen ? "active" : ""}`}
                    title={`Default project: ${projectButtonLabel}`}
                    aria-label={`Default project: ${projectButtonLabel}`}
                    aria-haspopup="menu"
                    aria-expanded={projectMenuOpen}
                    disabled={busy}
                    onClick={() => {
                      setProjectMenuOpen((current) => !current);
                      setModelMenuOpen(false);
                      setComposerMenuOpen(false);
                      setMoreMenuOpen(false);
                    }}
                  >
                    <FolderIcon className="button-icon" />
                  </button>

                  {projectMenuOpen ? (
                    <div className="dropdown-menu toolbar-menu picker-menu picker-menu-right">
                      <button className={`dropdown-item ${!projectName ? "selected" : ""}`} onClick={() => selectProject("")}>
                        <span>No default project</span>
                        <small>Start the next chat without a project preset</small>
                      </button>
                      {state.projects.map((project) => (
                        <button
                          key={project.name}
                          className={`dropdown-item ${projectName === project.name ? "selected" : ""}`}
                          onClick={() => selectProject(project.name)}
                        >
                          <span>{project.title || project.name}</span>
                          <small>{project.description || project.name}</small>
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : null}

              <div className="menu-anchor" onClick={(event) => event.stopPropagation()}>
                <button
                  className={`picker-button ${modelMenuOpen ? "active" : ""}`}
                  title={`Model: ${modelButtonLabel}`}
                  aria-label={`Model: ${modelButtonLabel}`}
                  aria-haspopup="menu"
                  aria-expanded={modelMenuOpen}
                  disabled={!setupReady || busy}
                  onClick={() => {
                    setModelMenuOpen((current) => !current);
                    setProjectMenuOpen(false);
                    setComposerMenuOpen(false);
                    setMoreMenuOpen(false);
                  }}
                >
                  <ModelIcon className="button-icon" />
                </button>

                {modelMenuOpen ? (
                  <div className="dropdown-menu toolbar-menu picker-menu picker-menu-right">
                    {state.modelState?.allow_override ? (
                      <>
                        <button className={`dropdown-item ${selectedPresetName ? "" : "selected"}`} onClick={() => void selectPreset("")}>
                          <span>Use Agent Zero default</span>
                          <small>{state.modelState?.models.chat.display_name || "Current default model"}</small>
                        </button>
                        {state.modelState?.presets.map((preset) => (
                          <button
                            key={preset.name}
                            className={`dropdown-item ${selectedPresetName === preset.name ? "selected" : ""}`}
                            onClick={() => void selectPreset(preset.name)}
                          >
                            <span>{preset.name}</span>
                            <small>{formatPresetCaption(preset)}</small>
                          </button>
                        ))}
                      </>
                    ) : (
                      <div className="dropdown-note">Chat preset switching is turned off in your Agent Zero model settings.</div>
                    )}
                  </div>
                ) : null}
              </div>

              <button
                className="send-button"
                disabled={busy || state.isResponding || !resolvedMessage || !setupReady}
                onClick={() => void submitMessage()}
              >
                <SendIcon className="button-icon" />
                <span>{busy ? "Sending…" : state.isResponding ? "Working…" : "Send"}</span>
              </button>
            </div>
          </div>
        </div>

        <input ref={fileInputRef} type="file" multiple hidden onChange={onPickFiles} />
      </footer>
    </div>
  );
}
