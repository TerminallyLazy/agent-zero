// jcode_harness welcome banner: surface "no provider configured" state.
// Heuristic only — defers final auth check to the daemon. Banner appears
// only when daemon_status returns an error mentioning credentials/provider.
window.jcodeLoginBanner = function () {
  return {
    needsLogin: false,
    async init() {
      try {
        const r = await fetch("/api/plugins/jcode_harness/daemon_status");
        const d = await r.json();
        // If daemon_status returns an error mentioning credentials/provider,
        // show the banner. Transient errors (network) don't trigger it.
        if (d.error && /credential|provider|login/i.test(d.error)) {
          this.needsLogin = true;
        }
      } catch (e) {
        // Don't show banner on transient errors; only confirmed state.
      }
    },
    openSettings() {
      // Routing to plugin settings depends on A0's plugin UI; emit a
      // notification with manual instructions in the meantime.
      window.$store?.notificationStore?.frontendInfo?.(
        "Open Plugins → jcode_harness → Settings to log in.",
        "jcode"
      );
    },
  };
};
