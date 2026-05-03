import { createStore } from "/js/AlpineStore.js";
import {
    toastFrontendError,
    toastFrontendSuccess,
    toastFrontendInfo,
} from "/components/notifications/notification-store.js";

const API_CONTROL = "/api/plugins/dj_booth/dj_control";
const API_STATUS  = "/api/plugins/dj_booth/stream_status";
const API_LIB     = "/api/plugins/dj_booth/library";

export const store = createStore("djBoothStore", {
    status: null,
    library: { tracks: [], total: 0, page: 0 },
    librarySearch: "",
    isOpen: false,
    pollInterval: null,
    searchDebounce: null,

    async init() {
        await this.fetchStatus();
    },

    async onOpen() {
        this.isOpen = true;
        await this.fetchStatus();
        await this.fetchLibrary();
        this.pollInterval = setInterval(() => this.fetchStatus(), 1000);
    },

    cleanup() {
        this.isOpen = false;
        if (this.pollInterval) clearInterval(this.pollInterval);
        this.pollInterval = null;
    },

    async fetchStatus() {
        try {
            const res = await fetch(API_STATUS);
            if (res.ok) this.status = await res.json();
        } catch (e) {
            // silent — toast on mutating calls only
        }
    },

    async _post(url, body) {
        try {
            const res = await fetch(url, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
            });
            const data = await res.json();
            if (data && data.error) {
                toastFrontendError(data.error, "DJ Booth");
            }
            return data;
        } catch (e) {
            toastFrontendError(String(e), "DJ Booth");
            return null;
        }
    },

    async _control(action, params = {}) {
        const data = await this._post(API_CONTROL, { action, ...params });
        if (data && !data.error) this.status = data;
        return data;
    },

    async start() {
        const r = await this._control("start");
        if (r && !r.error) toastFrontendSuccess("Stream started", "DJ Booth");
    },
    async stop() {
        const r = await this._control("stop");
        if (r && !r.error) toastFrontendInfo("Stream stopped", "DJ Booth");
    },
    async skip() { await this._control("skip"); },
    async clearQueue() { await this._control("clear_queue"); },
    async queueTrack(path) {
        const r = await this._control("queue_track", { path });
        if (r && !r.error) toastFrontendInfo("Queued", "DJ Booth");
    },
    async scanLibrary() {
        const r = await this._control("scan_library");
        if (r && !r.error) {
            toastFrontendSuccess(`Scanned ${r.library_count} tracks`, "DJ Booth");
            await this.fetchLibrary();
        }
    },

    async fetchLibrary() {
        const data = await this._post(API_LIB, {
            action: "list",
            page: this.library.page,
            per_page: 100,
            query: this.librarySearch,
        });
        if (data && !data.error) this.library = data;
    },

    onSearchChange(val) {
        this.librarySearch = val;
        if (this.searchDebounce) clearTimeout(this.searchDebounce);
        this.searchDebounce = setTimeout(() => {
            this.library.page = 0;
            this.fetchLibrary();
        }, 300);
    },

    async copyStreamUrl() {
        if (!this.status?.stream_url) return;
        try {
            await navigator.clipboard.writeText(this.status.stream_url);
            toastFrontendSuccess("Stream URL copied", "DJ Booth");
        } catch (e) {
            toastFrontendError("Copy failed", "DJ Booth");
        }
    },

    get isRunning() { return this.status?.is_running || false; },
    get engineLabel() {
        if (!this.status?.engine) return "—";
        return this.status.engine === "ffmpeg" ? "FFMPEG (fallback)" : this.status.engine.toUpperCase();
    },
    get listenerCount() { return this.status?.listener_count || 0; },
    get currentTrack() { return this.status?.current_track || ""; },
    get queueList() { return this.status?.queue || []; },
});
