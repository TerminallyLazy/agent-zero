import { AgentZeroClient } from "../lib/api";
import { buildBrowserContextMessage } from "../lib/compose";
import { normalizeConversation } from "../lib/conversation";
import type { AttachmentPayload, BridgeCommand, ConversationItem, DomSnapshot, LogItem, PageContext, ScreenshotPreview, SendMessagePayload } from "../lib/types";
import { captureActiveTabAsAttachment, collectTabs, executeBridgeCommand, getActiveTab, openCurrentWindowSidePanel, requestPageContext } from "./browser";
import { attachPort, getState, initializeState, patchState, setChatState, setConfig, setModelState, setProjects, setTabs } from "./store";

let chatInterval: number | null = null;
let commandInterval: number | null = null;
let sessionInterval: number | null = null;

let syncingSession = false;
let pollingLogs = false;
let pollingCommands = false;

const BRIDGE_CAPABILITIES = { bridge: "mv3", surfaces: ["sidepanel", "options", "contextMenus"] };

const client = (): AgentZeroClient | null => {
  const state = getState();
  if (!state.config.baseUrl || !state.config.apiKey) {
    return null;
  }
  return new AgentZeroClient(state.config);
};

async function syncProjects(): Promise<void> {
  const api = client();
  if (!api) {
    await setProjects([]);
    return;
  }
  try {
    const result = await api.listProjects();
    await setProjects(result.projects || []);
    await patchState({ connectionError: "" });
  } catch (error) {
    await patchState({ connectionError: String(error) });
  }
}

async function syncModelState(): Promise<void> {
  const api = client();
  const state = getState();
  if (!api) {
    await setModelState(null);
    return;
  }

  try {
    const result = await api.getModelState({
      contextId: state.contextId || undefined,
      projectName: state.contextId ? undefined : state.config.defaultProject || undefined,
    });
    await setModelState(result);
    await patchState({ connectionError: "" });
  } catch (error) {
    await setModelState(null);
    await patchState({ connectionError: String(error), lastStatus: "Could not load model state" });
  }
}

async function syncSession(): Promise<void> {
  if (syncingSession) return;
  syncingSession = true;
  try {
    const tabs = await collectTabs();
    const activeTab = tabs.find((tab) => tab.active) || null;
    await setTabs(tabs, activeTab?.tab_id ?? null);

    const api = client();
    if (!api) {
      return;
    }

    await api.upsertSession({
      browserSessionId: getState().browserSessionId,
      contextId: getState().contextId || undefined,
      activeTabId: activeTab?.tab_id ?? null,
      tabs,
      capabilities: BRIDGE_CAPABILITIES,
    });
    await patchState({ connectionError: "" });
  } catch (error) {
    await patchState({ connectionError: String(error), lastStatus: "Session sync failed" });
  } finally {
    syncingSession = false;
  }
}

async function applyLogState(messages: LogItem[], progress: string, progressActive: boolean): Promise<void> {
  const normalized = normalizeConversation(messages, { progressActive });
  const nextStatus = progressActive
    ? progress || "Agent Zero is responding…"
    : getState().contextId
      ? "Ready for the next message"
      : "Ready when you are";

  await setChatState({
    messages,
    conversation: normalized.conversation,
    activity: normalized.activity,
    progress,
    isResponding: progressActive,
  });
  await patchState({ connectionError: "", lastStatus: nextStatus });
}

async function pollLogs(): Promise<void> {
  if (pollingLogs) return;
  const state = getState();
  const api = client();
  if (!state.contextId) {
    await setChatState({
      messages: [],
      conversation: [],
      activity: [],
      progress: "",
      isResponding: false,
    });
    return;
  }
  if (!api) return;
  pollingLogs = true;
  try {
    const result = await api.getLogs(state.contextId);
    await applyLogState(result.log?.items || [], String(result.log?.progress || ""), Boolean(result.log?.progress_active));
  } catch (error) {
    const message = String(error);
    if (message.includes("Context not found")) {
      await setChatState({ messages: [], conversation: [], activity: [], progress: "", isResponding: false });
      await patchState({
        contextId: "",
        pendingPresetName: "",
        connectionError: "",
        lastStatus: "The previous chat is no longer available",
      });
      await syncModelState();
    } else {
      await patchState({ connectionError: message, lastStatus: "Chat polling failed" });
    }
  } finally {
    pollingLogs = false;
  }
}

