import { createStore } from "/js/AlpineStore.js";
import { processA2UIMessages } from "/components/a2ui/a2ui-renderer.js";

/**
 * Canvas Store - A2UI Visual Workspace
 *
 * The Canvas is a dedicated visual workspace where agents can create
 * interactive UI components using the A2UI (Agent-to-UI) protocol.
 *
 * A2UI surfaces are rendered in real-time as agents send:
 * - surfaceUpdate: Defines component structure
 * - dataModelUpdate: Updates data bindings
 * - beginRendering: Triggers render
 * - deleteSurface: Removes a surface
 */

const model = {
  // Panel state
  isOpen: false,
  isExpanded: false,
  panelWidth: 500,
  loading: false,
  error: null,

  // A2UI state - multiple surfaces can exist
  surfaces: {},  // Map of surfaceId -> { messages: [], rendered: false }
  activeSurfaceId: null,
  autoOpenEnabled: true,  // Auto-open when A2UI content arrives

  /**
   * Toggle canvas panel open/close
   */
  toggle() {
    if (this.isOpen) {
      this.close();
    } else {
      this.open();
    }
  },

  /**
   * Open canvas panel
   */
  open() {
    this.isOpen = true;
    document.body.classList.add('canvas-open');
    this.updatePanelWidth();

    // Render any existing surfaces
    this.renderActiveSurface();
  },

  /**
   * Close canvas panel
   */
  close() {
    this.isOpen = false;
    this.isExpanded = false;
    document.body.classList.remove('canvas-open');
    document.body.classList.remove('canvas-expanded');
  },

  /**
   * Toggle expanded mode
   */
  toggleExpand() {
    this.isExpanded = !this.isExpanded;
    if (this.isExpanded) {
      document.body.classList.add('canvas-expanded');
    } else {
      document.body.classList.remove('canvas-expanded');
    }
    this.updatePanelWidth();
  },

  /**
   * Set panel width (for resize)
   */
  setWidth(width) {
    const minWidth = 350;
    const maxWidth = window.innerWidth - 400;
    this.panelWidth = Math.max(minWidth, Math.min(maxWidth, width));
    this.updatePanelWidth();
  },

  /**
   * Update CSS variable for panel width
   */
  updatePanelWidth() {
    const container = document.getElementById('canvas-panel-container');
    if (container) {
      if (this.isExpanded) {
        container.style.width = '70%';
      } else {
        container.style.width = this.panelWidth + 'px';
      }
    }
  },

  /**
   * Receive an A2UI message from the agent
   * This is called when a2ui type messages come through the poll
   *
   * @param {string} surfaceId - The surface identifier
   * @param {Array} messages - Array of A2UI protocol messages
   * @param {Object} options - Additional options (heading, content for fallback)
   */
  receiveA2UIMessage(surfaceId, messages, options = {}) {
    if (!surfaceId) {
      surfaceId = 'main';
    }

    // Clean up heading - strip icon:// prefix for display
    let heading = options.heading || 'UI Component';
    heading = heading.replace(/^icon:\/\/\w+\s*/, '').trim() || 'UI Component';

    // Check for deleteSurface first
    for (const msg of messages) {
      if (msg.deleteSurface) {
        delete this.surfaces[surfaceId];
        if (this.activeSurfaceId === surfaceId) {
          this.activeSurfaceId = Object.keys(this.surfaces)[0] || null;
        }
        this.renderActiveSurface();
        return;
      }
    }

    // Replace surface state (don't accumulate - each update is complete)
    const hasBeginRendering = messages.some(m => m.beginRendering);
    this.surfaces[surfaceId] = {
      messages: messages,
      rendered: hasBeginRendering,
      heading: heading,
      fallbackContent: options.content || ''
    };

    // Set as active surface if none selected
    if (!this.activeSurfaceId) {
      this.activeSurfaceId = surfaceId;
    }

    // Auto-open panel when A2UI content arrives
    if (this.autoOpenEnabled && !this.isOpen && hasBeginRendering) {
      this.open();
    }

    // Render if panel is open
    if (this.isOpen) {
      this.renderActiveSurface();
    }
  },

  /**
   * Render the active surface in the canvas panel
   */
  renderActiveSurface() {
    const container = document.getElementById('canvas-a2ui-container');
    if (!container) return;

    if (!this.activeSurfaceId || !this.surfaces[this.activeSurfaceId]) {
      container.innerHTML = `
        <div class="canvas-empty-state">
          <svg xmlns="http://www.w3.org/2000/svg" height="48" viewBox="0 -960 960 960" width="48" fill="currentColor" opacity="0.3">
            <path d="M200-120q-33 0-56.5-23.5T120-200v-560q0-33 23.5-56.5T200-840h560q33 0 56.5 23.5T840-760v560q0 33-23.5 56.5T760-120H200Zm0-80h560v-480H200v480Zm40-40h200v-200H240v200Zm240 0h200v-80H480v80Zm0-120h200v-80H480v80Zm-240-120h440v-120H240v120Z"/>
          </svg>
          <p>Waiting for agent to create UI components...</p>
          <p class="canvas-hint">The agent can use the a2ui_component tool to create interactive interfaces here.</p>
        </div>
      `;
      return;
    }

    const surface = this.surfaces[this.activeSurfaceId];

    if (!surface.rendered || surface.messages.length === 0) {
      container.innerHTML = `
        <div class="canvas-loading-state">
          <div class="canvas-loading-spinner"></div>
          <p>Building UI...</p>
        </div>
      `;
      return;
    }

    try {
      // Use the A2UI renderer to process messages
      processA2UIMessages(surface.messages, container, {
        surfaceId: this.activeSurfaceId
      });
    } catch (e) {
      console.error("Canvas A2UI render error:", e);
      container.innerHTML = `
        <div class="canvas-error-state">
          <p>Error rendering UI: ${e.message}</p>
          ${surface.fallbackContent ? `<div class="canvas-fallback">${surface.fallbackContent}</div>` : ''}
        </div>
      `;
    }
  },

  /**
   * Switch to a different surface
   */
  switchSurface(surfaceId) {
    if (this.surfaces[surfaceId]) {
      this.activeSurfaceId = surfaceId;
      this.renderActiveSurface();
    }
  },

  /**
   * Get list of available surfaces
   */
  getSurfaceList() {
    return Object.keys(this.surfaces).map(id => ({
      id,
      heading: this.surfaces[id].heading,
      rendered: this.surfaces[id].rendered
    }));
  },

  /**
   * Clear all surfaces (e.g., on chat reset)
   */
  clearSurfaces() {
    this.surfaces = {};
    this.activeSurfaceId = null;
    if (this.isOpen) {
      this.renderActiveSurface();
    }
  },

  /**
   * Reset state completely
   */
  resetState() {
    this.isOpen = false;
    this.isExpanded = false;
    this.panelWidth = 500;
    this.loading = false;
    this.error = null;
    this.surfaces = {};
    this.activeSurfaceId = null;
    document.body.classList.remove('canvas-open');
    document.body.classList.remove('canvas-expanded');
  }
};

export const store = createStore("canvasStore", model);
