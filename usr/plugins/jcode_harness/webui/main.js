// jcode_harness main webui page.
// Surfaces daemon status, resumable sessions, and provider OAuth login.
// All toasts route through $store.notificationStore per AGENTS.plugins.md §3.
// Backend handlers under /api/plugins/jcode_harness/... are wired in Chunk 11.
window.jcodeMain = function () {
  return {
    daemon: { running: false, pid: null, uptime_s: 0 },
    sessions: [],

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
        if (d.auth_url) {
          window.open(d.auth_url, "_blank");
          window.$store?.notificationStore?.frontendInfo?.(
            `Complete login for ${provider} in the new tab`, "jcode"
          );
        } else if (d.user_code) {
          window.$store?.notificationStore?.frontendInfo?.(
            `Enter code ${d.user_code} at the login URL`, "jcode"
          );
        } else if (d.error) {
          window.$store?.notificationStore?.frontendError?.(d.error, "jcode");
        }
      } catch (e) {
        window.$store?.notificationStore?.frontendError?.(String(e), "jcode");
      }
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
};
