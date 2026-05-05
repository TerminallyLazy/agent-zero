// jcode_harness right-canvas panel logic.
// Listens for SidePanelSnapshot updates dispatched as `jcode:side_panel`
// events on window (emitter wired by Chunk 11 API/event bridge) and renders
// the focused page. Memory injection events show as a small chip strip.
window.jcodePanel = function () {
  return {
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
        this.memoryEvents.push({
          ts: Date.now(),
          summary: `+${d.count || 0} mem (${d.computed_age_ms || 0}ms old)`,
        });
        if (this.memoryEvents.length > 20) {
          this.memoryEvents = this.memoryEvents.slice(-20);
        }
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
};