async function pollCommands(): Promise<void> {
  if (pollingCommands) return;
  const state = getState();
  const api = client();
  if (!api || !state.panelConnected) return;
  pollingCommands = true;
  try {
    const next = await api.pullCommand(state.browserSessionId);
    const command = next.command;
    if (!command) {
      return;
    }
    try {
      const result = await executeBridgeCommand(command);
      await api.pushCommandResult({
        browserSessionId: state.browserSessionId,
        commandId: command.command_id,
        status: "completed",
        result,
        activeTabId: Number(result.active_tab_id || state.activeTabId || 0) || null,
        tabs: Array.isArray(result.tabs) ? result.tabs : state.tabs,
      });
      await patchState({ lastStatus: `Completed ${command.verb}` });
      await syncSession();
    } catch (error) {
      await api.pushCommandResult({
        browserSessionId: state.browserSessionId,
        commandId: command.command_id,
        status: "failed",
        error: String(error),
        activeTabId: state.activeTabId,
        tabs: state.tabs,
      });
      await patchState({ connectionError: String(error), lastStatus: `Bridge command failed: ${command.verb}` });
    }
  } catch (error) {
    await patchState({ connectionError: String(error), lastStatus: "Command polling failed" });
  } finally {
    pollingCommands = false;
  }
}

function restartLoops(): void {
  if (chatInterval) clearInterval(chatInterval);
  if (commandInterval) clearInterval(commandInterval);
  if (sessionInterval) clearInterval(sessionInterval);

  const state = getState();
  chatInterval = self.setInterval(() => void pollLogs(), state.config.chatPollMs);
  commandInterval = self.setInterval(() => void pollCommands(), state.config.commandPollMs);
  sessionInterval = self.setInterval(() => void syncSession(), state.config.sessionPollMs);
}

async function loadPageContextPreview(): Promise<PageContext> {
  const activeTab = await getActiveTab();
  if (!activeTab) {
    throw new Error("Open a regular browser tab before adding page details.");
  }

  const pageContext = await requestPageContext(activeTab.tab_id);
  if (!pageContext) {
    throw new Error("Page details are unavailable on this tab. Try a normal website instead of a browser-internal page.");
  }
  return pageContext;
}

async function loadDomSnapshotPreview(maxNodes = 18): Promise<DomSnapshot> {
  const activeTab = await getActiveTab();
  if (!activeTab) {
    throw new Error("Open a regular browser tab before inspecting interactive elements.");
  }

  const result = await executeBridgeCommand({
    command_id: "local-inspect-dom",
    browser_session_id: "local",
    verb: "inspect_dom",
    payload: { max_nodes: maxNodes },
    target_tab_id: activeTab.tab_id,
    timeout_seconds: 5,
    status: "queued",
    attempts: 0,
  });

  return {
    url: String(result.url || activeTab.url || ""),
    title: String(result.title || activeTab.title || ""),
    nodes: Array.isArray(result.nodes) ? (result.nodes as DomSnapshot["nodes"]) : [],
  };
}

async function loadScreenshotPreview(): Promise<ScreenshotPreview> {
  const attachment = await captureActiveTabAsAttachment();
  if (!attachment) {
    throw new Error("A screenshot could not be captured for the current tab.");
  }

  return {
    ...attachment,
    dataUrl: `data:image/png;base64,${attachment.base64}`,
  };
}

