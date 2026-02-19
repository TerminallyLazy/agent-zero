import { createStore } from "/js/AlpineStore.js";
import { callJsonApi } from "/js/api.js";

const model = {
    patterns: [],
    loading: false,
    showAddForm: false,
    newPattern: { name: "", category: "system_rule_change", attack_type: "direct", regex: "", weight: 0.5 },
    testText: "",
    testResult: null,
    _initialized: false,

    init() {
        if (this._initialized) return;
        this._initialized = true;
    },

    async open() {
        await this.refresh();
    },

    async refresh() {
        this.loading = true;
        try {
            const result = await callJsonApi("/stomper_patterns", { action: "list" });
            this.patterns = result.patterns || [];
        } catch (e) {
            console.error("Failed to load patterns:", e);
        }
        this.loading = false;
    },

    async addPattern() {
        const p = this.newPattern;
        if (!p.name.trim() || !p.regex.trim()) return;

        try {
            const result = await callJsonApi("/stomper_patterns", {
                action: "add",
                name: p.name.trim(),
                category: p.category,
                attack_type: p.attack_type,
                regex: p.regex.trim(),
                weight: parseFloat(p.weight),
            });
            if (result.status === "added") {
                this.newPattern = { name: "", category: "system_rule_change", attack_type: "direct", regex: "", weight: 0.5 };
                this.showAddForm = false;
                await this.refresh();
            }
        } catch (e) {
            console.error("Failed to add pattern:", e);
        }
    },

    async removePattern(name) {
        try {
            await callJsonApi("/stomper_patterns", { action: "remove", name });
            await this.refresh();
        } catch (e) {
            console.error("Failed to remove pattern:", e);
        }
    },

    async togglePattern(name, enabled) {
        try {
            await callJsonApi("/stomper_patterns", { action: "toggle", name, enabled });
            const p = this.patterns.find(p => p.name === name);
            if (p) p.enabled = enabled;
        } catch (e) {
            console.error("Failed to toggle pattern:", e);
        }
    },

    async testRegex() {
        if (!this.newPattern.regex || !this.testText) {
            this.testResult = null;
            return;
        }
        try {
            this.testResult = await callJsonApi("/stomper_patterns", {
                action: "test",
                regex: this.newPattern.regex,
                text: this.testText,
            });
        } catch (e) {
            this.testResult = { matches: false, error: String(e) };
        }
    },

    cleanup() {
        this.patterns = [];
        this.showAddForm = false;
        this.testResult = null;
    },
};

export const store = createStore("stomperPatternEditor", model);
