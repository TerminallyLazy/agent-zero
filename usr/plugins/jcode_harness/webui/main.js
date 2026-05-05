// jcode_harness main webui page.
// Surfaces daemon status, resumable sessions, and provider OAuth login.
// All toasts route through $store.notificationStore per AGENTS.plugins.md §3.
// Backend handlers under /api/plugins/jcode_harness/... are wired in Chunk 11.
import { createStore } from "/js/AlpineStore.js";

const model = {
  daemon: { running: false, pid: null, uptime_s: 0 },
  sessions: [],
  // Per-provider connection state, refreshed on init and after each
  // successful login. Shape: {claude: {connected: true, source: "auth_file"}}
  providerStatus: {},
  // Two-leg OAuth state. After clicking a provider login button, jcode
  // emits an auth_url (and optionally a user_code). The user finishes the
  // browser flow and pastes the response back here:
  //   - Claude / Gemini: a code is shown in the browser → paste auth_code
  //   - OpenAI:          browser redirects to localhost:1455/auth/callback?...
  //                      (the redirect FAILS because --no-browser disables
  //                      jcode's local listener — the user copies the full
  //                      URL from the address bar)
  //   - Copilot:         device flow — the user enters user_code at the
  //                      shown URL, then clicks "Complete" with no paste
  //                      (jcode polls via --complete)
  loginPending: null,
  loginPasteValue: "",
  loginInFlight: false,

  async init() {
    await this.refresh();
  },

  async refresh() {
    try {
      const r = await fetch("/api/plugins/jcode_harness/daemon_status");
      if (r.ok) this.daemon = await r.json();
    } catch (e) {
      window.$store?.notificationStore?.frontendWarning?.(
        "Could not read daemon status", "jcode"
      );
    }
    await this.refreshSessions();
    await this.refreshProviderStatus();
  },

  async refreshProviderStatus() {
    try {
      const r = await fetch("/api/plugins/jcode_harness/provider_status");
      if (!r.ok) return;
      const d = await r.json();
      this.providerStatus = d.providers || {};
    } catch (e) {
      // silent — buttons fall back to "not connected" state
    }
  },

  isConnected(provider) {
    return !!this.providerStatus?.[provider]?.connected;
  },

  connectionSource(provider) {
    return this.providerStatus?.[provider]?.source || "";
  },

  async refreshSessions() {
    try {
      const r = await fetch("/api/plugins/jcode_harness/list_sessions");
      const d = await r.json();
      this.sessions = d.sessions || [];
    } catch (e) {
      this.sessions = [];
    }
  },

  async resumeSession(id) {
    try {
      const r = await fetch("/api/plugins/jcode_harness/resume_session", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ session_id: id }),
      });
      const d = await r.json();
      if (d.ok) {
        window.$store?.notificationStore?.frontendSuccess?.(
          `Resumed ${id}`, "jcode"
        );
      } else {
        window.$store?.notificationStore?.frontendError?.(
          d.error || "Resume failed", "jcode"
        );
      }
    } catch (e) {
      window.$store?.notificationStore?.frontendError?.(
        String(e), "jcode"
      );
    }
  },

  async oauthLogin(provider) {
    try {
      const r = await fetch("/api/plugins/jcode_harness/login_provider", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ provider }),
      });
      const d = await r.json();
      if (d.error) {
        window.$store?.notificationStore?.frontendError?.(d.error, "jcode");
        return;
      }
      // Surface the second-leg paste UI so the user can finish the flow.
      this.loginPending = {
        provider,
        auth_url: d.auth_url || "",
        user_code: d.user_code || "",
      };
      this.loginPasteValue = "";
      if (d.auth_url) {
        window.open(d.auth_url, "_blank", "noopener,noreferrer");
      }
    } catch (e) {
      window.$store?.notificationStore?.frontendError?.(String(e), "jcode");
    }
  },

  loginHint() {
    if (!this.loginPending) return "";
    const p = this.loginPending.provider;
    if (p === "claude" || p === "antigravity") {
      return (
        "Claude shows you a code on the success page. Copy that code and paste it below."
      );
    }
    if (p === "openai") {
      return (
        "OpenAI redirects to http://localhost:1455/auth/callback?... " +
        "(the page will fail to load — that is expected because the local " +
        "listener is disabled). Copy the FULL URL from your browser's " +
        "address bar and paste it below."
      );
    }
    if (p === "gemini") {
      return (
        "Gemini shows a code after you authorise. Copy that code and paste it below."
      );
    }
    if (p === "copilot") {
      return (
        "GitHub gives you a device code to enter at the displayed URL. " +
        "Once approved on github.com, click 'Complete login' below " +
        "(leave the field empty)."
      );
    }
    return "Finish the OAuth flow in your browser, then paste the callback URL or code below.";
  },

  async submitLoginPaste() {
    if (!this.loginPending || this.loginInFlight) return;
    const provider = this.loginPending.provider;
    const pasted = (this.loginPasteValue || "").trim();
    const body = { provider };
    // Auto-detect: a callback URL starts with http(s); a bare code does not.
    // An empty paste field falls through to `--complete` (Copilot device flow).
    if (pasted) {
      if (/^https?:\/\//i.test(pasted)) {
        body.callback_url = pasted;
      } else {
        body.auth_code = pasted;
      }
    }
    this.loginInFlight = true;
    try {
      const r = await fetch(
        "/api/plugins/jcode_harness/complete_login",
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(body),
        },
      );
      const d = await r.json();
      if (d.ok) {
        window.$store?.notificationStore?.frontendSuccess?.(
          `${provider} login complete`, "jcode"
        );
        this.loginPending = null;
        this.loginPasteValue = "";
        // Refresh provider status first so the button flips to Connected
        // immediately, then fan out to the rest of the page.
        await this.refreshProviderStatus();
        await this.refresh();
      } else {
        window.$store?.notificationStore?.frontendError?.(
          d.error || `${provider} login failed`, "jcode"
        );
      }
    } catch (e) {
      window.$store?.notificationStore?.frontendError?.(String(e), "jcode");
    } finally {
      this.loginInFlight = false;
    }
  },

  cancelLoginPaste() {
    this.loginPending = null;
    this.loginPasteValue = "";
    this.loginInFlight = false;
  },

  async purgeImported() {
    if (!confirm("Remove all plugin-imported provider profiles?")) return;
    try {
      const r = await fetch(
        "/api/plugins/jcode_harness/purge_imported_profiles",
        { method: "POST" }
      );
      const d = await r.json();
      const n = (d.purged || []).length;
      window.$store?.notificationStore?.frontendSuccess?.(
        `Purged ${n} profile${n === 1 ? "" : "s"}`, "jcode"
      );
    } catch (e) {
      window.$store?.notificationStore?.frontendError?.(String(e), "jcode");
    }
  },
};

export const store = createStore("jcodeMain", model);
