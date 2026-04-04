import type { ActivityItem, ConversationItem, LogItem, ModelPresetSummary, ModelStateSummary } from "./types";

const HUMANIZED_TYPE_LABELS: Record<string, string> = {
  agent: "Agent step",
  browser: "Browser",
  error: "Error",
  info: "Update",
  tool: "Tool",
  warning: "Warning",
};

const USER_REQUEST_PATTERN = /\[User Request\]\s*([\s\S]*)$/i;

const extractReadableText = (obj: Record<string, unknown>): string => {
  // Agent Zero response objects contain structured fields — extract the useful parts
  const parts: string[] = [];

  // tool_args.text is the main human-readable response content
  if (obj.tool_args && typeof obj.tool_args === "object") {
    const args = obj.tool_args as Record<string, unknown>;
    if (typeof args.text === "string" && args.text.trim()) {
      parts.push(args.text.trim());
    }
  }

  // Fallback: headline is a short summary
  if (!parts.length && typeof obj.headline === "string" && obj.headline.trim()) {
    parts.push(obj.headline.trim());
  }

  // Fallback: content/message fields
  for (const key of ["content", "message", "text", "result", "output"]) {
    if (!parts.length && typeof obj[key] === "string" && (obj[key] as string).trim()) {
      parts.push((obj[key] as string).trim());
    }
  }

  return parts.join("\n\n");
};

export const renderLogContent = (value: unknown): string => {
  if (typeof value === "string") {
    return value.trim();
  }
  if (value == null) {
    return "";
  }
  if (typeof value === "object" && !Array.isArray(value)) {
    const readable = extractReadableText(value as Record<string, unknown>);
    if (readable) {
      return readable;
    }
  }
  return JSON.stringify(value, null, 2).trim();
};

export const extractVisibleUserMessage = (value: string): string => {
  const trimmed = value.trim();
  const match = trimmed.match(USER_REQUEST_PATTERN);
  if (!match?.[1]) {
    return trimmed;
  }
  return match[1].trim() || trimmed;
};

const attachmentNames = (item: LogItem): string[] => {
  const raw = item.kvps?.attachments;
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw.filter((value): value is string => typeof value === "string" && value.trim().length > 0);
};

const humanizeType = (value: string): string => {
  if (HUMANIZED_TYPE_LABELS[value]) {
    return HUMANIZED_TYPE_LABELS[value];
  }
  if (!value) {
    return "Update";
  }
  return value
    .split(/[_\-\s]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
};

const extractTitle = (item: LogItem): string => {
  if (item.heading?.trim()) return item.heading.trim();
  // Pull headline from structured content if available
  if (item.content && typeof item.content === "object" && !Array.isArray(item.content)) {
    const obj = item.content as Record<string, unknown>;
    if (typeof obj.headline === "string" && obj.headline.trim()) {
      return obj.headline.trim();
    }
  }
  return humanizeType(item.type);
};

const summarizeActivity = (item: LogItem, text: string): ActivityItem => {
  const detail = text || (item.kvps ? renderLogContent(item.kvps) : "");
  return {
    id: `${item.no}-${item.id || item.type}`,
    logNo: item.no,
    type: item.type,
    title: extractTitle(item),
    detail,
    timestamp: item.timestamp,
  };
};

export const normalizeConversation = (
  items: LogItem[],
  options: { progressActive?: boolean } = {},
): { conversation: ConversationItem[]; activity: ActivityItem[] } => {
  const conversation: ConversationItem[] = [];
  const activity: ActivityItem[] = [];

  for (const item of items) {
    const text = renderLogContent(item.content);
    const id = `${item.no}-${item.id || item.type}`;

    if (item.type === "user") {
      conversation.push({
        id,
        logNo: item.no,
        role: "user",
        text: extractVisibleUserMessage(text),
        attachments: attachmentNames(item),
        timestamp: item.timestamp,
      });
      continue;
    }

    if (item.type === "response") {
      conversation.push({
        id,
        logNo: item.no,
        role: "assistant",
        text,
        attachments: [],
        timestamp: item.timestamp,
      });
      continue;
    }

    activity.push(summarizeActivity(item, text));
  }

  if (options.progressActive) {
    const lastUserIndex = conversation.map((item) => item.role).lastIndexOf("user");
    const lastAssistantIndex = conversation.map((item) => item.role).lastIndexOf("assistant");

    if (lastAssistantIndex === -1 || lastUserIndex > lastAssistantIndex) {
      conversation.push({
        id: "pending-assistant",
        logNo: Number.MAX_SAFE_INTEGER,
        role: "assistant",
        text: "Agent Zero is responding…",
        attachments: [],
        pending: true,
      });
    } else {
      conversation[lastAssistantIndex] = {
        ...conversation[lastAssistantIndex],
        text: conversation[lastAssistantIndex].text || "Agent Zero is responding…",
        pending: true,
      };
    }
  }

  return { conversation, activity };
};

export const findPresetByName = (
  modelState: ModelStateSummary | null,
  presetName: string | null | undefined,
): ModelPresetSummary | null => {
  if (!modelState || !presetName) {
    return null;
  }
  return modelState.presets.find((preset) => preset.name === presetName) || null;
};

export const resolveModelButtonLabel = (
  modelState: ModelStateSummary | null,
  pendingPresetName: string,
): string => {
  const pendingPreset = findPresetByName(modelState, pendingPresetName);
  if (pendingPreset?.chat.display_name) {
    return pendingPreset.chat.display_name;
  }
  return modelState?.models.chat.display_name || "Agent Zero";
};
