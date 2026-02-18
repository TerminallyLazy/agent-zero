import { createStore } from "/js/AlpineStore.js";
import * as API from "/js/api.js";

const ENDPOINT = "/api/plugins/edgequake/edgequake_documents";

const model = {
  // Document list state
  documents: [],
  loading: false,
  total: 0,
  currentPage: 1,
  pageSize: 10,

  // Upload state
  uploadContent: "",
  uploadTitle: "",
  uploading: false,

  // Error state
  errorMessage: "",

  get totalPages() {
    if (this.total <= 0) return 1;
    return Math.ceil(this.total / this.pageSize);
  },

  async load() {
    this.errorMessage = "";
    this.loading = true;
    try {
      const response = await API.callJsonApi(ENDPOINT, {
        action: "list",
        page: this.currentPage,
        limit: this.pageSize,
      });
      if (response && response.error) {
        this.errorMessage = response.error;
        this.documents = [];
      } else {
        this.documents = response.documents || [];
        this.total = response.total || this.documents.length;
      }
    } catch (e) {
      this.errorMessage = "Failed to load documents: " + e.message;
      this.documents = [];
    } finally {
      this.loading = false;
    }
  },

  async nextPage() {
    if (this.currentPage < this.totalPages) {
      this.currentPage++;
      await this.load();
    }
  },

  async prevPage() {
    if (this.currentPage > 1) {
      this.currentPage--;
      await this.load();
    }
  },

  async upload() {
    const content = this.uploadContent.trim();
    if (!content) return;

    this.uploading = true;
    this.errorMessage = "";
    try {
      const response = await API.callJsonApi(ENDPOINT, {
        action: "upload",
        content: content,
        title: this.uploadTitle.trim() || undefined,
      });
      if (response && response.error) {
        this.errorMessage = response.error;
      } else {
        this.uploadContent = "";
        this.uploadTitle = "";
        this.currentPage = 1;
        await this.load();
      }
    } catch (e) {
      this.errorMessage = "Upload failed: " + e.message;
    } finally {
      this.uploading = false;
    }
  },

  async deleteDocument(documentId) {
    this.errorMessage = "";
    try {
      const response = await API.callJsonApi(ENDPOINT, {
        action: "delete",
        document_id: documentId,
      });
      if (response && response.error) {
        this.errorMessage = response.error;
      } else {
        await this.load();
      }
    } catch (e) {
      this.errorMessage = "Delete failed: " + e.message;
    }
  },

  destroy() {
    this.errorMessage = "";
    this.uploadContent = "";
    this.uploadTitle = "";
    this.uploading = false;
  },
};

export const store = createStore("edgequakeDocuments", model);
