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

    // Map terse backend errors to plain-language messages users can act on.
    // Anything not in the table gets a short friendly preamble so people don't
    // see raw stack traces in the toast — the original message still shows up
    // in the notification panel for debugging.
    _friendlyError(raw) {
        const msg = String(raw || "").toLowerCase();
        if (msg.includes("stream not running")) {
            return "The DJ Booth isn't running yet. Click Start at the top to begin.";
        }
        if (msg.includes("missing 'path'") || msg.includes("missing path")) {
            return "Pick a track from the Library first.";
        }
        if (msg.includes("port") && msg.includes("in use")) {
            return "That port is already taken by another app. Try a different port in Settings → DJ Booth.";
        }
        if (msg.includes("music_dir") || msg.includes("music dir")) {
            return "Couldn't find your music folder. Check the path in Settings → DJ Booth.";
        }
        if (msg.includes("invalid deck")) {
            return "That deck doesn't exist. Pick deck A or B.";
        }
        return `Couldn't do that — see details in the notification panel. (${raw})`;
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
                toastFrontendError(this._friendlyError(data.error), "DJ Booth");
            }
            return data;
        } catch (e) {
            toastFrontendError(this._friendlyError(e), "DJ Booth");
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
    async queueTrack(path, deck = "a") {
        const r = await this._control("queue_track", { path, deck });
        if (r && !r.error) toastFrontendInfo(`Queued on deck ${deck.toUpperCase()}`, "DJ Booth");
    },
    async skip(deck = "a") { await this._control("skip", { deck }); },
    async clearQueue(deck = "a") { await this._control("clear_queue", { deck }); },
    async setCrossfader(position) { await this._control("set_crossfader", { position }); },
    async setVolume(channel, level) { await this._control("set_volume", { channel, level }); },
    async setEQ(deck, low, mid, high) { await this._control("set_eq", { deck, low, mid, high }); },
    async setPitch(deck, semitones) { await this._control("set_pitch", { deck, semitones }); },
    async setEFX(effect, param, value) { await this._control("set_efx", { effect, param, value }); },
    async announce(text) {
        if (!text || !text.trim()) return;
        const r = await this._control("announce", { text });
        if (r && !r.error) toastFrontendInfo("Announcement queued", "DJ Booth");
    },
    async syncBPM(sourceBpm, targetBpm, targetDeck = "b") {
        await this._control("sync_bpm", {
            source_bpm: sourceBpm, target_bpm: targetBpm, target_deck: targetDeck,
        });
    },

    // Selected deck — UI tracks which deck is the "active" target for library double-click
    selectedDeck: "a",
    selectDeck(d) { this.selectedDeck = d; },
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

    async analyzeTrack(path) {
        const data = await this._post(API_LIB, { action: "analyze", path });
        if (data && data.track) {
            toastFrontendSuccess(`Analyzed: BPM ${data.track.bpm}, key ${data.track.key}`, "DJ Booth");
            await this.fetchLibrary();
        }
    },

    drawWaveform(canvas, deck) {
        if (!canvas) return;
        const ctx = canvas.getContext("2d");
        const { width, height } = canvas;
        ctx.clearRect(0, 0, width, height);
        const ds = deck === "a" ? this.deckA : this.deckB;
        if (!ds.current_track) return;
        // Find matching track
        const track = (this.library.tracks || []).find(t => {
            const display = `${t.artist} - ${t.title}`.trim();
            return ds.current_track && (display === ds.current_track || ds.current_track.includes(t.title));
        });
        const peaks = track?.waveform_peaks || [];
        if (!peaks.length) {
            // flat fill
            ctx.fillStyle = deck === "a" ? "#00d4ff" : "#ff006e";
            ctx.globalAlpha = 0.3;
            ctx.fillRect(0, height/2 - 1, width, 2);
            return;
        }
        const bw = width / peaks.length;
        ctx.fillStyle = deck === "a" ? "#00d4ff" : "#ff006e";
        peaks.forEach((p, i) => {
            const h = Math.max(1, p * height);
            ctx.fillRect(i * bw, (height - h) / 2, Math.max(1, bw - 0.5), h);
        });
    },

    get spectrumBars() {
        const s = this.status?.spectrum;
        if (!s || !s.length) return Array(64).fill(0);
        return s;
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

    async copyPublicUrl() {
        const u = this.status?.public_url;
        if (!u) return;
        try {
            await navigator.clipboard.writeText(u);
            toastFrontendSuccess("Public link copied — share with anyone!", "DJ Booth");
        } catch (e) {
            toastFrontendError("Copy failed", "DJ Booth");
        }
    },

    async startShare() {
        toastFrontendInfo("Creating public link — this takes ~10 seconds...", "DJ Booth");
        const r = await this._control("start_share");
        if (r && !r.error && r.public_url) {
            toastFrontendSuccess("Public link ready! Anyone can listen now.", "DJ Booth");
        }
    },

    async stopShare() {
        await this._control("stop_share");
        toastFrontendInfo("Public link removed.", "DJ Booth");
    },

    get publicUrl() { return this.status?.public_url || ""; },
    get publicUrlStarting() { return this.status?.public_url_starting || false; },
    get publicUrlError() { return this.status?.public_url_error || ""; },
    get hasPublicUrl() { return !!this.publicUrl; },

    get isRunning() { return this.status?.is_running || false; },
    // Listener Help panel: true when stream's been running 2+ minutes and no
    // one has ever connected. Hint, not a warning — could just mean nobody
    // has tried yet. UI uses this to nudge users about port forwarding.
    get shouldShowConnectivityHint() {
        if (!this.isRunning) return false;
        if (this.status?.ever_had_listener) return false;
        const startedAt = this.status?.started_at || 0;
        if (!startedAt) return false;
        const elapsedSec = Date.now() / 1000 - startedAt;
        return elapsedSec >= 120;
    },
    get streamPort() {
        // Pulled from the stream URL so users see the right number in the hint.
        const url = this.status?.stream_url || "";
        const m = url.match(/:(\d+)/);
        return m ? m[1] : "8000";
    },
    get engineLabel() {
        if (!this.status?.engine) return "—";
        return this.status.engine === "ffmpeg" ? "FFMPEG (fallback)" : this.status.engine.toUpperCase();
    },
    get listenerCount() { return this.status?.listener_count || 0; },
    get currentTrack() { return this.deckA.current_track || ""; },
    get queueList() { return this.deckA.queue || []; },

    // Deck/mixer convenience getters
    get deckA() { return this.status?.deck_a || { queue: [], current_track: "", volume: 1.0, eq_low: 0, eq_mid: 0, eq_high: 0, pitch: 0 }; },
    get deckB() { return this.status?.deck_b || { queue: [], current_track: "", volume: 1.0, eq_low: 0, eq_mid: 0, eq_high: 0, pitch: 0 }; },
    get mixer() { return this.status?.mixer || { crossfader: 0.5, master_volume: 0.8 }; },
    get efx() {
        return this.status?.efx || {
            reverb_wet: 0.0, delay_wet: 0.0, delay_time: 0.3,
            filter_freq: 20000.0, filter_type: "lowpass",
        };
    },
});
