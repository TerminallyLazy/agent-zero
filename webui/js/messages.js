// messages.js

// ───────────────
// 1. import / copy‐button setup
// ───────────────
import { openImageModal } from "./image_modal.js";

// Make openImageModal available globally for onclick handlers
window.openImageModal = openImageModal;

function createCopyButton() {
  const button = document.createElement("button");
  button.className = "copy-button";
  button.textContent = "Copy";

  button.addEventListener("click", async function (e) {
    e.stopPropagation();
    const container = this.closest(".msg-content, .kvps-row, .message-text");
    let textToCopy;

    if (container.classList.contains("kvps-row")) {
      textToCopy = container.querySelector(".kvps-val").textContent;
    } else {
      // both .message-text and the default case use a <span>
      textToCopy = container.querySelector("span").textContent;
    }

    try {
      await navigator.clipboard.writeText(textToCopy);
      const originalText = button.textContent;
      button.classList.add("copied");
      button.textContent = "Copied!";
      setTimeout(() => {
        button.classList.remove("copied");
        button.textContent = originalText;
      }, 2000);
    } catch (err) {
      console.error("Failed to copy text:", err);
    }
  });

  return button;
}

function addCopyButtonToElement(element) {
  if (!element.querySelector(".copy-button")) {
    element.appendChild(createCopyButton());
  }
}


// ───────────────
// 2. Handler‐selector
// ───────────────
export function getHandler(type) {
  switch (type) {
    case "user":
      return drawMessageUser;
    case "agent":
      return drawMessageAgent;
    case "response":
      return drawMessageResponse;
    case "tool":
      return drawMessageTool;
    case "code_exe":
      return drawMessageCodeExe;
    case "browser":
      return drawMessageBrowser;
    case "warning":
    case "rate_limit":
      return drawMessageWarning;
    case "error":
      return drawMessageError;
    case "info":
      return drawMessageInfo;
    case "util":
      return drawMessageUtil;
    case "hint":
      return drawMessageInfo;
    default:
      return drawMessageDefault;
  }
}


// ────────────────────────────────────────────────────────────────────────────
// 3. Core renderer: _drawMessage(...)  (all other drawMessage… functions delegate to this)
// ────────────────────────────────────────────────────────────────────────────
export function _drawMessage(
  messageContainer,
  heading,
  content,
  temp,
  followUp,
  kvps = null,
  messageClasses = [],
  contentClasses = [],
  latex = false
) {
  // Create the outer wrapper
  const messageDiv = document.createElement("div");
  messageDiv.classList.add("message", ...messageClasses);

  // If there is a heading (e.g. “User message”), render it
  if (heading) {
    const headingElement = document.createElement("h4");
    headingElement.textContent = heading;
    messageDiv.appendChild(headingElement);
  }

  // 3.a. Render any key‐value pairs / attachments
  drawKvps(messageDiv, kvps, latex);

  // 3.b. Render the main content (either a <pre><span>…</span></pre> or a <div>…</div> if media is detected)
  if (content && content.trim().length > 0) {
    // Detect any media tags (<img>, <video>, <audio>, <iframe>, or <image>…</image>)
    const mediaTagRegex = /<(img|video|audio|iframe|image)[^>]*>/i;
    let contentElement;

    if (mediaTagRegex.test(content)) {
      // Wrap media‐rich content in a <div>
      contentElement = document.createElement("div");
      contentElement.classList.add("msg-content", ...contentClasses);
      contentElement.style.whiteSpace = "normal";
      contentElement.style.wordBreak = "break-word";
      contentElement.innerHTML = convertHTML(content);
    } else {
      // Otherwise render as <pre><span>…</span></pre>
      contentElement = document.createElement("pre");
      contentElement.classList.add("msg-content", ...contentClasses);
      contentElement.style.whiteSpace = "pre-wrap";
      contentElement.style.wordBreak = "break-word";

      const spanElement = document.createElement("span");
      spanElement.innerHTML = convertHTML(content);
      // On small screens, clicking the text itself should copy it
      spanElement.addEventListener("click", () => {
        copyText(spanElement.textContent, spanElement);
      });

      contentElement.appendChild(spanElement);
    }

    // Put a copy‐button on whatever container we used
    addCopyButtonToElement(contentElement);
    messageDiv.appendChild(contentElement);

    // If LaTeX rendering is desired, render after insertion
    if (
      window.renderMathInElement &&
      latex &&
      contentElement.querySelector("span")
    ) {
      renderMathInElement(contentElement.querySelector("span"), {
        delimiters: [{ left: "$", right: "$", display: true }],
        throwOnError: false,
      });
    }
  }

  // 3.c. If this is a “followUp” style message, add that class
  if (followUp) {
    messageContainer.classList.add("message-followup");
  }

  // 3.d. Finally append into the provided container
  messageContainer.appendChild(messageDiv);
  return messageDiv;
}


