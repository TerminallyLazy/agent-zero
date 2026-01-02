import { createStore } from "/js/AlpineStore.js";
import { callJsonApi } from "/js/api.js";

const THEME = {
  textHints: {
    h1: "a2ui-text-h1",
    h2: "a2ui-text-h2",
    h3: "a2ui-text-h3",
    h4: "a2ui-text-h4",
    h5: "a2ui-text-h5",
    h6: "a2ui-text-h6",
    body: "a2ui-text-body",
    caption: "a2ui-text-caption",
    label: "a2ui-text-label",
    code: "a2ui-text-code",
    subtitle: "a2ui-text-subtitle",
    overline: "a2ui-text-overline",
    quote: "a2ui-text-quote",
  },
  imageHints: {
    avatar: "a2ui-image-avatar",
    header: "a2ui-image-header",
    icon: "a2ui-image-icon",
    largeFeature: "a2ui-image-large",
    thumbnail: "a2ui-image-thumbnail",
    banner: "a2ui-image-banner",
    logo: "a2ui-image-logo",
    background: "a2ui-image-background",
  },
};

const VALID_COMPONENTS = new Set([
  "Text", "Card", "Image", "Icon", "Video", "AudioPlayer",
  "Row", "Column", "List", "Divider", "Tabs", "Modal",
  "Button", "Link",
  "TextField", "DateTimeInput", "ChoicePicker", "Slider", "CheckBox", "MultipleChoice",
  "Table", "Progress",
  "Accordion", "AccordionItem",
]);

class A2UISurface {
  constructor(surfaceId) {
    this.surfaceId = surfaceId;
    this.componentMap = {};
    this.dataModel = {};
    this.rootId = null;
    this.rendered = false;
  }

  processMessage(message) {
    if (message.surfaceUpdate) {
      this.handleSurfaceUpdate(message.surfaceUpdate);
    } else if (message.dataModelUpdate) {
      this.handleDataModelUpdate(message.dataModelUpdate);
    } else if (message.beginRendering) {
      this.handleBeginRendering(message.beginRendering);
    }
  }

  handleSurfaceUpdate(update) {
    const components = update.components || [];
    components.forEach((comp) => {
      if (comp.id && comp.component) {
        this.componentMap[comp.id] = comp.component;
      }
    });
  }

