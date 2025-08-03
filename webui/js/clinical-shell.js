// Minimal clinical shell bootstrap without removing existing modules yet.
import { createInboxStore } from '../components/inbox/inbox-store.js';

window.__mountClinicalUI = function mountClinical() {
  if (document.body.classList.contains('clinical')) return;

  // Add clinical stylesheet
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = 'css/clinical.css';
  document.head.appendChild(link);

  // Replace body with clinical shell container while keeping modals appended later
  document.body.classList.add('clinical');

  const shell = document.createElement('div');
  shell.className = 'app-shell';
  shell.setAttribute('x-data', `{
    view: 'inbox',
    search: '',
    connected: true,
  }`);

  shell.innerHTML = `
    <div class="vnav">
      <div class="logo" title="Agent Zero"></div>
      <div class="nav-btn" :class="{active: view==='inbox'}" @click="view='inbox'" title="Inbox">📥</div>
      <div class="nav-btn" :class="{active: view==='agents'}" @click="view='agents'" title="Agents & Tasks">🤖</div>
      <div class="nav-btn" :class="{active: view==='drafts'}" @click="view='drafts'" title="Drafts & Sign-offs">✍️</div>
      <div class="nav-btn" :class="{active: view==='patients'}" @click="view='patients'" title="Patient Context">🩺</div>
      <div class="nav-btn" :class="{active: view==='history'}" @click="view='history'" title="History">🕘</div>
      <div class="nav-btn" :class="{active: view==='settings'}" @click="view='settings'" title="Settings">⚙️</div>
    </div>

    <div class="topbar">
      <div class="search">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zM9.5 14C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>
        <input type="text" placeholder="Search patients, messages, labs..." x-model="search" />
      </div>
      <div class="status-dot" :style="{background: connected ? 'var(--success)' : 'var(--danger)'}" title="Connection status"></div>
    </div>

    <div class="main">
      <div x-show="view==='inbox'" x-data="$store.inbox">
        <x-component path="/inbox/inbox-list.html"></x-component>
      </div>
      <div x-show="view==='agents'" style="padding:16px">Agents & Tasks (coming next)</div>
      <div x-show="view==='drafts'" style="padding:16px">Drafts & Sign-offs (coming next)</div>
      <div x-show="view==='patients'" style="padding:16px">Patient Context (coming next)</div>
      <div x-show="view==='history'" style="padding:16px">History (coming next)</div>
      <div x-show="view==='settings'" style="padding:16px">Settings (coming next)</div>
    </div>
  `;

  // Hide existing container but keep in DOM for now (settings modals, etc.)
  const old = document.querySelector('.container');
  if (old) old.style.display = 'none';
  document.body.appendChild(shell);

  // Initialize Alpine store
  if (!window.Alpine) {
    console.warn('Alpine not ready yet; clinical UI depends on it.');
  } else {
    if (!Alpine.store('inbox')) Alpine.store('inbox', createInboxStore());
    Alpine.start();
    Alpine.store('inbox').init();
  }
}

// Auto-mount when DOM ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => window.__mountClinicalUI());
} else {
  window.__mountClinicalUI();
}