// ────────────────────────────────────────────────────────────────────────────
// 4. “Simple” drawMessage… wrappers
//    These exist mainly to choose classes, followUp flags, and latex‐on/off.
// ────────────────────────────────────────────────────────────────────────────
export function drawMessageDefault(
  messageContainer,
  id,
  type,
  heading,
  content,
  temp,
  kvps = null
) {
  _drawMessage(
    messageContainer,
    heading,
    content,
    temp,
    false,           // followUp = false
    kvps,
    ["message-ai", "message-default"],
    ["msg-json"],
    false            // latex = false
  );
}

export function drawMessageAgent(
  messageContainer,
  id,
  type,
  heading,
  content,
  temp,
  kvps = null
) {
  let kvpsFlat = null;
  if (kvps) {
    kvpsFlat = { ...kvps, ...(kvps["tool_args"] || {}) };
    delete kvpsFlat["tool_args"];
  }

  _drawMessage(
    messageContainer,
    heading,
    content,
    temp,
    false,           // followUp = false
    kvpsFlat,
    ["message-ai", "message-agent"],
    ["msg-json"],
    true             // latex = true for “agent”
  );
}

export function drawMessageResponse(
  messageContainer,
  id,
  type,
  heading,
  content,
  temp,
  kvps = null
) {
  _drawMessage(
    messageContainer,
    heading,
    content,
    temp,
    true,            // followUp = true
    null,
    ["message-ai", "message-agent-response"],
    [],
    true             // latex = true
  );
}

export function drawMessageDelegation(
  messageContainer,
  id,
  type,
  heading,
  content,
  temp,
  kvps = null
) {
  _drawMessage(
    messageContainer,
    heading,
    content,
    temp,
    true,            // followUp = true
    kvps,
    ["message-ai", "message-agent", "message-agent-delegation"],
    [],
    true             // latex = true
  );
}

export function drawMessageUser(
  messageContainer,
  id,
  type,
  heading,
  content,
  temp,
  kvps = null,
  latex = false    // default user messages do not need LaTeX
) {
  const messageDiv = document.createElement("div");
  messageDiv.classList.add("message", "message-user");

  // Always label user messages
  const headingElement = document.createElement("h4");
  headingElement.textContent = "User message";
  messageDiv.appendChild(headingElement);

  if (content && content.trim().length > 0) {
    const textDiv = document.createElement("div");
    textDiv.classList.add("message-text");

    // Put the user’s text inside a <span>
    const spanElement = document.createElement("span");
    spanElement.innerHTML = convertHTML(content);
    textDiv.appendChild(spanElement);

    // Clicking the text itself also copies
    textDiv.addEventListener("click", () => {
      copyText(content, textDiv);
    });

    // Always add the copy button
    addCopyButtonToElement(textDiv);
    messageDiv.appendChild(textDiv);
  }

  // Handle any attachments (images, files, etc.)
  if (kvps && kvps.attachments && kvps.attachments.length > 0) {
    const attachmentsContainer = document.createElement("div");
    attachmentsContainer.classList.add("attachments-container");

    kvps.attachments.forEach((attachment) => {
      const attachmentDiv = document.createElement("div");
      attachmentDiv.classList.add("attachment-item");

      if (typeof attachment === "string") {
        // Plain filename (no rich metadata)
        const filename = attachment;
        const extension = filename.split(".").pop().toLowerCase();
        attachmentDiv.classList.add("file-type");
        attachmentDiv.innerHTML = `
          <div class="file-preview">
            <span class="filename">${filename}</span>
            <span class="extension">${extension.toUpperCase()}</span>
          </div>
        `;
      } else {
        // Any “object” attachment gets rendered via helper
        renderMediaAttachment(attachment, attachmentDiv);
      }

      attachmentsContainer.appendChild(attachmentDiv);
    });

    messageDiv.appendChild(attachmentsContainer);
  }

  messageContainer.appendChild(messageDiv);
}

