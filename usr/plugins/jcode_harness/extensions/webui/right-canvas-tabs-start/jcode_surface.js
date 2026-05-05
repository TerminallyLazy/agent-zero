// jcode_harness right-canvas surface registration.
// Spike 0.5: register a single "jcode" surface in A0's unified right-canvas.
// Internal tabs reflect SidePanelSnapshot.pages from jcode events (rendered
// by the right-canvas-panels extension).
export default async function () {
  if (!window.$store || !window.$store.rightCanvas) return;
  const rc = window.$store.rightCanvas;
  if (rc.hasSurface && rc.hasSurface("jcode")) return;
  if (typeof rc.registerSurface === "function") {
    try {
      rc.registerSurface({
        id: "jcode",
        title: "jcode",
        icon: "psychology",  // Material Symbols name; falls back to text
        undockable: true,
      });
    } catch (e) {
      console.warn("[jcode_harness] registerSurface failed", e);
    }
  } else {
    // API differs from Spike 0.5 guess; surface registration deferred.
    console.warn("[jcode_harness] $store.rightCanvas.registerSurface not found");
  }
}
