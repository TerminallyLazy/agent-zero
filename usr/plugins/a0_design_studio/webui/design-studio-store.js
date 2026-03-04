import { createStore } from "/js/AlpineStore.js";
import * as API from "/js/api.js";
import { store as notificationStore } from "/components/notifications/notification-store.js";

const GENERATE_API = "/plugins/a0_design_studio/image_generate";
const EDIT_API = "/plugins/a0_design_studio/image_edit";
const GALLERY_API = "/plugins/a0_design_studio/image_gallery";
const MODELS_API = "/plugins/a0_design_studio/image_models";

function toast(text, type = "info", timeout = 5000) {
    notificationStore.addFrontendToastOnly(type, text, "", timeout / 1000);
}

const designStudioStore = {
    // --- Canvas State ---
    canvas: {
        tool: "brush",
        color: "#000000",
        brushSize: 5,
        zoom: 1,
        panX: 0,
        panY: 0,
        history: [],
        redoStack: [],
    },

    // --- Model Selection ---
    models: {
        available: [],
        selected: "",
        loaded: false,
    },

    // --- Generation State ---
    generation: {
        prompt: "",
        size: "1024x1024",
        count: 1,
        loading: false,
        results: [],
    },

    // --- Editing State ---
    editing: {
        sourceImage: null,
        mask: null,
        editPrompt: "",
        loading: false,
        results: [],
    },

    // --- Gallery State ---
    gallery: {
        images: [],
        selectedImage: null,
        loading: false,
    },

    // --- UI State ---
    ui: {
        activePanel: "tools",
        showGrid: false,
        fullscreen: false,
    },

    // --- Lifecycle ---
    init() {},

    async onOpen() {
        await Promise.all([this.loadModels(), this.loadGallery()]);
    },

    async loadModels() {
        try {
            const response = await API.callJsonApi(MODELS_API, {});
            this.models.available = response.models || [];
            if (this.models.available.length > 0 && !this.models.selected) {
                this.models.selected = this.models.available[0].id;
            }
            this.models.loaded = true;
        } catch (err) {
            console.error("Failed to load models:", err);
        }
    },

    getSelectedModel() {
        return this.models.available.find((m) => m.id === this.models.selected);
    },

    cleanup() {
        this.generation.results = [];
        this.editing.results = [];
    },

    // --- Generation ---
    async generateImage() {
        const prompt = this.generation.prompt.trim();
        if (!prompt) {
            toast("Please enter a prompt", "warning");
            return;
        }

        const selectedModel = this.getSelectedModel();
        if (selectedModel && !selectedModel.key_set) {
            toast(
                `API key for ${selectedModel.provider.toUpperCase()} is not configured. Please add it in Settings.`,
                "error",
                8000,
            );
            return;
        }

        this.generation.loading = true;
        try {
            const response = await API.callJsonApi(GENERATE_API, {
                prompt,
                model: this.models.selected || undefined,
                size: this.generation.size,
                n: this.generation.count,
            });

            if (response.error) {
                toast(response.error, "error");
                return;
            }

            this.generation.results = response.images || [];

            if (this.generation.results.length > 0) {
                toast(`Generated ${this.generation.results.length} image(s)`, "success");
                this.loadImageToCanvas(this.generation.results[0].b64_json);
                await this.saveToGallery(
                    this.generation.results[0].b64_json,
                    { prompt, model: response.model }
                );
            }
        } catch (err) {
            toast("Generation failed: " + err.message, "error");
        } finally {
            this.generation.loading = false;
        }
    },

    // --- Editing ---
    async editImage() {
        if (!this.editing.sourceImage) {
            toast("No image loaded for editing", "warning");
            return;
        }
        const prompt = this.editing.editPrompt.trim();
        if (!prompt) {
            toast("Please enter editing instructions", "warning");
            return;
        }

        this.editing.loading = true;
        try {
            const response = await API.callJsonApi(EDIT_API, {
                image_b64: this.editing.sourceImage,
                prompt,
                mask_b64: this.editing.mask || undefined,
            });

            if (response.error) {
                toast(response.error, "error");
                return;
            }

            this.editing.results = response.images || [];
            toast("Edit analysis complete", "success");
        } catch (err) {
            toast("Edit failed: " + err.message, "error");
        } finally {
            this.editing.loading = false;
        }
    },

    // --- Gallery ---
    async loadGallery() {
        this.gallery.loading = true;
        try {
            const response = await API.callJsonApi(GALLERY_API, { action: "list" });
            this.gallery.images = response.images || [];
        } catch (err) {
            console.error("Failed to load gallery:", err);
        } finally {
            this.gallery.loading = false;
        }
    },

    async saveToGallery(imageB64, metadata = {}) {
        const filename = `generated_${Date.now()}.png`;
        try {
            await API.callJsonApi(GALLERY_API, {
                action: "save",
                image_b64: imageB64,
                filename,
                metadata,
            });
            await this.loadGallery();
        } catch (err) {
            console.error("Failed to save to gallery:", err);
        }
    },

    async deleteFromGallery(filename) {
        try {
            await API.callJsonApi(GALLERY_API, { action: "delete", filename });
            await this.loadGallery();
            toast("Image deleted", "info");
        } catch (err) {
            toast("Delete failed: " + err.message, "error");
        }
    },

    // --- Canvas Operations ---
    loadImageToCanvas(b64) {
        this.editing.sourceImage = b64;
    },

    loadGalleryImageToCanvas(image) {
        this.gallery.selectedImage = image;
        API.callJsonApi(GALLERY_API, { action: "get", filename: image.filename })
            .then((res) => {
                if (res.image_b64) {
                    this.loadImageToCanvas(res.image_b64);
                }
            });
    },

    setTool(toolName) {
        this.canvas.tool = toolName;
    },

    undo() {
        if (this.canvas.history.length > 0) {
            const state = this.canvas.history.pop();
            this.canvas.redoStack.push(state);
        }
    },

    redo() {
        if (this.canvas.redoStack.length > 0) {
            const state = this.canvas.redoStack.pop();
            this.canvas.history.push(state);
        }
    },

    saveCanvasState(dataUrl) {
        this.canvas.history.push(dataUrl);
        this.canvas.redoStack = [];
    },
};

createStore("designStudioStore", designStudioStore);
export const store = designStudioStore;
