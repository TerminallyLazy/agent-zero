import { defineManifest } from "@crxjs/vite-plugin";

export default defineManifest({
  manifest_version: 3,
  name: "Agent Zero Chrome Bridge",
  version: "0.1.0",
  description: "Agent Zero side panel plus live Chrome browser bridge.",
  permissions: ["activeTab", "contextMenus", "scripting", "sidePanel", "storage", "tabs"],
  host_permissions: ["http://*/*", "https://*/*"],
  background: {
    service_worker: "src/background/index.ts",
    type: "module",
  },
  action: {
    default_title: "Open Agent Zero",
  },
  side_panel: {
    default_path: "sidepanel.html",
  },
  options_page: "options.html",
  content_scripts: [
    {
      matches: ["http://*/*", "https://*/*"],
      js: ["src/content/index.ts"],
      run_at: "document_idle",
    },
  ],
});
