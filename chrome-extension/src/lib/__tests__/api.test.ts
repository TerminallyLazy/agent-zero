import { normalizeBaseUrl } from "../api";

describe("normalizeBaseUrl", () => {
  it("strips trailing slashes", () => {
    expect(normalizeBaseUrl("http://localhost:50001/")).toBe("http://localhost:50001");
  });

  it("strips a trailing api suffix", () => {
    expect(normalizeBaseUrl("https://agent-zero.example.com/api")).toBe("https://agent-zero.example.com");
  });
});
