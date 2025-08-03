import { fetchApi, callJsonApi } from '/js/api.js';

export function createInboxStore() {
  return {
    items: [],
    selected: null,
    filter: 'all',
    draft: '',
    isLoading: false,
    error: null,

    get filteredItems() {
      if (this.filter === 'all') return this.items;
      if (this.filter === 'signoff') return this.items.filter(i => i.needsSignoff);
      return this.items.filter(i => i.category === this.filter);
    },

    async setFilter(f) { 
      this.filter = f; 
      await this.loadInboxItems();
    },
    select(item) { this.selected = item; this.draft = item.draft || ''; },

    async summarize() {
      if (!this.selected) return;
      
      try {
        // Use Agent Zero to generate summary
        const response = await callJsonApi('/inbox_summarize', {
          item_id: this.selected.id,
          content: this.selected.body || this.selected.preview,
          type: this.selected.type
        });
        
        if (response.success) {
          this.selected.summary = response.summary;
        } else {
          throw new Error(response.message || 'Failed to generate summary');
        }
      } catch (error) {
        console.error('Failed to generate summary:', error);
        if (window.toast) {
          window.toast('Failed to generate summary', 'error', 3000);
        }
      }
    },

    async generateDraft() {
      if (!this.selected) return;
      
      try {
        // Use specialized agent to generate draft
        const agentId = this.getAgentForType(this.selected.type);
        
        const response = await callJsonApi('/inbox_generate_draft', {
          item_id: this.selected.id,
          agent_id: agentId,
          item_type: this.selected.type,
          patient: this.selected.patient,
          content: this.selected.body || this.selected.preview,
          context: {
            medications: this.selected.meds,
            allergies: this.selected.allergy,
            nextAppointment: this.selected.nextAppt
          }
        });
        
        if (response.success) {
          this.draft = response.draft;
          this.selected.draft = response.draft;
          this.selected.needsSignoff = true;
        } else {
          throw new Error(response.message || 'Failed to generate draft');
        }
      } catch (error) {
        console.error('Failed to generate draft:', error);
        if (window.toast) {
          window.toast('Failed to generate draft', 'error', 3000);
        }
      }
    },

    // Determine which agent should handle this type of message
    getAgentForType(type) {
      switch (type) {
        case 'lab': return 'lab-notifier';
        case 'refill': return 'refill-processor';
        case 'appt': return 'appointment-monitor';
        case 'patient':
        case 'colleague':
        default: return 'inbox-drafter';
      }
    },

    async approveAndSend() {
      if (!this.selected || !this.draft) return;
      
      try {
        const response = await callJsonApi('/inbox_send_message', {
          item_id: this.selected.id,
          patient: this.selected.patient,
          draft: this.draft,
          type: this.selected.type
        });
        
        if (response.success) {
          this.selected.needsSignoff = false;
          this.selected.status = 'sent';
          this.selected.sentAt = new Date().toISOString();
          
          if (window.toast) {
            window.toast(`Message sent to ${this.selected.patient}`, 'success', 3000);
          }
          
          // Log the action
          this.logAction('approved_and_sent', {
            patient: this.selected.patient,
            type: this.selected.type,
            draft_length: this.draft.length
          });
        } else {
          throw new Error(response.message || 'Failed to send message');
        }
      } catch (error) {
        console.error('Failed to send message:', error);
        if (window.toast) {
          window.toast('Failed to send message', 'error', 3000);
        }
      }
    },

    async requestChanges() {
      if (!this.selected) return;
      
      const reason = prompt('What changes would you like the agent to make?');
      if (!reason) return;
      
      try {
        const response = await callJsonApi('/inbox_request_changes', {
          item_id: this.selected.id,
          current_draft: this.draft,
          change_request: reason,
          agent_id: this.getAgentForType(this.selected.type)
        });
        
        if (response.success) {
          this.draft = response.revised_draft;
          this.selected.draft = response.revised_draft;
          
          if (window.toast) {
            window.toast('Agent is revising the draft', 'info', 3000);
          }
          
          // Log the action
          this.logAction('requested_changes', {
            patient: this.selected.patient,
            reason: reason
          });
        } else {
          throw new Error(response.message || 'Failed to request changes');
        }
      } catch (error) {
        console.error('Failed to request changes:', error);
        if (window.toast) {
          window.toast('Failed to request changes', 'error', 3000);
        }
      }
    },

    // Log user actions for audit trail
    async logAction(action, details) {
      try {
        await callJsonApi('/audit_log', {
          type: 'user_action',
          category: 'inbox',
          action: action,
          description: `${action.replace('_', ' ')} for ${details.patient}`,
          details: details
        });
      } catch (error) {
        console.error('Failed to log action:', error);
      }
    },

    // Add new message/draft to inbox
    addDraft(message) {
      this.items.unshift({
        id: message.id,
        initials: this.getInitials(message.patient || 'Unknown'),
        subject: message.subject,
        patient: message.patient,
        preview: message.content ? message.content.substring(0, 50) + '...' : '',
        type: message.type || 'patient',
        category: this.getCategoryForType(message.type || 'patient'),
        badge: this.getBadgeForType(message.type || 'patient'),
        badgeClass: this.getBadgeClassForType(message.type || 'patient'),
        needsSignoff: message.status === 'draft',
        body: message.content || '',
        status: message.status || 'new',
        createdAt: message.timestamp || new Date().toISOString()
      });
    },

    // Helper functions
    getInitials(name) {
      return name.split(' ').map(n => n[0]).join('').toUpperCase();
    },

    getCategoryForType(type) {
      switch (type) {
        case 'lab': return 'labs';
        case 'refill': return 'refills';
        case 'appt': return 'appointments';
        case 'colleague': return 'colleagues';
        default: return 'patients';
      }
    },

    getBadgeForType(type) {
      switch (type) {
        case 'lab': return 'Lab';
        case 'refill': return 'Refill';
        case 'appt': return 'Appt';
        case 'colleague': return 'Colleague';
        default: return 'Patient';
      }
    },

    getBadgeClassForType(type) {
      switch (type) {
        case 'lab': return 'lab';
        case 'refill': return 'refill';
        default: return '';
      }
    },

    // Load real inbox messages
    async loadInboxItems() {
      this.isLoading = true;
      this.error = null;
      
      try {
        const response = await callJsonApi('/inbox_messages', {
          filter: this.filter !== 'all' ? this.filter : undefined,
          limit: 50
        });
        
        if (response.success) {
          this.items = response.messages.map(this.normalizeInboxItem);
        } else {
          throw new Error(response.message || 'Failed to load inbox messages');
        }
      } catch (error) {
        console.error('Failed to load inbox:', error);
        this.error = error.message || 'Failed to load inbox messages';
        
        // Fallback to empty state with helpful message
        this.items = [];
      }
      
      this.isLoading = false;
    },

    // Normalize inbox item from API response
    normalizeInboxItem(rawItem) {
      return {
        id: rawItem.id,
        initials: this.getInitials(rawItem.patient || rawItem.sender || 'Unknown'),
        subject: rawItem.subject || rawItem.title,
        patient: rawItem.patient || rawItem.patient_name,
        preview: rawItem.preview || (rawItem.content ? rawItem.content.substring(0, 50) + '...' : ''),
        type: rawItem.type || rawItem.message_type || 'patient',
        category: rawItem.category || this.getCategoryForType(rawItem.type),
        badge: rawItem.badge || this.getBadgeForType(rawItem.type),
        badgeClass: rawItem.badge_class || this.getBadgeClassForType(rawItem.type),
        needsSignoff: rawItem.needs_signoff || rawItem.status === 'draft',
        body: rawItem.content || rawItem.body || '',
        nextAppt: rawItem.next_appointment,
        meds: rawItem.medications,
        allergy: rawItem.allergies,
        draft: rawItem.draft,
        status: rawItem.status || 'new',
        createdAt: rawItem.created_at || rawItem.timestamp
      };
    },

    async init() {
      await this.loadInboxItems();
    }
  }
}