export function drawMessageTool(
  messageContainer,
  id,
  type,
  heading,
  content,
  temp,
  kvps = null
) {
  _drawMessage(
    messageContainer,
    heading,
    content,
    temp,
    true,             // followUp = true
    kvps,
    ["message-ai", "message-tool"],
    ["msg-output"],
    false             // latex = false
  );
}

export function drawMessageCodeExe(
  messageContainer,
  id,
  type,
  heading,
  content,
  temp,
  kvps = null
) {
  _drawMessage(
    messageContainer,
    heading,
    content,
    temp,
    true,             // followUp = true
    null,
    ["message-ai", "message-code-exe"],
    [],
    false             // latex = false
  );
}

export function drawMessageBrowser(
  messageContainer,
  id,
  type,
  heading,
  content,
  temp,
  kvps = null
) {
  _drawMessage(
    messageContainer,
    heading,
    content,
    temp,
    true,             // followUp = true
    kvps,
    ["message-ai", "message-browser"],
    ["msg-json"],
    false             // latex = false
  );
}

export function drawMessageAgentPlain(
  classes,
  messageContainer,
  id,
  type,
  heading,
  content,
  temp,
  kvps = null
) {
  _drawMessage(
    messageContainer,
    heading,
    content,
    temp,
    false,
    kvps,
    [...classes],
    [],
    false
  );
  messageContainer.classList.add("center-container");
}

export function drawMessageInfo(
  messageContainer,
  id,
  type,
  heading,
  content,
  temp,
  kvps = null
) {
  return drawMessageAgentPlain(
    ["message-info"],
    messageContainer,
    id,
    type,
    heading,
    content,
    temp,
    kvps
  );
}

export function drawMessageUtil(
  messageContainer,
  id,
  type,
  heading,
  content,
  temp,
  kvps = null
) {
  _drawMessage(
    messageContainer,
    heading,
    content,
    temp,
    false,
    kvps,
    ["message-util"],
    ["msg-json"],
    false
  );
  messageContainer.classList.add("center-container");
}

export function drawMessageWarning(
  messageContainer,
  id,
  type,
  heading,
  content,
  temp,
  kvps = null
) {
  return drawMessageAgentPlain(
    ["message-warning"],
    messageContainer,
    id,
    type,
    heading,
    content,
    temp,
    kvps
  );
}

export function drawMessageError(
  messageContainer,
  id,
  type,
  heading,
  content,
  temp,
  kvps = null
) {
  return drawMessageAgentPlain(
    ["message-error"],
    messageContainer,
    id,
    type,
    heading,
    content,
    temp,
    kvps
  );
}


// ────────────────────────────────────────────────────────────────────────────
// 5. “Enhanced KVP” renderer (images, videos, audio, iframe, PDF, or plain text)
// ────────────────────────────────────────────────────────────────────────────
function drawKvps(container, kvps, latex) {
  if (!kvps) return;

  const table = document.createElement("table");
  table.classList.add("msg-kvps");

  for (let [key, value] of Object.entries(kvps)) {
    const row = table.insertRow();
    row.classList.add("kvps-row");
    if (key === "thoughts" || key === "reflection") {
      row.classList.add("msg-thoughts");
    }

    const th = row.insertCell();
    th.textContent = convertToTitleCase(key);
    th.classList.add("kvps-key");

    const td = row.insertCell();

    // If the value is an array, render each entry
    if (Array.isArray(value)) {
      for (const item of value) {
        addValue(item);
      }
    } else {
      addValue(value);
    }

    function addValue(val) {
      // If it's an object, stringify it
      if (typeof val === "object") {
        val = JSON.stringify(val, null, 2);
      }

      if (typeof val === "string") {
        if (val.startsWith("img://")) {
          renderKvpImage(val, td);
        } else if (val.startsWith("video://")) {
          renderKvpVideo(val, td);
        } else if (val.startsWith("audio://")) {
          renderKvpAudio(val, td);
        } else if (val.startsWith("iframe://") || val.startsWith("embed://")) {
          renderKvpIframe(val, td);
        } else if (val.startsWith("pdf://")) {
          renderKvpPdf(val, td);
        } else {
          renderKvpText(val, td, row, latex);
        }
      } else {
        // Non‐string (number, boolean), just render as text
        renderKvpText(val, td, row, latex);
      }
    }
  }

  container.appendChild(table);
}

