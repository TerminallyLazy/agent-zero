// jcode_harness right-canvas panel logic.
// Listens for SidePanelSnapshot updates dispatched as `jcode:side_panel`
// events on window (emitter wired by Chunk 11 API/event bridge) and renders
// the focused page. Memory injection events show as a small chip strip.
import { createStore } from "/js/AlpineStore.js";

const model = {
  pages: [],
  focusedId: null,
  memoryEvents: [],

  init() {
    // SidePanel snapshot updates
    window.addEventListener("jcode:side_panel", (ev) => {
      const snap = (ev && ev.detail) || {};
      this.pages = snap.pages || [];
      this.focusedId = snap.focused_page_id ||
                       (this.pages[0] && this.pages[0].id) ||
                       null;
    });
    // Memory injection events (from log surface or tool wiring; Chunk 11+)
    window.addEventListener("jcode:memory_injected", (ev) => {
      const d = (ev && ev.detail) || {};
      const next = this.memoryEvents.concat([{
        ts: Date.now(),
        summary: `+${d.count || 0} mem (${d.computed_age_ms || 0}ms old)`,
      }]);
      this.memoryEvents = next.length > 20 ? next.slice(-20) : next;
    });
  },

  currentPage() {
    return this.pages.find(p => p.id === this.focusedId);
  },

  renderedContent() {
    const p = this.currentPage();
    if (!p) return "";
    // jcode currently emits only Markdown format pages.
    // Use marked.js if A0 ships it; otherwise plaintext.
    if (window.marked && typeof window.marked.parse === "function") {
      return window.marked.parse(p.content || "");
    }
    // Escape and wrap in <pre> for safety.
    const safe = (p.content || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    return `<pre>${safe}</pre>`;
  },
};

export const store = createStore("jcodePanel", model);
