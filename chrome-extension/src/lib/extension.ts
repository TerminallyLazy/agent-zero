export async function sendRuntimeMessage<T>(message: Record<string, unknown>): Promise<T> {
  return (await chrome.runtime.sendMessage(message)) as T;
}

export function connectSidePanelPort(): chrome.runtime.Port {
  return chrome.runtime.connect({ name: "agent-zero-sidepanel" });
}
