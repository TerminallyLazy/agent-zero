import { extractVisibleUserMessage, normalizeConversation, resolveModelButtonLabel } from "../conversation";
import type { LogItem, ModelStateSummary } from "../types";

describe("extractVisibleUserMessage", () => {
  it("pulls the actual request out of the browser-context wrapper", () => {
    const text = [
      "[Chrome Page] URL: https://example.com",
      "[Chrome Page] Title: Example",
      "[User Request] Summarize the main page and tell me what matters.",
    ].join("\n");

    expect(extractVisibleUserMessage(text)).toBe("Summarize the main page and tell me what matters.");
  });
});

describe("normalizeConversation", () => {
  const baseLog = (overrides: Partial<LogItem>): LogItem => ({
    no: 1,
    type: "info",
    content: "",
    ...overrides,
  });

  it("separates transcript items from activity logs", () => {
    const items: LogItem[] = [
      baseLog({
        no: 1,
        type: "user",
        content: "[Chrome Page] URL: https://example.com\n[User Request] Check the page.",
        kvps: { attachments: ["screen.png"] },
      }),
      baseLog({ no: 2, type: "tool", heading: "Browser", content: "Captured page details" }),
      baseLog({ no: 3, type: "response", content: "Here is what stands out." }),
    ];

    const result = normalizeConversation(items);

    expect(result.conversation).toEqual([
      {
        id: "1-user",
        logNo: 1,
        role: "user",
        text: "Check the page.",
        attachments: ["screen.png"],
        timestamp: undefined,
      },
      {
        id: "3-response",
        logNo: 3,
        role: "assistant",
        text: "Here is what stands out.",
        attachments: [],
        timestamp: undefined,
      },
    ]);

    expect(result.activity).toEqual([
      {
        id: "2-tool",
        logNo: 2,
        type: "tool",
        title: "Browser",
        detail: "Captured page details",
        timestamp: undefined,
      },
    ]);
  });

  it("adds a pending assistant bubble while a response is in progress", () => {
    const items: LogItem[] = [baseLog({ no: 1, type: "user", content: "[User Request] Tell me what to do next." })];

    const result = normalizeConversation(items, { progressActive: true });

    expect(result.conversation.at(-1)).toMatchObject({
      role: "assistant",
      pending: true,
      text: "Agent Zero is responding…",
    });
  });
});

describe("resolveModelButtonLabel", () => {
  const modelState: ModelStateSummary = {
    allow_override: true,
    override: null,
    active_preset: null,
    models: {
      chat: {
        provider: "anthropic_oauth",
        provider_label: "Anthropic",
        name: "claude-opus-4-6",
        display_name: "claude-opus-4-6",
      },
      utility: {
        provider: "anthropic_oauth",
        provider_label: "Anthropic",
        name: "claude-sonnet-4-6",
        display_name: "claude-sonnet-4-6",
      },
      embedding: {
        provider: "huggingface",
        provider_label: "Hugging Face",
        name: "all-MiniLM-L6-v2",
        display_name: "all-MiniLM-L6-v2",
      },
    },
    presets: [
      {
        name: "Balance",
        summary: "gemini-3-pro-preview / gemini-3.1-flash-lite-preview",
        chat: {
          provider: "google",
          provider_label: "Google",
          name: "gemini-3-pro-preview",
          display_name: "gemini-3-pro-preview",
        },
        utility: {
          provider: "google",
          provider_label: "Google",
          name: "gemini-3.1-flash-lite-preview",
          display_name: "gemini-3.1-flash-lite-preview",
        },
      },
    ],
  };

  it("uses the active model by default", () => {
    expect(resolveModelButtonLabel(modelState, "")).toBe("claude-opus-4-6");
  });

  it("uses the pending preset chat model before the first message", () => {
    expect(resolveModelButtonLabel(modelState, "Balance")).toBe("gemini-3-pro-preview");
  });
});