async function sendChatMessage(payload: SendMessagePayload): Promise<{ ok: boolean; contextId: string }> {
  const api = client();
  if (!api) {
    throw new Error("Set the Agent Zero base URL and API key in the extension options first.");
  }

  const stateBeforeSend = getState();
  const attachments: AttachmentPayload[] = [...(payload.attachments || [])];

  if (payload.includeScreenshotAttachment) {
    const screenshot = await captureActiveTabAsAttachment();
    if (screenshot) {
      attachments.push(screenshot);
    }
  }

  let message = payload.message.trim();
  let pageContext = payload.pageContext || null;
  let contextId = stateBeforeSend.contextId;

  if (payload.includePageContext && !pageContext) {
    try {
      pageContext = await loadPageContextPreview();
    } catch {
      pageContext = null;
    }
  }

  message = buildBrowserContextMessage(message, {
    pageContext,
    domSnapshot: payload.domSnapshot || null,
  });

  const optimisticConversation: ConversationItem[] = [
    ...stateBeforeSend.conversation,
    {
      id: `optimistic-user-${Date.now()}`,
      logNo: Number.MAX_SAFE_INTEGER - 1,
      role: "user",
      text: payload.message.trim(),
      attachments: attachments.map((attachment) => attachment.filename),
    },
    {
      id: `optimistic-assistant-${Date.now()}`,
      logNo: Number.MAX_SAFE_INTEGER,
      role: "assistant",
      text: "Agent Zero is responding…",
      attachments: [],
      pending: true,
    },
  ];

  try {
    if (!contextId) {
      const bootstrap = await api.bootstrapChat({
        browserSessionId: stateBeforeSend.browserSessionId,
        projectName: payload.projectName || stateBeforeSend.config.defaultProject || undefined,
        presetName: stateBeforeSend.pendingPresetName || undefined,
        capabilities: BRIDGE_CAPABILITIES,
      });
      contextId = bootstrap.context_id;
      await patchState({
        contextId,
        pendingPresetName: "",
      });
    }

    await setChatState({
      conversation: optimisticConversation,
      activity: stateBeforeSend.activity,
      progress: "Agent Zero is responding…",
      isResponding: true,
    });
    await patchState({
      contextId,
      composeDraft: "",
      connectionError: "",
      lastStatus: "Agent Zero is responding…",
    });

    const response = await api.sendMessage(message, {
      contextId,
      attachments,
      projectName: undefined,
      waitForResponse: false,
    });

    await patchState({
      contextId: response.context_id || contextId,
      composeDraft: "",
      connectionError: "",
      lastStatus: "Agent Zero is responding…",
    });
    await syncSession();
    await syncModelState();
    await pollLogs();
    return { ok: true, contextId: getState().contextId };
  } catch (error) {
    await setChatState({
      conversation: stateBeforeSend.conversation,
      activity: stateBeforeSend.activity,
      progress: "",
      isResponding: false,
    });
    await patchState({
      connectionError: String(error),
      lastStatus: "Message failed to send",
    });
    throw error;
  }
}

async function resetChat(): Promise<void> {
  const api = client();
  const contextId = getState().contextId;
  if (!api || !contextId) return;
  await api.resetChat(contextId);
  await setChatState({ messages: [], conversation: [], activity: [], progress: "", isResponding: false });
  await syncModelState();
  await patchState({ lastStatus: "Chat reset" });
}

async function terminateChat(): Promise<void> {
  const api = client();
  const contextId = getState().contextId;
  if (api && contextId) {
    await api.terminateChat(contextId);
  }
  await setChatState({ messages: [], conversation: [], activity: [], progress: "", isResponding: false });
  await patchState({ composeDraft: "", contextId: "", pendingPresetName: "", lastStatus: "Chat ended" });
  await syncSession();
  await syncModelState();
}

async function selectPreset(presetName: string): Promise<void> {
  const api = client();
  if (!api) {
    throw new Error("Set up the extension connection before changing models.");
  }

  const state = getState();
  if (!state.modelState?.allow_override) {
    await patchState({ lastStatus: "Chat model switching is disabled in Agent Zero" });
    return;
  }

  if (!state.contextId) {
    await patchState({
      pendingPresetName: presetName,
      lastStatus: presetName ? `Preset ready: ${presetName}` : "Using your Agent Zero default",
    });
    return;
  }

  await api.bootstrapChat({
    browserSessionId: state.browserSessionId,
    contextId: state.contextId,
    presetName: presetName || undefined,
    clearOverride: !presetName,
    capabilities: BRIDGE_CAPABILITIES,
  });
  await patchState({
    pendingPresetName: "",
    lastStatus: presetName ? `Preset switched to ${presetName}` : "Using your Agent Zero default",
  });
  await syncModelState();
}

