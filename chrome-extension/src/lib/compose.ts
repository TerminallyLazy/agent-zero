import type { DomNodeSummary, DomSnapshot, PageContext } from "./types";

export const buildPageContextMessage = (message: string, pageContext: PageContext | null): string => {
  if (!pageContext) {
    return message.trim();
  }

  const parts = [
    `[Chrome Page] URL: ${pageContext.url}`,
    `[Chrome Page] Title: ${pageContext.title}`,
  ];

  if (pageContext.metaDescription) {
    parts.push(`[Chrome Page] Meta Description: ${pageContext.metaDescription}`);
  }

  if (pageContext.selectedText) {
    parts.push(`[Chrome Page] Selected Text: ${pageContext.selectedText}`);
  }

  parts.push(`[User Request] ${message.trim()}`);
  return parts.join("\n");
};

const summarizeNode = (node: DomNodeSummary): string => {
  const label = node.label || node.aria_label || node.text || node.placeholder || node.type || node.tag;
  const details = [
    node.tag,
    label ? `label="${label.slice(0, 120)}"` : "",
    node.type ? `type="${node.type}"` : "",
    `node_id="${node.node_id}"`,
  ].filter(Boolean);
  return `- ${details.join(" | ")}`;
};

export const buildDomSnapshotMessage = (message: string, domSnapshot: DomSnapshot | null): string => {
  if (!domSnapshot) {
    return message.trim();
  }

  const parts = [
    `[Chrome DOM] URL: ${domSnapshot.url}`,
    `[Chrome DOM] Title: ${domSnapshot.title}`,
    `[Chrome DOM] Actionable Nodes (${domSnapshot.nodes.length}):`,
    ...domSnapshot.nodes.slice(0, 20).map((node) => summarizeNode(node)),
  ];

  parts.push(`[User Request] ${message.trim()}`);
  return parts.join("\n");
};

export const buildBrowserContextMessage = (
  message: string,
  options: {
    pageContext?: PageContext | null;
    domSnapshot?: DomSnapshot | null;
  },
): string => {
  const trimmed = message.trim();
  if (!options.pageContext && !options.domSnapshot) {
    return trimmed;
  }

  const parts = [];
  if (options.pageContext) {
    parts.push(
      `[Chrome Page] URL: ${options.pageContext.url}`,
      `[Chrome Page] Title: ${options.pageContext.title}`,
    );

    if (options.pageContext.metaDescription) {
      parts.push(`[Chrome Page] Meta Description: ${options.pageContext.metaDescription}`);
    }

    if (options.pageContext.selectedText) {
      parts.push(`[Chrome Page] Selected Text: ${options.pageContext.selectedText}`);
    }
  }

  if (options.domSnapshot) {
    parts.push(
      `[Chrome DOM] URL: ${options.domSnapshot.url}`,
      `[Chrome DOM] Title: ${options.domSnapshot.title}`,
      `[Chrome DOM] Actionable Nodes (${options.domSnapshot.nodes.length}):`,
      ...options.domSnapshot.nodes.slice(0, 20).map((node) => summarizeNode(node)),
    );
  }

  parts.push(`[User Request] ${trimmed}`);
  return parts.join("\n");
};

export const dataUrlToBase64 = (value: string): string => {
  const [, base64 = ""] = value.split(",", 2);
  return base64;
};
