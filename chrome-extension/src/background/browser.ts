import type { AttachmentPayload, BridgeCommand, BrowserTabSummary, PageContext } from "../lib/types";
import { dataUrlToBase64 } from "../lib/compose";

const tabSummary = (tab: chrome.tabs.Tab, windowFocused: boolean): BrowserTabSummary => ({
  tab_id: tab.id || -1,
  window_id: tab.windowId,
  url: tab.url || "",
  title: tab.title || "",
  active: Boolean(tab.active),
  focused: Boolean(windowFocused && tab.active),
});

export async function collectTabs(): Promise<BrowserTabSummary[]> {
  const windows = await chrome.windows.getAll({ populate: true });
  return windows.flatMap((windowInfo) =>
    (windowInfo.tabs || [])
      .filter((tab): tab is chrome.tabs.Tab & { id: number } => typeof tab.id === "number")
      .map((tab) => tabSummary(tab, Boolean(windowInfo.focused))),
  );
}

export async function getActiveTab(): Promise<BrowserTabSummary | null> {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  return tab && typeof tab.id === "number" ? tabSummary(tab, true) : null;
}

async function imageDimensionsFromDataUrl(dataUrl: string): Promise<{ width: number; height: number }> {
  try {
    const response = await fetch(dataUrl);
    const blob = await response.blob();
    const bitmap = await createImageBitmap(blob);
    const dimensions = { width: bitmap.width, height: bitmap.height };
    bitmap.close();
    return dimensions;
  } catch {
    return { width: 0, height: 0 };
  }
}

export async function requestPageContext(tabId: number): Promise<PageContext | null> {
  try {
    return (await chrome.tabs.sendMessage(tabId, { type: "GET_PAGE_CONTEXT" })) as PageContext;
  } catch {
    return null;
  }
}

async function sendContentCommand(tabId: number, command: BridgeCommand): Promise<Record<string, unknown>> {
  const response = (await chrome.tabs.sendMessage(tabId, {
    type: "EXECUTE_BRIDGE_COMMAND",
    command,
  })) as { ok?: boolean; result?: Record<string, unknown>; error?: string } | undefined;

  if (!response?.ok) {
    throw new Error(response?.error || "The content script did not respond.");
  }
  return response.result || {};
}

async function focusTab(tabId: number): Promise<void> {
  const tab = await chrome.tabs.get(tabId);
  await chrome.tabs.update(tabId, { active: true });
  if (typeof tab.windowId === "number") {
    await chrome.windows.update(tab.windowId, { focused: true });
  }
}

export async function executeBridgeCommand(command: BridgeCommand): Promise<Record<string, unknown>> {
  const targetTabId =
    command.target_tab_id ??
    (await getActiveTab())?.tab_id ??
    null;

  switch (command.verb) {
    case "list_tabs": {
      const tabs = await collectTabs();
      return { tabs, active_tab_id: tabs.find((tab) => tab.active)?.tab_id ?? null };
    }
    case "open_tab": {
      const created = await chrome.tabs.create({
        url: String(command.payload.url || ""),
        active: command.payload.active !== false,
      });
      const tabs = await collectTabs();
      return { tab_id: created.id, url: created.url || "", title: created.title || "", tabs, active_tab_id: created.id };
    }
    case "focus_tab": {
      if (targetTabId == null) throw new Error("focus_tab requires a target_tab_id or an active tab.");
      await focusTab(targetTabId);
      const tab = await chrome.tabs.get(targetTabId);
      return { tab_id: targetTabId, url: tab.url || "", title: tab.title || "", tabs: await collectTabs(), active_tab_id: targetTabId };
    }
    case "close_tab": {
      if (targetTabId == null) throw new Error("close_tab requires a target_tab_id or an active tab.");
      await chrome.tabs.remove(targetTabId);
      const tabs = await collectTabs();
      return { tab_id: targetTabId, tabs, active_tab_id: tabs.find((tab) => tab.active)?.tab_id ?? null };
    }
    case "navigate": {
      if (targetTabId == null) throw new Error("navigate requires a target tab.");
      const updated = await chrome.tabs.update(targetTabId, { url: String(command.payload.url || "") });
      return { tab_id: targetTabId, url: updated.url || "", title: updated.title || "", tabs: await collectTabs(), active_tab_id: targetTabId };
    }
    case "capture_visible_tab": {
      if (targetTabId == null) throw new Error("capture_visible_tab requires a target tab.");
      await focusTab(targetTabId);
      const tab = await chrome.tabs.get(targetTabId);
      const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, {
        format: (command.payload.format as chrome.tabs.ImageDetails["format"]) || "png",
        quality: Number(command.payload.quality || 90),
      });
      const dimensions = await imageDimensionsFromDataUrl(dataUrl);
      return {
        tab_id: targetTabId,
        url: tab.url || "",
        title: tab.title || "",
        image_data_url: dataUrl,
        image_width: dimensions.width,
        image_height: dimensions.height,
        tabs: await collectTabs(),
        active_tab_id: targetTabId,
      };
    }
    case "inspect_dom":
    case "click_node":
    case "type_node":
    case "scroll": {
      if (targetTabId == null) throw new Error(`${command.verb} requires a target tab.`);
      const result = await sendContentCommand(targetTabId, command);
      return { ...result, tabs: await collectTabs(), active_tab_id: targetTabId };
    }
    default:
      throw new Error(`Unsupported bridge command: ${command.verb}`);
  }
}

export async function captureActiveTabAsAttachment(filename = "tab-screenshot.png"): Promise<AttachmentPayload | null> {
  const activeTab = await getActiveTab();
  if (!activeTab) {
    return null;
  }
  const result = await executeBridgeCommand({
    command_id: "local-capture",
    browser_session_id: "local",
    verb: "capture_visible_tab",
    payload: { format: "png", quality: 90 },
    target_tab_id: activeTab.tab_id,
    timeout_seconds: 5,
    status: "queued",
    attempts: 0,
  });
  const dataUrl = String(result.image_data_url || "");
  if (!dataUrl) {
    return null;
  }
  return { filename, base64: dataUrlToBase64(dataUrl) };
}

export async function openCurrentWindowSidePanel(): Promise<void> {
  const currentWindow = await chrome.windows.getCurrent();
  if (typeof currentWindow.id === "number") {
    await chrome.sidePanel.open({ windowId: currentWindow.id });
  }
}