function renderKvpImage(value, td) {
  const imgElement = document.createElement("img");
  imgElement.classList.add("kvps-img");
  imgElement.src = value.replace("img://", "/image_get?path=");
  imgElement.alt = "Image Attachment";
  imgElement.style.cursor = "pointer";
  imgElement.addEventListener("click", () => {
    openImageModal(imgElement.src, 1000);
  });
  td.appendChild(imgElement);
}

function renderKvpVideo(value, td) {
  const videoElement = document.createElement("video");
  videoElement.classList.add("kvps-video");
  videoElement.src = value.replace("video://", "/media_get?path=");
  videoElement.controls = true;
  videoElement.style.maxWidth = "100%";
  videoElement.style.height = "auto";
  td.appendChild(videoElement);
}

function renderKvpAudio(value, td) {
  const audioElement = document.createElement("audio");
  audioElement.classList.add("kvps-audio");
  audioElement.src = value.replace("audio://", "/media_get?path=");
  audioElement.controls = true;
  audioElement.style.width = "100%";
  td.appendChild(audioElement);
}

function renderKvpIframe(value, td) {
  const iframeElement = document.createElement("iframe");
  iframeElement.classList.add("kvps-iframe");
  iframeElement.src = value.replace(/^(iframe|embed):\/\//, "");
  iframeElement.style.width = "100%";
  iframeElement.style.height = "300px";
  iframeElement.style.border = "1px solid #ccc";
  iframeElement.style.borderRadius = "4px";
  iframeElement.setAttribute("sandbox", "allow-scripts allow-same-origin allow-forms");
  iframeElement.setAttribute("loading", "lazy");
  td.appendChild(iframeElement);
}

function renderKvpPdf(value, td) {
  const pdfElement = document.createElement("iframe");
  pdfElement.classList.add("kvps-pdf");
  pdfElement.src = value.replace("pdf://", "/pdf_get?path=");
  pdfElement.style.width = "100%";
  pdfElement.style.height = "400px";
  pdfElement.style.border = "1px solid #ccc";
  pdfElement.style.borderRadius = "4px";
  td.appendChild(pdfElement);
}

function renderKvpText(value, td, row, latex) {
  const pre = document.createElement("pre");
  pre.classList.add("kvps-val");
  const span = document.createElement("span");
  span.innerHTML = convertHTML(value);
  pre.appendChild(span);
  td.appendChild(pre);
  addCopyButtonToElement(row);

  span.addEventListener("click", () => {
    copyText(span.textContent, span);
  });

  if (window.renderMathInElement && latex) {
    renderMathInElement(span, {
      delimiters: [{ left: "$", right: "$", display: true }],
      throwOnError: false,
    });
  }
}


// ────────────────────────────────────────────────────────────────────────────
// 6. “Render any single attachment object” for drawMessageUser
// ────────────────────────────────────────────────────────────────────────────
function renderMediaAttachment(attachment, container) {
  const { type, url, name, extension } = attachment;

  switch (type) {
    case "image":
      renderImageAttachment(attachment, container);
      break;
    case "video":
      renderVideoAttachment(attachment, container);
      break;
    case "audio":
      renderAudioAttachment(attachment, container);
      break;
    case "iframe":
    case "embed":
      renderIframeAttachment(attachment, container);
      break;
    case "pdf":
      renderPdfAttachment(attachment, container);
      break;
    default:
      renderFileAttachment(attachment, container);
  }
}

function renderImageAttachment(attachment, container) {
  const imgWrapper = document.createElement("div");
  imgWrapper.classList.add("image-wrapper");

  const img = document.createElement("img");
  img.src = attachment.url;
  img.alt = attachment.name;
  img.classList.add("attachment-preview");
  img.style.cursor = "pointer";
  img.addEventListener("click", () => {
    openImageModal(attachment.url, 1000);
  });

  const fileInfo = document.createElement("div");
  fileInfo.classList.add("file-info");
  fileInfo.innerHTML = `
    <span class="filename">${attachment.name}</span>
    <span class="extension">${attachment.extension.toUpperCase()}</span>
  `;

  imgWrapper.appendChild(img);
  container.appendChild(imgWrapper);
  container.appendChild(fileInfo);
}

function renderVideoAttachment(attachment, container) {
  const videoWrapper = document.createElement("div");
  videoWrapper.classList.add("video-wrapper");

  const video = document.createElement("video");
  video.src = attachment.url;
  video.controls = true;
  video.classList.add("attachment-preview", "video-preview");
  video.style.maxWidth = "100%";
  video.style.height = "auto";

  const fileInfo = document.createElement("div");
  fileInfo.classList.add("file-info");
  fileInfo.innerHTML = `
    <span class="filename">${attachment.name}</span>
    <span class="extension">${attachment.extension.toUpperCase()}</span>
  `;

  videoWrapper.appendChild(video);
  container.appendChild(videoWrapper);
  container.appendChild(fileInfo);
}

function renderAudioAttachment(attachment, container) {
  const audioWrapper = document.createElement("div");
  audioWrapper.classList.add("audio-wrapper");

  const audio = document.createElement("audio");
  audio.src = attachment.url;
  audio.controls = true;
  audio.classList.add("attachment-preview", "audio-preview");
  audio.style.width = "100%";

  const fileInfo = document.createElement("div");
  fileInfo.classList.add("file-info");
  fileInfo.innerHTML = `
    <span class="filename">${attachment.name}</span>
    <span class="extension">${attachment.extension.toUpperCase()}</span>
  `;

  audioWrapper.appendChild(audio);
  container.appendChild(audioWrapper);
  container.appendChild(fileInfo);
}

function renderIframeAttachment(attachment, container) {
  const iframeWrapper = document.createElement("div");
  iframeWrapper.classList.add("iframe-wrapper");

  const iframe = document.createElement("iframe");
  iframe.src = attachment.url;
  iframe.classList.add("attachment-preview", "iframe-preview");
  iframe.style.width = "100%";
  iframe.style.height = "400px";
  iframe.style.border = "1px solid #ccc";
  iframe.style.borderRadius = "4px";
  iframe.setAttribute("sandbox", "allow-scripts allow-same-origin allow-forms");
  iframe.setAttribute("loading", "lazy");

  const fileInfo = document.createElement("div");
  fileInfo.classList.add("file-info");
  fileInfo.innerHTML = `
    <span class="filename">${attachment.name}</span>
    <span class="extension">EMBED</span>
  `;

  iframeWrapper.appendChild(iframe);
  container.appendChild(iframeWrapper);
  container.appendChild(fileInfo);
}

function renderPdfAttachment(attachment, container) {
  const pdfWrapper = document.createElement("div");
  pdfWrapper.classList.add("pdf-wrapper");

  const iframe = document.createElement("iframe");
  iframe.src = attachment.url;
  iframe.classList.add("attachment-preview", "pdf-preview");
  iframe.style.width = "100%";
  iframe.style.height = "500px";
  iframe.style.border = "1px solid #ccc";
  iframe.style.borderRadius = "4px";

  const fileInfo = document.createElement("div");
  fileInfo.classList.add("file-info");
  fileInfo.innerHTML = `
    <span class="filename">${attachment.name}</span>
    <span class="extension">PDF</span>
  `;

  pdfWrapper.appendChild(iframe);
  container.appendChild(pdfWrapper);
  container.appendChild(fileInfo);
}

function renderFileAttachment(attachment, container) {
  container.classList.add("file-type");
  container.innerHTML = `
    <div class="file-preview">
      <span class="filename">${attachment.name}</span>
      <span class="extension">${attachment.extension.toUpperCase()}</span>
    </div>
  `;
}


// ────────────────────────────────────────────────────────────────────────────
// 7. HTML‐conversion / media‐tag conversion pipeline
// ────────────────────────────────────────────────────────────────────────────
function convertHTML(str) {
  if (typeof str !== "string") str = JSON.stringify(str, null, 2);

  // Process media tags BEFORE escaping HTML to preserve existing HTML tags
  let result = convertImageTags(str);
  result = convertImageUrls(result);
  result = convertVideoTags(result);
  result = convertAudioTags(result);
  result = convertIframeTags(result);
  result = convertExistingImgTags(result);

  // Now escape HTML for any remaining content
  result = escapeHTML(result);
  result = convertPathsToLinks(result);
  return result;
}

// Convert <image>…</image> (base64‐encoded) to inline <img src="data:image/...">
function convertImageTags(content) {
  const imageTagRegex = /<image(?:\s+alt="([^"]*)")?(?:\s+width="([^"]*)")?(?:\s+height="([^"]*)")?>(.*?)<\/image>/g;
  return content.replace(imageTagRegex, (match, alt, width, height, base64Content) => {
    try {
      const altText = alt || "Image Attachment";
      const widthStyle = width ? `width: ${width};` : "max-width: 400px;";
      const heightStyle = height ? `height: ${height};` : "height: auto;";
      return `<img
                src="data:image/jpeg;base64,${base64Content}"
                alt="${altText}"
                style="${widthStyle} ${heightStyle} border-radius: 4px; cursor: pointer; display: block; margin: 8px 0;"
                onclick="openImageModal(this.src, 1000)"
                onerror="this.style.display='none'; this.insertAdjacentHTML('afterend', '<div class=\\"media-error\\">Failed to load image</div>')"
              />`;
    } catch (error) {
      console.error("Error processing image tag:", error);
      return `<div class="media-error">Invalid image data</div>`;
    }
  });
}

