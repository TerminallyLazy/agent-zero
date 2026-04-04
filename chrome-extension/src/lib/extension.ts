export async function sendRuntimeMessage<T>(message: Record<string, unknown>): Promise<T> {
  return await new Promise<T>((resolve, reject) => {
    chrome.runtime.sendMessage(message, (response) => {
      const runtimeError = chrome.runtime.lastError;
      if (runtimeError) {
        reject(new Error(runtimeError.message));
        return;
      }

      if (response && typeof response === "object" && "ok" in response && response.ok === false) {
        const messageText =
          "error" in response && typeof response.error === "string" && response.error
            ? response.error
            : "The extension request failed.";
        reject(new Error(messageText));
        return;
      }

      resolve(response as T);
    });
  });
}

export function connectSidePanelPort(): chrome.runtime.Port {
  return chrome.runtime.connect({ name: "agent-zero-sidepanel" });
}
