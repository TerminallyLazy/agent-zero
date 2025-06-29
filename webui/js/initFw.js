import * as _modals from "./modals.js";
import * as _components from "./components.js";

await import("./alpine.min.js");

// add x-destroy directive
Alpine.directive(
  "destroy",
  (el, { expression }, { evaluateLater, cleanup }) => {
    const onDestroy = evaluateLater(expression);
    cleanup(() => onDestroy());
  }
);

// Wait for all modules to load before starting Alpine.js
await new Promise(resolve => {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', resolve);
  } else {
    resolve();
  }
});

// Give a small delay to ensure all module scripts have loaded
await new Promise(resolve => setTimeout(resolve, 100));

console.log("Starting Alpine.js...");
// Start Alpine.js
Alpine.start();