// Convert any explicit URL ending in an image extension to <img>…</img>
function convertImageUrls(content) {
  const imageUrlRegex = /(https?:\/\/[^\s<>"]+\.(jpg|jpeg|png|gif|bmp|webp|svg))(?:\s|$|[<>"'])/gi;
  return content.replace(imageUrlRegex, (match, url, ext) => {
    return `<img
              src="${url}"
              alt="Image from ${url}"
              style="max-width: 400px; height: auto; border-radius: 4px; cursor: pointer; display: block; margin: 8px 0;"
              onclick="openImageModal('${url}', 1000)"
              onerror="this.style.display='none'; this.insertAdjacentHTML('afterend', '<div class=\\"media-error\\">Failed to load image from ${url}</div>')"
            /> `;
  });
}

// Convert existing HTML <img> tags to ensure they have proper styling and click handlers
function convertExistingImgTags(content) {
  const imgTagRegex = /<img\s+([^>]*?)>/gi;
  return content.replace(imgTagRegex, (match, attributes) => {
    // Extract src attribute
    const srcMatch = attributes.match(/src\s*=\s*["']([^"']*?)["']/i);
    if (!srcMatch) return match; // No src, return original

    const src = srcMatch[1];

    // Extract alt attribute or create default
    const altMatch = attributes.match(/alt\s*=\s*["']([^"']*?)["']/i);
    const alt = altMatch ? altMatch[1] : `Image from ${src}`;

    // Extract width attribute if present
    const widthMatch = attributes.match(/width\s*=\s*["']([^"']*?)["']/i);
    const width = widthMatch ? widthMatch[1] : "400px";

    return `<img
              src="${src}"
              alt="${alt}"
              style="max-width: ${width}; height: auto; border-radius: 4px; cursor: pointer; display: block; margin: 8px 0;"
              onclick="openImageModal('${src}', 1000)"
              onerror="this.style.display='none'; this.insertAdjacentHTML('afterend', '<div class=\\"media-error\\">Failed to load image from ${src}</div>')"
            />`;
  });
}

// Convert <video …>…</video> to an inline <video> tag
function convertVideoTags(content) {
  const videoTagRegex = /<video(?:\s+src="([^"]*)")?(?:\s+width="([^"]*)")?(?:\s+height="([^"]*)")?>(.*?)<\/video>/g;
  return content.replace(videoTagRegex, (match, src, width, height, innerContent) => {
    const videoSrc = src || innerContent;
    if (videoSrc) {
      const widthStyle = width ? `width: ${width};` : "max-width: 100%;";
      const heightStyle = height ? `height: ${height};` : "height: auto;";
      return `<video controls style="${widthStyle} ${heightStyle} border-radius: 4px; margin: 8px 0;">
                <source src="${videoSrc}" type="video/mp4">
                Your browser does not support the video tag.
              </video>`;
    }
    return match;
  });
}

// Convert <audio …>…</audio> to an inline <audio> tag
function convertAudioTags(content) {
  const audioTagRegex = /<audio(?:\s+src="([^"]*)")?>(.*?)<\/audio>/g;
  return content.replace(audioTagRegex, (match, src, innerContent) => {
    const audioSrc = src || innerContent;
    if (audioSrc) {
      return `<audio controls style="width: 100%; margin: 8px 0;">
                <source src="${audioSrc}" type="audio/mpeg">
                Your browser does not support the audio tag.
              </audio>`;
    }
    return match;
  });
}

