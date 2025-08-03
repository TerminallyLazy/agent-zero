import { fetchApi, callJsonApi } from '/js/api.js';

export function createHistoryStore() {
  return {
    filter: 'all',
    dateRange: 'week', // today, week, month, all
    events: [],
    selectedEvent: null,
    isLoading: false,
    error: null,
    
    // Real-time event tracking
    eventCache: new Map(),
    lastSyncTime: null,
    autoRefreshInterval: null,
    
    // Filter options
    filterOptions: [
      { value: 'all', label: 'All Events' },
      { value: 'agent_action', label: 'Agent Actions' },
      { value: 'user_action', label: 'User Actions' },
      { value: 'system_event', label: 'System Events' }
    ],
    
    dateRangeOptions: [
      { value: 'today', label: 'Today' },
      { value: 'week', label: 'Past Week' },
      { value: 'month', label: 'Past Month' },
      { value: 'all', label: 'All Time' }
    ],
    
    get filteredEvents() {
      let filtered = this.events;
      
      // Apply type filter
      if (this.filter !== 'all') {
        filtered = filtered.filter(e => e.type === this.filter);
      }
      
      // Apply date filter
      const now = new Date();
      const cutoff = new Date();
      
      switch(this.dateRange) {
        case 'today':
          cutoff.setHours(0, 0, 0, 0);
          break;
        case 'week':
          cutoff.setDate(now.getDate() - 7);
          break;
        case 'month':
          cutoff.setMonth(now.getMonth() - 1);
          break;
      }
      
      if (this.dateRange !== 'all') {
        filtered = filtered.filter(e => new Date(e.timestamp) >= cutoff);
      }
      
      return filtered;
    },
    
    async setFilter(f) {
      this.filter = f;
      await this.loadEvents(true); // Refresh with new filter
    },
    
    async setDateRange(range) {
      this.dateRange = range;
      await this.loadEvents(true); // Refresh with new date range
    },
    
    selectEvent(event) {
      this.selectedEvent = event;
    },
    
    closeDetail() {
      this.selectedEvent = null;
    },
    
    // Format helpers
    formatTimestamp(timestamp) {
      const date = new Date(timestamp);
      const now = new Date();
      const diff = now - date;
      
      // Less than 1 hour ago
      if (diff < 60 * 60 * 1000) {
        const mins = Math.floor(diff / (60 * 1000));
        return mins === 0 ? 'Just now' : `${mins}m ago`;
      }
      
      // Less than 24 hours ago
      if (diff < 24 * 60 * 60 * 1000) {
        const hours = Math.floor(diff / (60 * 60 * 1000));
        return `${hours}h ago`;
      }
      
      // Less than 7 days ago
      if (diff < 7 * 24 * 60 * 60 * 1000) {
        const days = Math.floor(diff / (24 * 60 * 60 * 1000));
        return days === 1 ? 'Yesterday' : `${days}d ago`;
      }
      
      // Default to date
      return date.toLocaleDateString();
    },
    
    formatTime(timestamp) {
      return new Date(timestamp).toLocaleTimeString([], { 
        hour: '2-digit', 
        minute: '2-digit' 
      });
    },
    
    formatDate(timestamp) {
      return new Date(timestamp).toLocaleDateString([], { 
        month: 'short', 
        day: 'numeric',
        year: 'numeric'
      });
    },
    
    getEventIcon(type) {
      switch(type) {
        case 'agent_action': return '🤖';
        case 'user_action': return '👤';
        case 'system_event': return '⚙️';
        default: return '📝';
      }
    },
    
    getEventColor(type) {
      switch(type) {
        case 'agent_action': return 'primary';
        case 'user_action': return 'accent';
        case 'system_event': return 'warning';
        default: return '';
      }
    },
    
    getCategoryBadgeClass(category) {
      switch(category) {
        case 'inbox': return '';
        case 'drafts': return 'accent';
        case 'tasks': return 'primary';
        case 'appointments': return 'warning';
        case 'settings': return 'muted';
        case 'system': return 'danger';
        default: return '';
      }
    },
    
    // Export functionality
    async exportHistory() {
      try {
        // Get all events (not just filtered) for complete export
        const response = await callJsonApi('/audit_export', {
          format: 'csv',
          filter: this.filter,
          date_range: this.dateRange
        });
        
        if (response.success && response.download_url) {
          // Server-generated export
          window.open(response.download_url, '_blank');
        } else {
          // Fallback to client-side export
          this.exportClientSide();
        }
        
      } catch (error) {
        console.error('Export failed, using client-side export:', error);
        this.exportClientSide();
      }
    },

    // Client-side export fallback
    exportClientSide() {
      const data = this.filteredEvents.map(e => ({
        timestamp: e.timestamp,
        type: e.type,
        user: e.user,
        action: e.action,
        description: e.description,
        patient: e.patient || '',
        agent: e.agent || '',
        details: JSON.stringify(e.details)
      }));
      
      // Escape CSV fields
      const escapeCsvField = (field) => {
        if (field === null || field === undefined) return '';
        const str = String(field);
        if (str.includes(',') || str.includes('"') || str.includes('\n')) {
          return `"${str.replace(/"/g, '""')}"`;
        }
        return str;
      };
      
      const csv = [
        ['Timestamp', 'Type', 'User', 'Action', 'Description', 'Patient', 'Agent', 'Details'],
        ...data.map(row => Object.values(row).map(escapeCsvField))
      ].map(row => row.join(',')).join('\n');
      
      // Create download
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `clinical-audit-log-${new Date().toISOString().split('T')[0]}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      
      if (window.toast) {
        window.toast('Audit log exported successfully', 'success', 3000);
      }
    },
    
    // Load real audit logs from Agent Zero
    async loadEvents(refresh = false) {
      if (!refresh && this.isLoading) return;
      
      this.isLoading = true;
      this.error = null;
      
      try {
        // Get audit logs from all contexts
        const response = await callJsonApi('/audit_logs', {
          filter: this.filter !== 'all' ? this.filter : undefined,
          date_range: this.dateRange,
          since: this.lastSyncTime,
          limit: 100
        });
        
        if (response.success) {
          const newEvents = response.events.map(this.normalizeEvent);
          
          if (refresh || !this.lastSyncTime) {
            // Full refresh
            this.events = newEvents;
          } else {
            // Incremental update
            const existingIds = new Set(this.events.map(e => e.id));
            const uniqueNewEvents = newEvents.filter(e => !existingIds.has(e.id));
            this.events = [...uniqueNewEvents, ...this.events];
          }
          
          // Sort by timestamp
          this.events.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
          
          // Update sync time
          this.lastSyncTime = new Date().toISOString();
          
          // Cache events
          this.events.forEach(event => {
            this.eventCache.set(event.id, event);
          });
          
        } else {
          throw new Error(response.message || 'Failed to load audit logs');
        }
        
      } catch (error) {
        console.error('Failed to load audit events:', error);
        this.error = error.message || 'Failed to load audit logs';
        
        // Fallback to Agent Zero system logs if audit endpoint doesn't exist
        await this.loadFromSystemLogs();
      }
      
      this.isLoading = false;
    },

    // Fallback: Load from Agent Zero system logs
    async loadFromSystemLogs() {
      try {
        // Get all contexts to extract activity
        const contextsResponse = await callJsonApi('/contexts_get', {});
        
        if (contextsResponse.contexts) {
          const events = [];
          
          // Process each context for activity events
          for (const context of contextsResponse.contexts) {
            try {
              // Get logs for this context
              const logsResponse = await callJsonApi('/logs_get', {
                context_id: context.id,
                limit: 20
              });
              
              if (logsResponse.logs) {
                // Convert logs to audit events
                const contextEvents = logsResponse.logs
                  .filter(log => log.type && log.content)
                  .map(log => this.convertLogToEvent(log, context));
                
                events.push(...contextEvents);
              }
            } catch (logError) {
              console.warn(`Failed to load logs for context ${context.id}:`, logError);
            }
          }
          
          // Sort and store events
          this.events = events.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
        }
        
      } catch (error) {
        console.error('Failed to load from system logs:', error);
        this.events = [];
      }
    },

    // Convert Agent Zero log entry to audit event
    convertLogToEvent(log, context) {
      const timestamp = log.timestamp || new Date().toISOString();
      const contextName = context.name || `Context ${context.id}`;
      
      // Determine event type and details based on log type
      let type, category, action, description, agent;
      
      switch (log.type) {
        case 'user':
          type = 'user_action';
          category = 'inbox';
          action = 'Message sent';
          description = `User message: ${this.truncateText(log.content, 100)}`;
          break;
          
        case 'response':
          type = 'agent_action';
          category = 'agents';
          action = 'Response generated';
          description = `Agent response: ${this.truncateText(log.content, 100)}`;
          agent = this.extractAgentFromContext(contextName);
          break;
          
        case 'tool':
          type = 'agent_action';
          category = 'tasks';
          action = log.heading || 'Tool executed';
          description = `Tool: ${log.heading || 'Unknown'} - ${this.truncateText(log.content, 100)}`;
          agent = this.extractAgentFromContext(contextName);
          break;
          
        case 'info':
        case 'warning':
        case 'error':
          type = 'system_event';
          category = 'system';
          action = log.type.charAt(0).toUpperCase() + log.type.slice(1);
          description = this.truncateText(log.content, 150);
          break;
          
        default:
          type = 'system_event';
          category = 'system';
          action = 'System activity';
          description = this.truncateText(log.content, 150);
      }
      
      return {
        id: `${context.id}-${log.id || Date.now()}`,
        timestamp,
        type,
        category,
        user: 'Clinical User', // TODO: Extract from context if available
        agent,
        action,
        description,
        contextId: context.id,
        contextName,
        details: {
          logId: log.id,
          logType: log.type,
          originalContent: log.content,
          kvps: log.kvps || {}
        }
      };
    },

    // Extract agent name from context name
    extractAgentFromContext(contextName) {
      if (contextName.includes('Lab Notifier')) return 'Lab Notifier';
      if (contextName.includes('Refill Processor')) return 'Refill Processor';
      if (contextName.includes('Appointment Monitor')) return 'Appointment Monitor';
      if (contextName.includes('Inbox Drafter')) return 'Inbox Drafter';
      return 'Agent Zero';
    },

    // Normalize event from different sources
    normalizeEvent(rawEvent) {
      // If it's already normalized, return as-is
      if (rawEvent.id && rawEvent.timestamp && rawEvent.type) {
        return rawEvent;
      }
      
      // Handle different event formats
      return {
        id: rawEvent.id || `evt-${Date.now()}`,
        timestamp: rawEvent.timestamp || rawEvent.created_at || new Date().toISOString(),
        type: rawEvent.type || 'system_event',
        category: rawEvent.category || 'system',
        user: rawEvent.user || rawEvent.username || 'System',
        agent: rawEvent.agent,
        patient: rawEvent.patient || rawEvent.patient_name,
        action: rawEvent.action || rawEvent.event_type || 'Action',
        description: rawEvent.description || rawEvent.message || '',
        details: rawEvent.details || rawEvent.metadata || {}
      };
    },

    // Helper to truncate text
    truncateText(text, maxLength) {
      if (!text) return '';
      return text.length > maxLength ? text.substring(0, maxLength) + '...' : text;
    },

    // Start auto-refresh
    startAutoRefresh() {
      this.stopAutoRefresh();
      this.autoRefreshInterval = setInterval(() => {
        this.loadEvents(false); // Incremental refresh
      }, 30000); // Refresh every 30 seconds
    },

    // Stop auto-refresh
    stopAutoRefresh() {
      if (this.autoRefreshInterval) {
        clearInterval(this.autoRefreshInterval);
        this.autoRefreshInterval = null;
      }
    },

    // Manual refresh
    async refresh() {
      await this.loadEvents(true);
    },

    // Initialize
    async init() {
      await this.loadEvents(true);
      this.startAutoRefresh();
    },

    // Cleanup
    destroy() {
      this.stopAutoRefresh();
    }
  }
}