async function ensureContextMenus(): Promise<void> {
  await chrome.contextMenus.removeAll();
  chrome.contextMenus.create({ id: "agent-zero-selection", title: "Ask Agent Zero about this", contexts: ["selection"] });
  chrome.contextMenus.create({ id: "agent-zero-page", title: "Analyze this page with Agent Zero", contexts: ["page"] });
  chrome.contextMenus.create({ id: "agent-zero-image", title: "Describe this image with Agent Zero", contexts: ["image"] });
}

chrome.runtime.onInstalled.addListener(() => {
  void ensureContextMenus();
  if (chrome.sidePanel?.setPanelBehavior) {
    void chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
  }
});

chrome.runtime.onStartup.addListener(() => {
  void ensureContextMenus();
});

chrome.runtime.onConnect.addListener((port) => {
  if (port.name === "agent-zero-sidepanel") {
    attachPort(port);
  }
});

chrome.action.onClicked.addListener(() => {
  void openCurrentWindowSidePanel();
});

chrome.contextMenus.onClicked.addListener((info) => {
  const draft =
    info.menuItemId === "agent-zero-selection"
      ? `Please help with this selection:\n\n${info.selectionText || ""}`
      : info.menuItemId === "agent-zero-image"
        ? `Describe the image at ${info.srcUrl || ""}.`
        : "Analyze the current page and summarize the most important information.";
  void patchState({ composeDraft: draft, lastStatus: "Draft prepared from context menu" });
  void openCurrentWindowSidePanel();
});

chrome.tabs.onActivated.addListener(() => void syncSession());
chrome.tabs.onRemoved.addListener(() => void syncSession());
chrome.tabs.onUpdated.addListener(() => void syncSession());
chrome.windows.onFocusChanged.addListener(() => void syncSession());

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  (async () => {
    switch (message?.type) {
      case "get_state":
        return { ok: true, state: getState() };
      case "save_config":
        await setConfig(message.config || {});
        restartLoops();
        await syncProjects();
        await syncSession();
        await syncModelState();
        return { ok: true, state: getState() };
      case "refresh":
        await syncProjects();
        await syncSession();
        await syncModelState();
        await pollLogs();
        return { ok: true, state: getState() };
      case "preview_page_context":
        return { ok: true, pageContext: await loadPageContextPreview() };
      case "preview_dom":
        return { ok: true, domSnapshot: await loadDomSnapshotPreview(Number(message.maxNodes || 18)) };
      case "preview_screenshot":
        return { ok: true, screenshot: await loadScreenshotPreview() };
      case "send_message":
        return await sendChatMessage(message.payload as SendMessagePayload);
      case "reset_chat":
        await resetChat();
        return { ok: true };
      case "terminate_chat":
        await terminateChat();
        return { ok: true };
      case "select_preset":
        await selectPreset(String(message.presetName || ""));
        return { ok: true, state: getState() };
      case "focus_browser_tab":
        await executeBridgeCommand({
          command_id: "focus-tab",
          browser_session_id: getState().browserSessionId,
          verb: "focus_tab",
          payload: {},
          target_tab_id: Number(message.tabId),
          timeout_seconds: 5,
          status: "queued",
          attempts: 0,
        });
        await syncSession();
        return { ok: true };
      default:
        return { ok: false, error: "Unsupported message" };
    }
  })()
    .then((result) => sendResponse(result))
    .catch((error) => {
      const errorMessage = error instanceof Error ? error.message : String(error);
      void patchState({
        connectionError: errorMessage,
        lastStatus: "Extension request failed",
      }).finally(() => sendResponse({ ok: false, error: errorMessage }));
    });
  return true;
});

void initializeState().then(async () => {
  restartLoops();
  await syncProjects();
  await syncSession();
  await syncModelState();
  await pollLogs();
});