// Convert <iframe …>…</iframe> to a sandboxed inline <iframe>
function convertIframeTags(content) {
  const iframeTagRegex = /<iframe(?:\s+src="([^"]*)")?(?:\s+width="([^"]*)")?(?:\s+height="([^"]*)")?[^>]*>(.*?)<\/iframe>/g;
  return content.replace(iframeTagRegex, (match, src, width, height) => {
    if (src) {
      const widthAttr = width || "100%";
      const heightAttr = height || "400px";
      return `<iframe
                src="${src}"
                width="${widthAttr}"
                height="${heightAttr}"
                style="border: 1px solid #ccc; border-radius: 4px; margin: 8px 0;"
                sandbox="allow-scripts allow-same-origin allow-forms"
                loading="lazy">
              </iframe>`;
    }
    return match;
  });
}

// Convert plaintext “/some/path/file.txt” into clickable <a> links
function convertPathsToLinks(str) {
  function generateLinks(match) {
    const parts = match.split("/");
    if (!parts[0]) parts.shift();
    let conc = "";
    let html = "";
    for (let part of parts) {
      conc += "/" + part;
      html += `/\<a href="#" class="path-link" onclick="openFileLink('${conc}');">${part}</a>`;
    }
    return html;
  }

  const prefix = `(?:^|[ \`'"\\n]|&#39;|&quot;)`; 
  const folder = `[a-zA-Z0-9_\\/.\\-]`; 
  const file = `[a-zA-Z0-9_\\-\\/]`; 
  const suffix = `(?<!\\.)`;
  const regex = new RegExp(`(?<=${prefix})\\/${folder}*${file}${suffix}`, "g");

  return str.replace(regex, generateLinks);
}