  handleDataModelUpdate(update) {
    const path = update.path || "";
    const contents = update.contents || [];

    if (!path) {
      this.dataModel = this.contentsToObject(contents);
    } else {
      const pathParts = path.replace(/^\//, "").split("/");
      let target = this.dataModel;

      for (let i = 0; i < pathParts.length - 1; i++) {
        const part = pathParts[i];
        if (!(part in target)) {
          target[part] = {};
        }
        target = target[part];
      }

      const lastPart = pathParts[pathParts.length - 1];
      if (lastPart) {
        target[lastPart] = this.contentsToObject(contents);
      } else {
        Object.assign(this.dataModel, this.contentsToObject(contents));
      }
    }
  }

  contentsToObject(contents) {
    const result = {};
    contents.forEach((item) => {
      const key = item.key;
      if ("valueString" in item) {
        result[key] = item.valueString;
      } else if ("valueNumber" in item) {
        result[key] = item.valueNumber;
      } else if ("valueBoolean" in item) {
        result[key] = item.valueBoolean;
      } else if ("valueMap" in item) {
        const nested = this.contentsToObject(item.valueMap);
        if (Object.keys(nested).every((k) => !isNaN(k))) {
          result[key] = Object.values(nested);
        } else {
          result[key] = nested;
        }
      }
    });
    return result;
  }

  handleBeginRendering(begin) {
    this.rootId = begin.root || "root";
    this.rendered = true;
  }

  render(container) {
    if (!this.rootId || !this.componentMap[this.rootId]) {
      console.warn("A2UI: Cannot render - no root component found");
      return;
    }

    container.innerHTML = "";
    const options = {
      componentMap: this.componentMap,
      dataModel: this.dataModel,
      surfaceId: this.surfaceId,
    };

    const element = renderComponent(this.componentMap[this.rootId], options);
    if (element) {
      container.appendChild(element);
    }
  }
}

export function processA2UIMessages(messages, container, options = {}) {
  const surfaceId = options.surfaceId || "main";
  const surface = new A2UISurface(surfaceId);

  messages.forEach((msg) => surface.processMessage(msg));

  if (surface.rendered) {
    surface.render(container);
  }

  return surface;
}

export function renderA2UIComponent(componentDef, container, options = {}) {
  if (!componentDef || typeof componentDef !== "object") {
    throw new Error("Invalid component definition");
  }
  container.innerHTML = "";

  if (Array.isArray(componentDef)) {
    const isMessageArray = componentDef.some(
      (item) => item.surfaceUpdate || item.dataModelUpdate || item.beginRendering
    );

    if (isMessageArray) {
      return processA2UIMessages(componentDef, container, options);
    }

    const componentMap = {};
    let rootId = null;

    componentDef.forEach((item) => {
      if (item.id && item.component) {
        componentMap[item.id] = item.component;
        if (item.id === "root" || !rootId) {
          rootId = item.id;
        }
      }
    });

    if (rootId && componentMap[rootId]) {
      options.componentMap = componentMap;
      options.dataModel = options.dataModel || {};
      const element = renderComponent(componentMap[rootId], options);
      if (element) {
        container.appendChild(element);
      }
    }
  } else {
    options.componentMap = options.componentMap || {};
    options.dataModel = options.dataModel || {};
    const element = renderComponent(componentDef, options);
    if (element) {
      container.appendChild(element);
    }
  }
}

function renderComponent(component, options = {}) {
  if (!component || typeof component !== "object") {
    return null;
  }

  const componentType = Object.keys(component).find((key) => VALID_COMPONENTS.has(key));

  if (!componentType) {
    console.warn("Unknown component type:", Object.keys(component));
    return null;
  }

  const props = component[componentType] || {};

  switch (componentType) {
    case "Text":
      return renderText(props, options);
    case "Card":
      return renderCard(props, options);
    case "Button":
      return renderButton(props, options);
    case "Image":
      return renderImage(props, options);
    case "Icon":
      return renderIcon(props, options);
    case "Row":
      return renderRow(props, options);
    case "Column":
      return renderColumn(props, options);
    case "List":
      return renderList(props, options);
    case "Divider":
      return renderDivider(props, options);
    case "Table":
      return renderTable(props, options);
    case "Progress":
      return renderProgress(props, options);
    case "Link":
      return renderLink(props, options);
    case "Video":
      return renderVideo(props, options);
    case "AudioPlayer":
      return renderAudioPlayer(props, options);
    case "TextField":
      return renderTextField(props, options);
    case "CheckBox":
      return renderCheckBox(props, options);
    case "Slider":
      return renderSlider(props, options);
    case "MultipleChoice":
      return renderMultipleChoice(props, options);
    case "Tabs":
      return renderTabs(props, options);
    case "Modal":
      return renderModal(props, options);
    default:
      console.warn("Unhandled component type:", componentType);
      return null;
  }
}

function renderText(props, options) {
  const hint = props.usageHint || "body";
  const text = extractString(props.text, options);

  let tagName = "p";
  if (hint.startsWith("h") && hint.length === 2 && !isNaN(hint[1])) {
    tagName = hint;
  } else if (hint === "code") {
    tagName = "code";
  } else if (hint === "caption" || hint === "label" || hint === "overline") {
    tagName = "span";
  } else if (hint === "quote") {
    tagName = "blockquote";
  }

  const el = document.createElement(tagName);
  el.className = `a2ui-text ${THEME.textHints[hint] || "a2ui-text-body"}`;
  el.textContent = text;

  return el;
}

function renderCard(props, options) {
  const card = document.createElement("div");
  card.className = "a2ui-card";

  if (props.title) {
    const title = document.createElement("div");
    title.className = "a2ui-card-title";
    title.textContent = extractString(props.title, options);
    card.appendChild(title);
  }

  const content = document.createElement("div");
  content.className = "a2ui-card-content";

  if (props.child) {
    const childEl = renderChildById(props.child, options);
    if (childEl) content.appendChild(childEl);
  } else if (props.children) {
    renderChildren(props.children, content, options);
  }

  card.appendChild(content);

  return card;
}

function renderButton(props, options) {
  const btn = document.createElement("button");
  btn.className = "a2ui-button";

  if (props.primary) {
    btn.classList.add("a2ui-button-primary");
  } else {
    btn.classList.add("a2ui-button-secondary");
  }

  if (props.child) {
    const childEl = renderChildById(props.child, options);
    if (childEl) btn.appendChild(childEl);
  } else if (props.label) {
    btn.textContent = extractString(props.label, options);
  }

  if (props.disabled) {
    btn.disabled = true;
  }

  const action = props.action;
  if (action) {
    btn.dataset.actionName = action.name || "";
    btn.addEventListener("click", () => {
      const actionContext = resolveActionContext(action.context, options);
      document.dispatchEvent(
        new CustomEvent("a2ui:action", {
          detail: {
            actionId: action.name,
            surfaceId: options.surfaceId || "main",
            context: actionContext,
          },
        })
      );
    });
  }

  return btn;
}

function resolveActionContext(contextDef, options) {
  if (!contextDef || !Array.isArray(contextDef)) return {};

  const result = {};
  contextDef.forEach((item) => {
    if (item.key && item.value) {
      if (item.value.path) {
        result[item.key] = resolveDataPath(item.value.path, options.dataModel || {});
      } else if (item.value.literalString) {
        result[item.key] = item.value.literalString;
      } else if (item.value.literalNumber !== undefined) {
        result[item.key] = item.value.literalNumber;
      } else if (item.value.literalBoolean !== undefined) {
        result[item.key] = item.value.literalBoolean;
      }
    }
  });
  return result;
}

function renderImage(props, options) {
  const img = document.createElement("img");
  img.className = "a2ui-image";

  const hint = props.usageHint || "thumbnail";
  img.classList.add(THEME.imageHints[hint] || "a2ui-image-thumbnail");

  if (props.url) {
    img.src = extractString(props.url, options);
  } else if (props.base64) {
    const mimeType = props.mimeType || "image/png";
    img.src = `data:${mimeType};base64,${props.base64}`;
  }

  img.alt = extractString(props.altText, options) || "Image";

  if (props.fit) {
    img.style.objectFit = props.fit;
  }

  return img;
}

function renderIcon(props, options) {
  const span = document.createElement("span");
  span.className = "a2ui-icon material-symbols-outlined";
  span.textContent = extractString(props.name, options) || "help";
  return span;
}

function renderRow(props, options) {
  const row = document.createElement("div");
  row.className = "a2ui-row";
  applyLayoutHints(row, props);
  renderChildren(props.children, row, options);
  return row;
}

function renderColumn(props, options) {
  const col = document.createElement("div");
  col.className = "a2ui-column";
  applyLayoutHints(col, props);
  renderChildren(props.children, col, options);
  return col;
}

function applyLayoutHints(element, props) {
  if (props.gap) {
    element.classList.add(`a2ui-gap-${props.gap}`);
  }
  if (props.alignment) {
    element.classList.add(`a2ui-align-${props.alignment}`);
  }
  if (props.distribution) {
    element.classList.add(`a2ui-distribute-${props.distribution}`);
  }
}

function renderList(props, options) {
  const list = document.createElement("div");
  list.className = "a2ui-list";

  if (props.direction === "horizontal") {
    list.classList.add("a2ui-list-horizontal");
  }

  if (props.alignment) {
    list.classList.add(`a2ui-align-${props.alignment}`);
  }

  renderChildren(props.children, list, options);

  return list;
}

function renderDivider(props, options) {
  const hr = document.createElement("hr");
  hr.className = "a2ui-divider";
  if (props.axis === "vertical") {
    hr.classList.add("a2ui-divider-vertical");
  }
  return hr;
}

function renderTable(props, options) {
  const wrapper = document.createElement("div");
  wrapper.className = "a2ui-table-wrapper";

  const table = document.createElement("table");
  table.className = "a2ui-table";

  let headers = props.headers;
  if (headers && !Array.isArray(headers)) {
    if (typeof headers === "string") {
      headers = headers.split(",").map((h) => h.trim());
    } else {
      headers = [String(headers)];
    }
  }

  if (headers && Array.isArray(headers)) {
    const thead = document.createElement("thead");
    const headerRow = document.createElement("tr");
    headers.forEach((header) => {
      const th = document.createElement("th");
      th.textContent = extractString(header, options);
      headerRow.appendChild(th);
    });
    thead.appendChild(headerRow);
    table.appendChild(thead);
  }

  let rows = props.rows;
  if (rows && !Array.isArray(rows)) {
    if (typeof rows === "string") {
      rows = rows.split("\n").filter((r) => r.trim()).map((r) => r.split(",").map((c) => c.trim()));
    } else if (typeof rows === "object") {
      rows = Object.entries(rows).map(([k, v]) => [k, String(v)]);
    } else {
      rows = [[String(rows)]];
    }
  }

  if (rows && Array.isArray(rows)) {
    const tbody = document.createElement("tbody");
    rows.forEach((row) => {
      const tr = document.createElement("tr");
      let cells = row;
      if (!Array.isArray(cells)) {
        if (typeof cells === "string") {
          cells = cells.split(",").map((c) => c.trim());
        } else if (typeof cells === "object" && cells !== null) {
          cells = Object.values(cells).map((v) => String(v));
        } else {
          cells = [String(cells)];
        }
      }
      cells.forEach((cell) => {
        const td = document.createElement("td");
        td.textContent = extractString(cell, options);
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
  }

  wrapper.appendChild(table);
  return wrapper;
}

function renderProgress(props, options) {
  const container = document.createElement("div");
  container.className = "a2ui-progress";

  const value = props.value ?? 0;
  const max = props.max ?? 100;
  const percent = Math.min(100, Math.max(0, (value / max) * 100));

  if (props.label) {
    const label = document.createElement("div");
    label.className = "a2ui-progress-label";
    label.textContent = extractString(props.label, options);
    container.appendChild(label);
  }

  const barContainer = document.createElement("div");
  barContainer.className = "a2ui-progress-bar-container";

  const bar = document.createElement("div");
  bar.className = "a2ui-progress-bar";

  const fill = document.createElement("div");
  fill.className = "a2ui-progress-fill";
  fill.style.width = `${percent}%`;

  bar.appendChild(fill);
  barContainer.appendChild(bar);

  const percentText = document.createElement("span");
  percentText.className = "a2ui-progress-percent";
  percentText.textContent = `${Math.round(percent)}%`;
  barContainer.appendChild(percentText);

  container.appendChild(barContainer);

  return container;
}

function renderLink(props, options) {
  const a = document.createElement("a");
  a.className = "a2ui-link";
  a.textContent = extractString(props.text || props.label, options);
  a.href = extractString(props.url, options) || "#";
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  return a;
}

function renderVideo(props, options) {
  const video = document.createElement("video");
  video.className = "a2ui-video";
  video.controls = true;

  if (props.url) {
    video.src = extractString(props.url, options);
  }

  if (props.poster) {
    video.poster = extractString(props.poster, options);
  }

  return video;
}

function renderAudioPlayer(props, options) {
  const container = document.createElement("div");
  container.className = "a2ui-audio-player";

  if (props.description) {
    const desc = document.createElement("div");
    desc.className = "a2ui-audio-description";
    desc.textContent = extractString(props.description, options);
    container.appendChild(desc);
  }

  const audio = document.createElement("audio");
  audio.controls = true;
  if (props.url) {
    audio.src = extractString(props.url, options);
  }
  container.appendChild(audio);

  return container;
}

function renderTextField(props, options) {
  const container = document.createElement("div");
  container.className = "a2ui-textfield";

  if (props.label) {
    const label = document.createElement("label");
    label.className = "a2ui-textfield-label";
    label.textContent = extractString(props.label, options);
    container.appendChild(label);
  }

  const isLongText = props.textFieldType === "longText";

  const input = isLongText
    ? document.createElement("textarea")
    : document.createElement("input");

  input.className = "a2ui-textfield-input";

  if (!isLongText) {
    const typeMap = {
      shortText: "text",
      number: "number",
      obscured: "password",
      date: "date",
    };
    input.type = typeMap[props.textFieldType] || "text";
  }

  input.placeholder = extractString(props.placeholder, options) || "";
  input.value = extractString(props.text || props.value, options) || "";

  if (props.validationRegexp) {
    input.pattern = props.validationRegexp;
  }

  if (props.disabled) {
    input.disabled = true;
  }

  if (props.text?.path) {
    input.dataset.bindPath = props.text.path;
    input.addEventListener("input", (e) => {
      store.updateDataModel(props.text.path, e.target.value);
    });
  }

  container.appendChild(input);
  return container;
}

function renderCheckBox(props, options) {
  const container = document.createElement("label");
  container.className = "a2ui-checkbox";

  const input = document.createElement("input");
  input.type = "checkbox";
  input.className = "a2ui-checkbox-input";

  if (props.value?.path) {
    input.checked = !!resolveDataPath(props.value.path, options.dataModel || {});
    input.dataset.bindPath = props.value.path;
    input.addEventListener("change", (e) => {
      store.updateDataModel(props.value.path, e.target.checked);
    });
  } else {
    input.checked = !!props.checked;
  }

  if (props.disabled) {
    input.disabled = true;
  }

  const text = document.createElement("span");
  text.className = "a2ui-checkbox-label";
  text.textContent = extractString(props.label, options) || "";

  container.appendChild(input);
  container.appendChild(text);
  return container;
}

function renderSlider(props, options) {
  const container = document.createElement("div");
  container.className = "a2ui-slider";

  if (props.label) {
    const label = document.createElement("label");
    label.className = "a2ui-slider-label";
    label.textContent = extractString(props.label, options);
    container.appendChild(label);
  }

  const input = document.createElement("input");
  input.type = "range";
  input.className = "a2ui-slider-input";
  input.min = props.minValue ?? props.min ?? 0;
  input.max = props.maxValue ?? props.max ?? 100;
  input.step = props.step ?? 1;

  if (props.value?.path) {
    input.value = resolveDataPath(props.value.path, options.dataModel || {}) || 50;
    input.dataset.bindPath = props.value.path;
    input.addEventListener("input", (e) => {
      store.updateDataModel(props.value.path, parseFloat(e.target.value));
    });
  } else {
    input.value = props.value ?? 50;
  }

  if (props.disabled) {
    input.disabled = true;
  }

  container.appendChild(input);
  return container;
}

function renderMultipleChoice(props, options) {
  const container = document.createElement("div");
  container.className = "a2ui-multiple-choice";

  const maxSelections = props.maxAllowedSelections || Infinity;
  const isSingle = maxSelections === 1;

  const inputType = isSingle ? "radio" : "checkbox";
  const groupName = `mc-${Math.random().toString(36).substr(2, 9)}`;

  (props.options || []).forEach((opt, idx) => {
    const optContainer = document.createElement("label");
    optContainer.className = "a2ui-choice-option";

    const input = document.createElement("input");
    input.type = inputType;
    input.name = groupName;
    input.value = opt.id || idx;

    const label = document.createElement("span");
    label.textContent = extractString(opt.label || opt.text, options);

    optContainer.appendChild(input);
    optContainer.appendChild(label);
    container.appendChild(optContainer);
  });

  return container;
}

function renderTabs(props, options) {
  const container = document.createElement("div");
  container.className = "a2ui-tabs";

  const tabsBar = document.createElement("div");
  tabsBar.className = "a2ui-tabs-bar";

  const tabContents = document.createElement("div");
  tabContents.className = "a2ui-tabs-content";

  (props.tabItems || []).forEach((item, idx) => {
    const tabBtn = document.createElement("button");
    tabBtn.className = "a2ui-tab-button";
    tabBtn.textContent = extractString(item.title, options);
    if (idx === 0) tabBtn.classList.add("a2ui-tab-active");

    const tabContent = document.createElement("div");
    tabContent.className = "a2ui-tab-panel";
    if (idx === 0) tabContent.classList.add("a2ui-tab-panel-active");

    if (item.child) {
      const childEl = renderChildById(item.child, options);
      if (childEl) tabContent.appendChild(childEl);
    }

    tabBtn.addEventListener("click", () => {
      container.querySelectorAll(".a2ui-tab-button").forEach((b) => b.classList.remove("a2ui-tab-active"));
      container.querySelectorAll(".a2ui-tab-panel").forEach((p) => p.classList.remove("a2ui-tab-panel-active"));
      tabBtn.classList.add("a2ui-tab-active");
      tabContent.classList.add("a2ui-tab-panel-active");
    });

    tabsBar.appendChild(tabBtn);
    tabContents.appendChild(tabContent);
  });

  container.appendChild(tabsBar);
  container.appendChild(tabContents);

  return container;
}

function renderModal(props, options) {
  const container = document.createElement("div");
  container.className = "a2ui-modal-container";

  if (props.entryPointChild) {
    const trigger = renderChildById(props.entryPointChild, options);
    if (trigger) {
      trigger.addEventListener("click", () => {
        modal.classList.add("a2ui-modal-open");
      });
      container.appendChild(trigger);
    }
  }

  const modal = document.createElement("div");
  modal.className = "a2ui-modal";

  const overlay = document.createElement("div");
  overlay.className = "a2ui-modal-overlay";
  overlay.addEventListener("click", () => {
    modal.classList.remove("a2ui-modal-open");
  });

  const content = document.createElement("div");
  content.className = "a2ui-modal-content";

  if (props.contentChild) {
    const contentEl = renderChildById(props.contentChild, options);
    if (contentEl) content.appendChild(contentEl);
  }

  modal.appendChild(overlay);
  modal.appendChild(content);
  container.appendChild(modal);

  return container;
}

function renderChildren(children, container, options) {
  if (!children) return;

  if (Array.isArray(children)) {
    children.forEach((child) => {
      const el = renderComponent(child, options);
      if (el) container.appendChild(el);
    });
  } else if (typeof children === "object") {
    if (children.explicitList && Array.isArray(children.explicitList)) {
      const componentMap = options.componentMap || {};
      children.explicitList.forEach((childId) => {
        const childComponent = componentMap[childId];
        if (childComponent) {
          const el = renderComponent(childComponent, options);
          if (el) container.appendChild(el);
        }
      });
    } else if (children.template) {
      renderDynamicChildren(children.template, container, options);
    } else {
      const el = renderComponent(children, options);
      if (el) container.appendChild(el);
    }
  }
}

function renderDynamicChildren(template, container, options) {
  const dataPath = template.dataBinding;
  const templateId = template.componentId;

  if (!dataPath || !templateId) return;

  const dataList = resolveDataPath(dataPath, options.dataModel || {});
  if (!Array.isArray(dataList)) return;

  const templateComponent = options.componentMap?.[templateId];
  if (!templateComponent) return;

  dataList.forEach((itemData, idx) => {
    const scopedOptions = {
      ...options,
      dataModel: itemData,
      parentPath: dataPath + "/" + idx,
    };
    const el = renderComponent(templateComponent, scopedOptions);
    if (el) container.appendChild(el);
  });
}

function renderChildById(childId, options) {
  const componentMap = options.componentMap || {};
  const childComponent = componentMap[childId];
  if (childComponent) {
    return renderComponent(childComponent, options);
  }
  return null;
}

function extractString(value, options = {}) {
  if (!value) return "";
  if (typeof value === "string") return value;
  if (typeof value === "object") {
    if (value.literalString) return value.literalString;
    if (value.literalNumber !== undefined) return String(value.literalNumber);
    if (value.path) {
      return resolveDataPath(value.path, options.dataModel || {});
    }
    if (value.dataBinding) return `{{ ${value.dataBinding} }}`;
  }
  return String(value);
}

function resolveDataPath(path, dataModel) {
  if (!path || !dataModel) return "";

  const parts = path.replace(/^\//, "").split("/");
  let current = dataModel;

  for (const part of parts) {
    if (current === null || current === undefined) {
      return "";
    }
    if (Array.isArray(current) && !isNaN(part)) {
      current = current[parseInt(part, 10)];
    } else if (typeof current === "object") {
      current = current[part];
    } else {
      return "";
    }
  }

  return current !== null && current !== undefined ? String(current) : "";
}

const a2uiModel = {
  surfaces: {},
  actionHandlers: {},
  dataModel: {},

  init() {
    document.addEventListener("a2ui:action", (e) => {
      const { actionId, surfaceId, context } = e.detail;
      this.handleAction(actionId, surfaceId, context);
    });
  },

  setDataModel(surfaceId, data) {
    this.dataModel[surfaceId] = data || {};
  },

  updateDataModel(path, value) {
    const parts = path.replace(/^\//, "").split("/");
    let surfaceId = "main";
    let current = this.dataModel[surfaceId] || {};
    this.dataModel[surfaceId] = current;

    for (let i = 0; i < parts.length - 1; i++) {
      const part = parts[i];
      if (!(part in current)) {
        current[part] = {};
      }
      current = current[part];
    }

    current[parts[parts.length - 1]] = value;
  },

  registerActionHandler(actionId, handler) {
    this.actionHandlers[actionId] = handler;
  },

  async handleAction(actionId, surfaceId, context = {}) {
    const handler = this.actionHandlers[actionId];
    if (handler) {
      handler(surfaceId, context);
      return;
    }

    try {
      const ctxid = window.currentContext?.id || "";

      const result = await callJsonApi("/a2ui_action", {
        actionId,
        surfaceId,
        context,
        ctxid,
      });

      console.log("A2UI action sent:", actionId, "->", result.status);
    } catch (err) {
      console.error("A2UI action error:", err);
    }
  },
};

export const store = createStore("a2ui", a2uiModel);
