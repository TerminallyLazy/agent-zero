import * as api from "./api.js";

/**
 * @typedef {string} WebuiExtension
 */



/**
 * @typedef {Object} LoadWebuiExtensionsResponse
 * @property {WebuiExtension[]} extensions
 */

/**
 * @typedef {Object} JsExtensionImport
 * @property {string} path
 * @property {{ default: (data: any) => (void|Promise<void>) }} module
 */

/** @type {Map<string, JsExtensionImport[]>} */
const jsExtensionsCache = new Map();

/** @type {Map<string, string>} */
const htmlExtensionsCache = new Map();

export function invalidateCache() {
  jsExtensionsCache.clear();
  htmlExtensionsCache.clear();
}

/**
 * Call all JS extensions for a given extension point.
 *
 * @param {string} extensionPoint
 * @param {any} data
 * @returns {Promise<void>}
 */
export async function callJsExtensions(extensionPoint, ...data){
  const extensions = jsExtensionsCache.get(extensionPoint) || await loadJsExtensions(extensionPoint);
  for(const extension of extensions){
    try{
      await extension.module.default(...data);
    }catch(error){
      console.error(`Error calling extension: ${extension.path}`, error);
    }
  }
}

/**
 * Load JS extension modules for an extension point.
 *
 * @param {string} extensionPoint
 * @returns {Promise<JsExtensionImport[]>}
 */
export async function loadJsExtensions(extensionPoint) {
  try {
    /** @type {LoadWebuiExtensionsResponse} */
    const response = await api.callJsonApi(`/api/load_webui_extensions`, {
      extension_point: extensionPoint,
      filters: ["*.js", "*.mjs"],
    });
    /** @type {JsExtensionImport[]} */
    const imports = await Promise.all(
      response.extensions.map(async (path) => ({
        path,
        module: await import(normalizePath(path))
      }))
    );
    jsExtensionsCache.set(extensionPoint, imports);
    return imports;
  } catch (error) {
    console.error("Error loading JS extensions:", error);
    return [];
  }
}

// Load all x-component tags starting from root elements
/**
 * Load and render all HTML extensions in the given DOM roots.
 *
 * @param {Element | Document | Array<Element | Document>} [roots]
 * @returns {Promise<void>}
 */
export async function loadHtmlExtensions(roots = [document.documentElement]) {
  try {
    // Convert single root to array if needed
    /** @type {Array<Element | Document>} */
    const rootElements = Array.isArray(roots) ? roots : [roots];

    // Find all top-level components and load them in parallel
    /** @type {Element[]} */
    const extensions = rootElements.flatMap((root) =>
      Array.from(root.querySelectorAll("x-extension")),
    );

    if (extensions.length === 0) return;

    await Promise.all(
      extensions.map(async (extension) => {
        const path = extension.getAttribute("id");
        if (!path) {
          console.error("x-extension missing id attribute:", extension);
          return;
        }
        await importHtmlExtensions(path, /** @type {HTMLElement} */ (extension));
      }),
    );
  } catch (error) {
    console.error("Error loading HTML extensions:", error);
  }
}

// import all extensions for extension point via backend api
/**
 * Import all HTML extensions for an extension point and inject them as `<x-component>` tags.
 *
 * @param {string} extensionPoint
 * @param {HTMLElement} targetElement
 * @returns {Promise<void>}
 */
export async function importHtmlExtensions(extensionPoint, targetElement) {
  try {
    const cachedHtml = htmlExtensionsCache.get(extensionPoint);
    if (cachedHtml != null) {
      targetElement.innerHTML = cachedHtml;
      return;
    }

    /** @type {LoadWebuiExtensionsResponse} */
    const response = await api.callJsonApi(`/api/load_webui_extensions`, {
      extension_point: extensionPoint,
      filters: ["*.html", "*.htm", "*.xhtml"],
    });
    let combinedHTML = "";
    for (const extension of response.extensions) {
      const path = normalizePath(extension);
      combinedHTML += `<x-component path="${path}"></x-component>`;
    }
    htmlExtensionsCache.set(extensionPoint, combinedHTML);
    targetElement.innerHTML = combinedHTML;
  } catch (error) {
    console.error("Error importing HTML extensions:", error);
    return [];
  }
}

/**
 * @param {string} path
 * @returns {string}
 */
function normalizePath(path) {
  return path.startsWith("/") ? path : "/" + path;
}

// Watch for DOM changes to dynamically load x-extensions
/** @type {MutationCallback} */
const extensionObserver = new MutationObserver((mutations) => {
  for (const mutation of mutations) {
    for (const node of mutation.addedNodes) {
      if (node.nodeType === 1) {
        // ELEMENT_NODE
        // Check if this node or its descendants contain x-extension(s)
        const el = /** @type {Element} */ (node);
        if (el.matches?.("x-extension")) {
          const id = el.getAttribute("id");
          if (id) importHtmlExtensions(id, /** @type {HTMLElement} */ (el));
        } else if (node.querySelectorAll) {
          loadHtmlExtensions([node]);
        }
      }
    }
  }
});
extensionObserver.observe(document.body, { childList: true, subtree: true });