// Escape HTML entities but preserve processed media tags
function escapeHTML(str) {
  // First, protect already processed media tags by replacing them with placeholders
  // This regex matches self-closing tags like <img ... /> and <iframe ... />
  const mediaTagRegex = /<(img|video|audio|iframe)\s[^>]*\/?>/gi;
  const protectedTags = [];
  let protectedStr = str.replace(mediaTagRegex, (match) => {
    const placeholder = `__MEDIA_TAG_${protectedTags.length}__`;
    protectedTags.push(match);
    return placeholder;
  });

  // Also protect any closing tags for video/audio elements
  const closingTagRegex = /<\/(video|audio|iframe)>/gi;
  protectedStr = protectedStr.replace(closingTagRegex, (match) => {
    const placeholder = `__MEDIA_TAG_${protectedTags.length}__`;
    protectedTags.push(match);
    return placeholder;
  });

  // Now escape HTML entities in the remaining content
  const escapeChars = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "'": "&#39;",
    '"': "&quot;",
  };
  protectedStr = protectedStr.replace(/[&<>'"]/g, (char) => escapeChars[char]);

  // Restore the protected media tags
  protectedTags.forEach((tag, index) => {
    protectedStr = protectedStr.replace(`__MEDIA_TAG_${index}__`, tag);
  });

  return protectedStr;
}


// ────────────────────────────────────────────────────────────────────────────
// 8. Text‐to‐Clipboard helper
// ────────────────────────────────────────────────────────────────────────────
async function copyText(text, element) {
  try {
    await navigator.clipboard.writeText(text);
    element.classList.add("copied");
    setTimeout(() => {
      element.classList.remove("copied");
    }, 2000);
  } catch (err) {
    console.error("Failed to copy text:", err);
  }
}


// ────────────────────────────────────────────────────────────────────────────
// 9. A tiny helper to title‐case keys in the KVP table
// ────────────────────────────────────────────────────────────────────────────
function convertToTitleCase(str) {
  return str
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (match) => match.toUpperCase());
}
