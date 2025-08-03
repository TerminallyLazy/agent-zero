// Clinical Inbox Orchestrator shell bootstrap
console.log('Clinical shell script loading...');

// Prevent old UI scripts from interfering
window.CLINICAL_MODE = true;
import { createAgentsStore } from '../components/agents/agents-store.js';
import { createDraftsStore } from '../components/drafts/drafts-store.js';
import { createInboxStore } from '../components/inbox/inbox-store.js';
import { createPatientStore } from '../components/patient/patient-store.js';
import { createHistoryStore } from '../components/history/history-store.js';
import { createDrChronoStore } from '../components/settings/drchrono/drchrono-store.js';
import { createWebhooksStore } from '../components/settings/webhooks/webhooks-store.js';
import { createAgentChatStore } from '../components/agent-chat/agent-chat-store.js';
import { icons, createIcon } from '../components/shared/icons.js';
console.log('Imports completed');

window.__mountClinicalUI = function mountClinical() {
  console.log('Mounting clinical UI...');
  if (document.body.classList.contains('clinical')) {
    console.log('Clinical UI already mounted');
    return;
  }

  // Add clinical stylesheet
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = 'css/clinical.css';
  document.head.appendChild(link);
  
  // Add style to hide any remaining old UI elements
  const hideOldUIStyle = document.createElement('style');
  hideOldUIStyle.textContent = `
    body.clinical-mode .container:not(.app-shell),
    body.clinical-mode #user-time,
    body.clinical-mode #user-time-container,
    body.clinical-mode .user-time,
    body.clinical-mode .sidebar:not(.clinical-sidebar),
    body.clinical-mode #sidebar:not(.clinical-sidebar),
    body.clinical-mode .main-content:not(.clinical-main) {
      display: none !important;
    }
  `;
  document.head.appendChild(hideOldUIStyle);

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
      <div class="nav-btn" :class="{active: view==='inbox'}" @click="view='inbox'" title="Inbox">${createIcon('inbox', 'icon-lg')}</div>
      <div class="nav-btn" :class="{active: view==='agents'}" @click="view='agents'" title="Agents & Tasks">${createIcon('agents', 'icon-lg')}</div>
      <div class="nav-btn" :class="{active: view==='drafts'}" @click="view='drafts'" title="Drafts & Sign-offs">${createIcon('drafts', 'icon-lg')}</div>
      <div class="nav-btn" :class="{active: view==='patients'}" @click="view='patients'" title="Patient Context">${createIcon('patients', 'icon-lg')}</div>
      <div class="nav-btn" :class="{active: view==='history'}" @click="view='history'" title="History">${createIcon('history', 'icon-lg')}</div>
      <div class="nav-btn" :class="{active: view==='settings'}" @click="view='settings'" title="Settings">${createIcon('settings', 'icon-lg')}</div>
    </div>

    <div class="topbar">
      <div class="search">
        ${createIcon('search', 'icon-sm')}
        <input type="text" placeholder="Search patients, messages, labs..." x-model="search" />
      </div>
      <div class="status-dot" :style="{background: connected ? 'var(--success)' : 'var(--danger)'}" title="Connection status"></div>
    </div>

    <div class="main">
      <div x-show="view==='inbox'" x-data="$store.inbox">
        <x-component path="/inbox/inbox-list.html"></x-component>
      </div>
      <div x-show="view==='agents'" x-data="$store.agents" x-init="$store.agents.init && $store.agents.init()">
        <x-component path="/agents/agents-view.html"></x-component>
      </div>
          <div x-show="view==='drafts'" x-data="$store.drafts" x-init="$store.drafts.init && $store.drafts.init()">
        <x-component path="/drafts/drafts-view.html"></x-component>
      </div>
      <div x-show="view==='patients'" x-data="$store.patient" x-init="$store.patient.init && $store.patient.init()">
        <x-component path="/patient/patient-panel.html"></x-component>
      </div>
      <div x-show="view==='history'" x-data="$store.history" x-init="$store.history.init && $store.history.init()">
        <x-component path="/history/history-view.html"></x-component>
      </div>
      <div x-show="view==='settings'">
        <div class="settings-container" style="padding: 20px;">
          <h2 style="margin-bottom: 24px;">Settings</h2>
          <div class="settings-sections">
            <div class="settings-section">
              <h3>External Services</h3>
              <div x-data="$store.drchrono" x-init="$store.drchrono.init && $store.drchrono.init()">
                <x-component path="/settings/drchrono/drchrono-view.html"></x-component>
              </div>
            </div>
            <div class="settings-section">
              <h3>Webhook Integration</h3>
              <div x-data="$store.webhooks" x-init="$store.webhooks.init && $store.webhooks.init()">
                <x-component path="/settings/webhooks/webhooks-view.html"></x-component>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    
    <!-- Global bottom action bar -->
    <div class="bottom-action-bar">
      <div class="action-group">
        <button class="fab" @click="$store.agentChat.toggleChat()" title="Chat with Agent Zero">
          ${createIcon('compose', 'icon-md')}
        </button>
        <div class="context-actions">
          <button class="btn" x-show="view==='inbox'" @click="$store.agentChat.startConversation('inbox-drafter')">
            ${createIcon('message', 'icon-sm')}
            Ask Drafter
          </button>
          <button class="btn" x-show="view==='agents'" @click="$store.agentChat.startConversation('agent-zero')">
            ${createIcon('agents', 'icon-sm')}
            Ask Agent Zero
          </button>
          <button class="btn" x-show="view==='patients'" @click="$store.agentChat.startConversation('agent-zero', {patient: $store.patient.selectedPatient?.name})">
            ${createIcon('patients', 'icon-sm')}
            Discuss Patient
          </button>
          <button class="btn" x-show="view==='history'" @click="$store.history?.exportHistory()">
            ${createIcon('export', 'icon-sm')}
            Export
          </button>
        </div>
      </div>
      <div class="status-indicators">
        <span>3 tasks running</span>
        <span>•</span>
        <span>12 items pending</span>
        <span>•</span>
        <span :style="{color: connected ? 'var(--success)' : 'var(--danger)'}">●</span>
        <span x-text="connected ? 'Connected' : 'Disconnected'"></span>
      </div>
    </div>
    
    <!-- Agent Chat Interface -->
    <div x-data="$store.agentChat" x-init="$store.agentChat.init && $store.agentChat.init()">
      <x-component path="/agent-chat/agent-chat-panel.html"></x-component>
    </div>
  `;

  // Initialize Alpine stores BEFORE adding HTML
  if (!window.Alpine) {
    console.warn('Alpine not ready yet; clinical UI depends on it.');
    // Try to wait for Alpine and retry
    setTimeout(() => {
      if (window.Alpine) {
        console.log('Alpine now available, retrying mount...');
        window.__mountClinicalUI();
      }
    }, 100);
    return;
  }
  
  console.log('Alpine is available, proceeding with mount...');

  // Register all stores if not already registered
  if (!Alpine.store('inbox')) Alpine.store('inbox', createInboxStore());
  if (!Alpine.store('agents')) {
    console.log('Registering agents store');
    const agentsStore = createAgentsStore();
    console.log('Agents store created:', !!agentsStore, Object.keys(agentsStore));
    Alpine.store('agents', agentsStore);
    console.log('Agents store registered');
  }
  if (!Alpine.store('drafts')) Alpine.store('drafts', createDraftsStore());
  if (!Alpine.store('patient')) Alpine.store('patient', createPatientStore());
  if (!Alpine.store('history')) Alpine.store('history', createHistoryStore());
  if (!Alpine.store('drchrono')) Alpine.store('drchrono', createDrChronoStore());
  if (!Alpine.store('webhooks')) Alpine.store('webhooks', createWebhooksStore());
  if (!Alpine.store('agentChat')) {
    console.log('Registering agentChat store');
    try {
      const chatStore = createAgentChatStore();
      console.log('Chat store created:', !!chatStore);
      console.log('Chat store methods:', Object.keys(chatStore));
      Alpine.store('agentChat', chatStore);
      console.log('Chat store registered');
    } catch (error) {
      console.error('Error creating agentChat store:', error);
      // Fallback simple store for testing
      Alpine.store('agentChat', {
        isOpen: false,
        toggleChat() { 
          this.isOpen = !this.isOpen; 
          console.log('Chat toggled:', this.isOpen);
        },
        startConversation(agentId, context = null) {
          console.log('Starting conversation with:', agentId, context);
          this.isOpen = true;
        },
        init() {
          console.log('Simple agentChat store initialized');
        }
      });
    }
  }
  
  // Debug: Check if agentChat store is available
  console.log('agentChat store available:', !!Alpine.store('agentChat'));
  
  // Add global debugging functions
  window.testAgentChat = function() {
    const store = Alpine.store('agentChat');
    console.log('Store test:', {
      store: !!store,
      methods: store ? Object.keys(store) : 'none',
      toggleChat: typeof store?.toggleChat
    });
    if (store && store.toggleChat) {
      store.toggleChat();
    }
  };
  
  window.testAgentsStore = function() {
    const store = Alpine.store('agents');
    console.log('Agents store test:', {
      store: !!store,
      methods: store ? Object.keys(store) : 'none',
      createAgent: typeof store?.createAgent,
      showAddAgent: store?.showAddAgent,
      newAgent: store?.newAgent,
      agents: store?.agents?.length
    });
    return store;
  };
  
  // Remove all existing UI elements that might interfere
  const oldElements = [
    '.container',
    '#chat-container', 
    '#messages-container',
    '.chat-messages',
    '.original-chat',
    '#user-time',
    '#user-time-container',
    '.user-time',
    '.sidebar',
    '#sidebar',
    '.main-content',
    '#main-content'
  ];
  
  oldElements.forEach(selector => {
    const elements = document.querySelectorAll(selector);
    elements.forEach(element => {
      console.log('Removing old UI element:', selector);
      element.remove();
    });
  });
  
  // Stop any running intervals from the old UI
  const maxIntervalId = window.setTimeout(() => {}, 0);
  for (let i = 1; i <= maxIntervalId; i++) {
    window.clearInterval(i);
    window.clearTimeout(i);
  }
  console.log('Cleared old UI timers and intervals');
  
  // Override global functions that the old UI might call
  window.updateUserTime = function() { /* no-op */ };
  window.handleResize = function() { /* no-op */ };
  window.initializeOldUI = function() { /* no-op */ };
  
  // Add body class to indicate clinical UI is active
  document.body.classList.add('clinical-mode');
  document.body.classList.remove('agent-zero-original');
  
  document.body.appendChild(shell);

  // Initialize Alpine if not started
  if (!window.Alpine._started) {
    Alpine.start();
  }
  
  // Initialize all stores asynchronously
  (async () => {
    try {
      console.log('Initializing stores...');
      await Alpine.store('inbox').init();
      await Alpine.store('agents').init();
      await Alpine.store('drafts').init();
      await Alpine.store('patient').init();
      await Alpine.store('history').init();
      await Alpine.store('drchrono').init();
      await Alpine.store('webhooks').init();
      await Alpine.store('agentChat').init();
      console.log('All stores initialized successfully');
    } catch (error) {
      console.error('Error initializing stores:', error);
    }
  })();
}

// Auto-mount when DOM ready
console.log('Clinical shell script loaded');

// Add a global function to force mount clinical UI for debugging
window.forceMountClinical = function() {
  console.log('Force mounting clinical UI...');
  // Remove any existing clinical class
  document.body.classList.remove('clinical');
  // Call mount function
  window.__mountClinicalUI();
};

function tryMount() {
  console.log('Attempting to mount clinical UI...');
  console.log('Document ready state:', document.readyState);
  console.log('Alpine available:', !!window.Alpine);
  
  if (window.Alpine) {
    window.__mountClinicalUI();
  } else {
    console.log('Waiting for Alpine...');
    // Wait for Alpine to be available
    let attempts = 0;
    const checkAlpine = setInterval(() => {
      attempts++;
      if (window.Alpine) {
        console.log('Alpine found after', attempts, 'attempts');
        clearInterval(checkAlpine);
        window.__mountClinicalUI();
      } else if (attempts > 50) { // 5 seconds max wait
        console.error('Alpine not found after 5 seconds, giving up');
        clearInterval(checkAlpine);
      }
    }, 100);
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', tryMount);
} else {
  tryMount();
}
