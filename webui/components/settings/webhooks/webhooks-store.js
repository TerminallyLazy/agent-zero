import { fetchApi, callJsonApi } from '/js/api.js';

export function createWebhooksStore() {
  return {
    // Webhook configuration
    enabled: false,
    callbackUrl: '',
    secretToken: '1e0535a6bcffac57c9c666a33bd27746e5ee1892ab5f80c265038a9521f155a8',
    
    // Supported events
    supportedEvents: [
      { id: 'APPOINTMENT_CREATE', name: 'Appointment Created', description: 'New appointment scheduled' },
      { id: 'APPOINTMENT_MODIFY', name: 'Appointment Modified', description: 'Appointment details changed' },
      { id: 'APPOINTMENT_DELETE', name: 'Appointment Deleted', description: 'Appointment cancelled/deleted' },
      { id: 'PATIENT_CREATE', name: 'Patient Created', description: 'New patient registered' },
      { id: 'PATIENT_MODIFY', name: 'Patient Modified', description: 'Patient information updated' },
      { id: 'PATIENT_ALLERGY_CREATE', name: 'Allergy Added', description: 'New patient allergy recorded' },
      { id: 'PATIENT_ALLERGY_MODIFY', name: 'Allergy Modified', description: 'Patient allergy updated' },
      { id: 'PATIENT_MEDICATION_CREATE', name: 'Medication Added', description: 'New medication prescribed' },
      { id: 'PATIENT_MEDICATION_MODIFY', name: 'Medication Modified', description: 'Medication updated' },
      { id: 'PATIENT_PROBLEM_CREATE', name: 'Problem Added', description: 'New patient problem recorded' },
      { id: 'PATIENT_PROBLEM_MODIFY', name: 'Problem Modified', description: 'Patient problem updated' },
      { id: 'CLINICAL_NOTE_LOCK', name: 'Note Finalized', description: 'Clinical note locked/finalized' },
      { id: 'CLINICAL_NOTE_UNLOCK', name: 'Note Reopened', description: 'Clinical note unlocked' },
      { id: 'TASK_CREATE', name: 'Task Created', description: 'New task assigned' },
      { id: 'TASK_MODIFY', name: 'Task Modified', description: 'Task updated or completed' },
      { id: 'TASK_DELETE', name: 'Task Deleted', description: 'Task removed' },
      { id: 'LAB_ORDER_CREATE', name: 'Lab Order Created', description: 'New lab order placed' },
      { id: 'LAB_ORDER_MODIFY', name: 'Lab Order Modified', description: 'Lab order updated' },
      { id: 'LAB_ORDER_DELETE', name: 'Lab Order Deleted', description: 'Lab order cancelled' }
    ],
    
    // Selected events
    selectedEvents: [
      'APPOINTMENT_CREATE',
      'APPOINTMENT_MODIFY', 
      'PATIENT_CREATE',
      'PATIENT_MODIFY',
      'CLINICAL_NOTE_LOCK',
      'TASK_CREATE'
    ],
    
    // Webhook status
    isVerified: false,
    lastVerification: null,
    
    // Recent deliveries
    recentDeliveries: [],
    
    // UI state
    showAdvanced: false,
    isConfiguring: false,
    testResult: null,
    
    // Initialize
    async init() {
      // Always use the HTTPS production URL for DrChrono webhooks
      this.callbackUrl = `https://inbox-agent.xyz/drchrono_webhooks`;
      
      // Load saved configuration
      const saved = localStorage.getItem('webhooks_config');
      if (saved) {
        try {
          const config = JSON.parse(saved);
          this.enabled = config.enabled || false;
          this.selectedEvents = config.selectedEvents || this.selectedEvents;
          this.isVerified = config.isVerified || false;
          this.lastVerification = config.lastVerification ? new Date(config.lastVerification) : null;
        } catch (e) {
          console.error('Failed to load webhooks config:', e);
        }
      }
      
      // Load recent deliveries
      await this.loadRecentDeliveries();
    },
    
    // Toggle event selection
    toggleEvent(eventId) {
      const index = this.selectedEvents.indexOf(eventId);
      if (index > -1) {
        this.selectedEvents.splice(index, 1);
      } else {
        this.selectedEvents.push(eventId);
      }
      this.save();
    },
    
    // Check if event is selected
    isEventSelected(eventId) {
      return this.selectedEvents.includes(eventId);
    },
    
    // Verify webhook endpoint
    async verifyWebhook() {
      try {
        this.isConfiguring = true;
        this.testResult = null;
        
        // Test against local endpoint since we can't test the production endpoint directly
        const testMessage = 'verification_test_' + Date.now();
        const response = await fetch('/drchrono_webhooks?msg=' + encodeURIComponent(testMessage), {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json'
          }
        });
        
        if (response.ok) {
          const data = await response.json();
          if (data.secret_token) {
            this.isVerified = true;
            this.lastVerification = new Date();
            this.testResult = {
              success: true,
              message: 'Local webhook endpoint verified successfully! Production endpoint at https://inbox-agent.xyz/drchrono_webhooks should work with DrChrono.'
            };
          } else {
            throw new Error('Invalid verification response');
          }
        } else {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
      } catch (error) {
        this.isVerified = false;
        this.testResult = {
          success: false,
          message: `Local verification failed: ${error.message}. Note: Production endpoint https://inbox-agent.xyz/drchrono_webhooks may still work with DrChrono.`
        };
      } finally {
        this.isConfiguring = false;
        this.save();
      }
    },
    
    // Test webhook with ping
    async pingWebhook() {
      try {
        this.isConfiguring = true;
        this.testResult = null;
        
        // Test webhook ping against local endpoint
        const response = await fetch('/drchrono_webhooks', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-drchrono-event': 'PING',
            'X-drchrono-delivery': 'test_' + Date.now()
          },
          body: JSON.stringify({
            receiver: { id: 'test_webhook' },
            object: { test: true }
          })
        });
        
        if (response.ok) {
          const data = await response.json();
          if (data.status === 'pong') {
            this.testResult = {
              success: true,
              message: 'Local webhook ping successful! Production endpoint should handle DrChrono pings correctly.'
            };
          } else {
            throw new Error('Unexpected ping response: ' + JSON.stringify(data));
          }
        } else {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
      } catch (error) {
        this.testResult = {
          success: false,
          message: `Local ping failed: ${error.message}. Note: Production endpoint may still work with DrChrono.`
        };
      } finally {
        this.isConfiguring = false;
      }
    },
    
    // Load recent webhook deliveries
    async loadRecentDeliveries() {
      try {
        // In a real implementation, this would fetch from a deliveries log
        // For now, return mock data
        this.recentDeliveries = [
          {
            id: 'del_001',
            event: 'PATIENT_CREATE',
            timestamp: new Date(Date.now() - 3600000),
            status: 'delivered',
            attempts: 1
          },
          {
            id: 'del_002', 
            event: 'APPOINTMENT_CREATE',
            timestamp: new Date(Date.now() - 7200000),
            status: 'delivered',
            attempts: 1
          }
        ];
      } catch (error) {
        console.error('Failed to load deliveries:', error);
        this.recentDeliveries = [];
      }
    },
    
    // Generate webhook configuration for DrChrono
    getDrchronoConfig() {
      return {
        callback_url: this.callbackUrl,
        secret_token: this.secretToken,
        events: this.selectedEvents,
        enabled: this.enabled
      };
    },
    
    // Format timestamp
    formatTimestamp(timestamp) {
      if (!timestamp) return 'Never';
      const date = timestamp instanceof Date ? timestamp : new Date(timestamp);
      const now = new Date();
      const diff = now - date;
      
      if (diff < 60000) return 'Just now';
      if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
      if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
      return date.toLocaleDateString();
    },
    
    // Save configuration
    save() {
      const config = {
        enabled: this.enabled,
        selectedEvents: this.selectedEvents,
        isVerified: this.isVerified,
        lastVerification: this.lastVerification?.toISOString()
      };
      localStorage.setItem('webhooks_config', JSON.stringify(config));
    },
    
    // Export configuration for DrChrono setup
    exportConfig() {
      const config = this.getDrchronoConfig();
      const configText = JSON.stringify(config, null, 2);
      
      // Create downloadable file
      const blob = new Blob([configText], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'drchrono-webhook-config.json';
      a.click();
      URL.revokeObjectURL(url);
    }
  }
}