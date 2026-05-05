// jcode_harness sidebar quick actions.
// Two buttons: kick off a new session (info toast pointing at chat) and
// browse + resume an existing cross-harness session via prompt picker.
window.jcodeQuick = function () {
  return {
    newSession() {
      window.$store?.notificationStore?.frontendInfo?.(
        "Type your coding task in chat — the agent will use jcode_session.",
        "jcode"
      );
    },
    async resumeSessionList() {
      try {
        const r = await fetch("/api/plugins/jcode_harness/list_sessions");
        const d = await r.json();
        const ss = d.sessions || [];
        if (ss.length === 0) {
          window.$store?.notificationStore?.frontendInfo?.(
            "No resumable sessions found.", "jcode"
          );
          return;
        }
        const lines = ss.slice(0, 10).map(s =>
          `${s.id} [${s.provider_key}] ${s.title || "(untitled)"}`
        ).join("\n");
        const id = prompt(`Recent sessions:\n\n${lines}\n\nEnter session id to resume:`);
        if (!id) return;
        const rr = await fetch("/api/plugins/jcode_harness/resume_session", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ session_id: id.trim() }),
        });
        const dd = await rr.json();
        if (dd.ok) {
          window.$store?.notificationStore?.frontendSuccess?.(
            `Resumed ${id}`, "jcode"
          );
        } else {
          window.$store?.notificationStore?.frontendError?.(
            dd.error || "Resume failed", "jcode"
          );
        }
      } catch (e) {
        window.$store?.notificationStore?.frontendError?.(
          String(e), "jcode"
        );
      }
    },
  };
};
