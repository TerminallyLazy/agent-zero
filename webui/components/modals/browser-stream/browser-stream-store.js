import { createStore } from "/js/AlpineStore.js";

const model = {
    // Connection state
    connected: false,
    connecting: false,
    error: null,

    // Stream data
    frameData: null,
    viewportWidth: 1280,
    viewportHeight: 720,

    // WebSocket
    _ws: null,
    _reconnectTimer: null,
    _initialized: false,

    // Settings
    port: 9223,
    quality: 80,

    init() {
        if (this._initialized) return;
        this._initialized = true;
    },

    async connect(port = 9223) {
        if (this.connecting || this.connected) return;

        this.port = port;
        this.connecting = true;
        this.error = null;

        try {
            const wsUrl = `ws://localhost:${port}`;
            this._ws = new WebSocket(wsUrl);

            this._ws.onopen = () => {
                this.connected = true;
                this.connecting = false;
                this.error = null;
                console.log("Browser stream connected");
            };

            this._ws.onmessage = (event) => {
                try {
                    const msg = JSON.parse(event.data);
                    this._handleMessage(msg);
                } catch (e) {
                    console.error("Failed to parse WebSocket message:", e);
                }
            };

            this._ws.onclose = () => {
                this.connected = false;
                this.connecting = false;
                console.log("Browser stream disconnected");
                // Auto-reconnect after 2 seconds
                this._scheduleReconnect();
            };

            this._ws.onerror = (err) => {
                this.error = "Connection failed";
                this.connecting = false;
                console.error("WebSocket error:", err);
            };

        } catch (e) {
            this.error = e.message;
            this.connecting = false;
        }
    },

    _handleMessage(msg) {
        switch (msg.type) {
            case "frame":
                this.frameData = `data:image/jpeg;base64,${msg.data}`;
                if (msg.metadata) {
                    this.viewportWidth = msg.metadata.deviceWidth || this.viewportWidth;
                    this.viewportHeight = msg.metadata.deviceHeight || this.viewportHeight;
                }
                break;

            case "status":
                this.connected = msg.connected;
                if (msg.viewportWidth) this.viewportWidth = msg.viewportWidth;
                if (msg.viewportHeight) this.viewportHeight = msg.viewportHeight;
                break;

            default:
                console.log("Unknown message type:", msg.type);
        }
    },

    _scheduleReconnect() {
        if (this._reconnectTimer) clearTimeout(this._reconnectTimer);
        this._reconnectTimer = setTimeout(() => {
            if (!this.connected && !this.connecting) {
                this.connect(this.port);
            }
        }, 2000);
    },

    disconnect() {
        if (this._reconnectTimer) {
            clearTimeout(this._reconnectTimer);
            this._reconnectTimer = null;
        }
        if (this._ws) {
            this._ws.close();
            this._ws = null;
        }
        this.connected = false;
        this.connecting = false;
        this.frameData = null;
    },

    // Input injection methods
    sendMouseEvent(eventType, x, y, button = "left", clickCount = 1) {
        if (!this._ws || this._ws.readyState !== WebSocket.OPEN) return;

        this._ws.send(JSON.stringify({
            type: "input_mouse",
            eventType,
            x: Math.round(x),
            y: Math.round(y),
            button,
            clickCount
        }));
    },

    sendKeyboardEvent(eventType, key, code, modifiers = 0) {
        if (!this._ws || this._ws.readyState !== WebSocket.OPEN) return;

        this._ws.send(JSON.stringify({
            type: "input_keyboard",
            eventType,
            key,
            code,
            modifiers
        }));
    },

    sendTouchEvent(eventType, touchPoints) {
        if (!this._ws || this._ws.readyState !== WebSocket.OPEN) return;

        this._ws.send(JSON.stringify({
            type: "input_touch",
            eventType,
            touchPoints
        }));
    },

    // Mouse helpers
    click(x, y) {
        this.sendMouseEvent("mousePressed", x, y, "left", 1);
        setTimeout(() => {
            this.sendMouseEvent("mouseReleased", x, y, "left");
        }, 50);
    },

    moveMouse(x, y) {
        this.sendMouseEvent("mouseMoved", x, y);
    },

    scroll(x, y, deltaY, deltaX = 0) {
        if (!this._ws || this._ws.readyState !== WebSocket.OPEN) return;

        this._ws.send(JSON.stringify({
            type: "input_mouse",
            eventType: "mouseWheel",
            x: Math.round(x),
            y: Math.round(y),
            deltaX,
            deltaY
        }));
    },

    // Keyboard helpers
    pressKey(key, code) {
        this.sendKeyboardEvent("keyDown", key, code);
        setTimeout(() => {
            this.sendKeyboardEvent("keyUp", key, code);
        }, 50);
    },

    typeChar(char) {
        this.sendKeyboardEvent("char", char, "");
    },

    // Cleanup
    destroy() {
        this.disconnect();
        this._initialized = false;
    }
};

export const store = createStore("browserStream", model);
