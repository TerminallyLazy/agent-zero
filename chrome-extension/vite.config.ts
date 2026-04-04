import { crx } from "@crxjs/vite-plugin";
import preact from "@preact/preset-vite";
import { defineConfig } from "vite";

import manifest from "./src/manifest";

export default defineConfig({
  plugins: [preact(), crx({ manifest })],
  test: {
    exclude: ["tests/e2e/**", "node_modules/**", "dist/**"],
    globals: true,
  },
});
