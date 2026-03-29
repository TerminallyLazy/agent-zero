import { marked } from "/vendor/marked/marked.esm.js";
import { createStore } from "/js/AlpineStore.js";

export const store = createStore("markdownModal", {
    title: "",
    content: "",
    error: null,

    open(title, content) {
        this.title = title;
        this.content = content;
        this.error = null;
    },

    get renderedHtml() {
        if (!this.content) return "";
        return marked.parse(this.content, { breaks: true });
    },

    cleanup() {
        this.title = "";
        this.content = "";
        this.error = null;
    },
});
