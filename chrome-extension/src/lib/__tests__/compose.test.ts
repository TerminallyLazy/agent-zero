import { buildBrowserContextMessage, buildDomSnapshotMessage, buildPageContextMessage, dataUrlToBase64 } from "../compose";

describe("buildPageContextMessage", () => {
  it("embeds page context headers", () => {
    expect(
      buildPageContextMessage("Summarize this page", {
        url: "https://example.com",
        title: "Example",
        selectedText: "Selected text",
        metaDescription: "Meta copy",
      }),
    ).toContain("[Chrome Page] URL: https://example.com");
  });
});

describe("dataUrlToBase64", () => {
  it("removes the data url prefix", () => {
    expect(dataUrlToBase64("data:image/png;base64,abc123")).toBe("abc123");
  });
});

describe("buildDomSnapshotMessage", () => {
  it("includes actionable node summaries", () => {
    expect(
      buildDomSnapshotMessage("Find the next action", {
        url: "https://example.com",
        title: "Example",
        nodes: [
          {
            node_id: "body > button:nth-of-type(1)",
            tag: "button",
            text: "Continue",
            placeholder: "",
            type: "button",
            aria_label: "",
            label: "Continue",
          },
        ],
      }),
    ).toContain('[Chrome DOM] Actionable Nodes (1):');
  });
});

describe("buildBrowserContextMessage", () => {
  it("combines page context and dom details", () => {
    const message = buildBrowserContextMessage("Help me here", {
      pageContext: {
        url: "https://example.com",
        title: "Example",
        selectedText: "",
        metaDescription: "Meta copy",
      },
      domSnapshot: {
        url: "https://example.com",
        title: "Example",
        nodes: [],
      },
    });

    expect(message).toContain("[Chrome Page] URL: https://example.com");
    expect(message).toContain("[Chrome DOM] Actionable Nodes (0):");
    expect(message).toContain("[User Request] Help me here");
  });
});
