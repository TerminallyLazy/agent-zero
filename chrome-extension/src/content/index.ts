import type { BridgeCommand, PageContext } from "../lib/types";

type CommandResult = { ok: boolean; result?: Record<string, unknown>; error?: string };

const getPageContext = (): PageContext => ({
  url: window.location.href,
  title: document.title,
  selectedText: window.getSelection()?.toString() || "",
  metaDescription: document.querySelector<HTMLMetaElement>('meta[name="description"]')?.content || "",
});

const isVisible = (element: Element): boolean => {
  const rect = element.getBoundingClientRect();
  if (!rect.width || !rect.height) return false;
  const style = window.getComputedStyle(element);
  return style.visibility !== "hidden" && style.display !== "none";
};

const buildNodeId = (element: Element): string => {
  const segments: string[] = [];
  let current: Element | null = element;
  while (current && current.tagName.toLowerCase() !== "html") {
    const parent = current.parentElement;
    const tag = current.tagName.toLowerCase();
    if (!parent) {
      segments.unshift(tag);
      break;
    }
    const siblings = Array.from(parent.children).filter((child) => child.tagName === current?.tagName);
    const index = Math.max(1, siblings.indexOf(current) + 1);
    segments.unshift(`${tag}:nth-of-type(${index})`);
    current = parent;
  }
  return segments.join(" > ");
};

const labelFor = (element: HTMLElement): string => {
  const aria = element.getAttribute("aria-label");
  if (aria) return aria;
  if (
    element instanceof HTMLInputElement ||
    element instanceof HTMLTextAreaElement ||
    element instanceof HTMLSelectElement
  ) {
    return element.labels?.[0]?.textContent?.trim() || "";
  }
  return element.innerText?.trim() || element.textContent?.trim() || "";
};

const inspectDom = (maxNodes = 40): Record<string, unknown> => {
  const selector = 'a, button, input, textarea, select, [role="button"], [contenteditable="true"], [tabindex]';
  const nodes = Array.from(document.querySelectorAll<HTMLElement>(selector))
    .filter((element) => isVisible(element))
    .slice(0, maxNodes)
    .map((element) => ({
      node_id: buildNodeId(element),
      tag: element.tagName.toLowerCase(),
      text: (element.innerText || element.textContent || "").trim().slice(0, 200),
      placeholder: (element as HTMLInputElement).placeholder || "",
      type: (element as HTMLInputElement).type || "",
      aria_label: element.getAttribute("aria-label") || "",
      label: labelFor(element),
    }));
  return {
    url: window.location.href,
    title: document.title,
    nodes,
  };
};

const resolveNode = (nodeId: string): HTMLElement | null => {
  try {
    return document.querySelector<HTMLElement>(nodeId);
  } catch {
    return null;
  }
};

const clickNode = (nodeId: string): Record<string, unknown> => {
  const node = resolveNode(nodeId);
  if (!node) throw new Error(`Node ${nodeId} was not found.`);
  node.scrollIntoView({ block: "center", behavior: "smooth" });
  node.click();
  return { node_id: nodeId, url: window.location.href, title: document.title };
};

const typeNode = (nodeId: string, text: string, clearFirst: boolean, submit: boolean): Record<string, unknown> => {
  const node = resolveNode(nodeId);
  if (!node) throw new Error(`Node ${nodeId} was not found.`);
  node.scrollIntoView({ block: "center", behavior: "smooth" });
  node.focus();

  if (node instanceof HTMLInputElement || node instanceof HTMLTextAreaElement) {
    if (clearFirst) node.value = "";
    node.value = `${clearFirst ? "" : node.value}${text}`;
    node.dispatchEvent(new Event("input", { bubbles: true }));
    node.dispatchEvent(new Event("change", { bubbles: true }));
    if (submit) node.dispatchEvent(new KeyboardEvent("keydown", { bubbles: true, key: "Enter" }));
  } else if (node.isContentEditable) {
    if (clearFirst) node.textContent = "";
    node.textContent = `${node.textContent || ""}${text}`;
    node.dispatchEvent(new Event("input", { bubbles: true }));
  } else {
    throw new Error(`Node ${nodeId} cannot receive text input.`);
  }

  return { node_id: nodeId, typed: text.length, url: window.location.href, title: document.title };
};

const scrollPage = (direction: string, amount: number): Record<string, unknown> => {
  const sign = direction === "up" ? -1 : 1;
  window.scrollBy({ top: sign * amount, behavior: "smooth" });
  return { scroll_y: window.scrollY, url: window.location.href, title: document.title };
};

const runBridgeCommand = (command: BridgeCommand): Record<string, unknown> => {
  switch (command.verb) {
    case "inspect_dom":
      return inspectDom(Number(command.payload.max_nodes || 40));
    case "click_node":
      return clickNode(String(command.payload.node_id || ""));
    case "type_node":
      return typeNode(
        String(command.payload.node_id || ""),
        String(command.payload.text || ""),
        Boolean(command.payload.clear_first),
        Boolean(command.payload.submit),
      );
    case "scroll":
      return scrollPage(String(command.payload.direction || "down"), Number(command.payload.amount || 600));
    default:
      throw new Error(`Unsupported in-page command: ${command.verb}`);
  }
};

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  try {
    if (message?.type === "GET_PAGE_CONTEXT") {
      sendResponse(getPageContext());
      return true;
    }
    if (message?.type === "EXECUTE_BRIDGE_COMMAND") {
      const result = runBridgeCommand(message.command as BridgeCommand);
      sendResponse({ ok: true, result } satisfies CommandResult);
      return true;
    }
  } catch (error) {
    sendResponse({ ok: false, error: String(error) } satisfies CommandResult);
    return true;
  }
  return false;
});
