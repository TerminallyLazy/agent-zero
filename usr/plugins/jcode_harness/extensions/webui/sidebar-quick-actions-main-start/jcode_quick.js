// jcode_harness sidebar quick actions.
// Both buttons open the plugin's main modal so the user can manage the
// daemon, log in to providers, and pick a resumable session in a UI that
// can actually render the data — no more `prompt()` picker.
//
// Modal opener mirrors plugins/_time_travel and plugins/_browser:
// `ensureModalOpen('/plugins/<name>/webui/main.html')` is A0's canonical
// surface for plugin modals (with `openModal` as a fallback).
import { createStore } from "/js/AlpineStore.js";

const MODAL_PATH = "/plugins/jcode_harness/webui/main.html";

function _openMain() {
  if (typeof window.ensureModalOpen === "function") {
    window.ensureModalOpen(MODAL_PATH);
    return true;
  }
  if (typeof window.openModal === "function") {
    window.openModal(MODAL_PATH);
    return true;
  }
  window.$store?.notificationStore?.frontendError?.(
    "Plugin modal API not available; open Plugins → jcode harness manually.",
    "jcode",
  );
  return false;
}

const model = {
  newSession() {
    _openMain();
  },

  resumeSessionList() {
    _openMain();
  },
};

export const store = createStore("jcodeQuick", model);
