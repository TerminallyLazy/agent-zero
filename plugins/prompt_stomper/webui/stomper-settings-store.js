import { createStore } from "/js/AlpineStore.js";
import { callJsonApi } from "/js/api.js";

const model = {
    settings: {},
    saving: false,
    _initialized: false,

    init() {
        if (this._initialized) return;
        this._initialized = true;
    },

    async open() {
        try {
            const result = await callJsonApi("/stomper_settings", {});
            this.settings = result.settings || {};
        } catch (e) {
            console.error("Failed to load stomper settings:", e);
        }
    },

    async save() {
        this.saving = true;
        try {
            const result = await callJsonApi("/stomper_settings", { settings: this.settings });
            this.settings = result.settings || this.settings;
        } catch (e) {
            console.error("Failed to save stomper settings:", e);
        }
        this.saving = false;
    },

    toggle(key) {
        this.settings[key] = !this.settings[key];
        this.save();
    },

    cleanup() {},
};

export const store = createStore("stomperSettings", model);
