import { fetchApi, callJsonApi } from '/js/api.js';

export function createAgentChatStore() {
  return {
    // UI State
    isOpen: false,
    activeAgent: null,
    activeThread: null,
    isMinimized: false,
    
    // Chat data
    conversations: [],
    agents: [],
    currentMessage: '',
    isTyping: false,
    typingAgents: [],
    
    // Agent Zero Integration
    agentContexts: new Map(), // Map of agentId -> Agent Zero context ID
    messageHistory: new Map(), // Map of contextId -> message history
    
    // Connection state
    isConnected: true,
    lastActivity: null,
    
    // Available agents with their specialties
    availableAgents: [
      {
        id: 'agent-zero',
        name: 'Agent Zero',
        role: 'Orchestrator',
        avatar: '🧠',
        status: 'online',
        specialty: 'General coordination, complex reasoning, task orchestration',
        capabilities: ['reasoning', 'coordination', 'medical-analysis', 'workflow-management'],
        description: 'Primary AI assistant for complex medical tasks and coordination',
        systemPrompt: 'You are Agent Zero, a specialized medical AI orchestrator. You coordinate complex medical tasks, provide clinical reasoning, and manage workflow between different medical specialists. Focus on comprehensive analysis and clear communication with healthcare providers.'
      },
      {
        id: 'lab-notifier',
        name: 'Lab Notifier',
        role: 'Lab Specialist',
        avatar: '🔬',
        status: 'online',
        specialty: 'Lab result interpretation, flagging abnormal values',
        capabilities: ['lab-analysis', 'result-interpretation', 'flagging'],
        description: 'Specialized in processing and interpreting laboratory results',
        systemPrompt: 'You are a specialized Lab Notifier agent. Your role is to analyze laboratory results, identify abnormal values, interpret clinical significance, and provide clear recommendations for follow-up. Always include reference ranges and clinical context in your analysis.'
      },
      {
        id: 'refill-processor',
        name: 'Refill Processor',
        role: 'Medication Specialist',
        avatar: '💊',
        status: 'online',
        specialty: 'Medication refills, drug interactions, dosage verification',
        capabilities: ['medication-management', 'refill-processing', 'interaction-checking'],
        description: 'Handles medication refills and drug safety checks',
        systemPrompt: 'You are a Refill Processor agent specializing in medication management. Review refill requests, check for drug interactions, verify appropriate dosing, and ensure prescription safety. Provide clear approval/denial decisions with rationale.'
      },
      {
        id: 'appointment-monitor',
        name: 'Appointment Monitor',
        role: 'Scheduling Specialist',
        avatar: '📅',
        status: 'online',
        specialty: 'Appointment management, scheduling optimization',
        capabilities: ['scheduling', 'calendar-management', 'patient-coordination'],
        description: 'Manages appointments and scheduling workflows',
        systemPrompt: 'You are an Appointment Monitor agent focused on scheduling optimization. Help manage patient appointments, suggest optimal scheduling based on urgency and availability, and coordinate follow-up care timing.'
      },
      {
        id: 'inbox-drafter',
        name: 'Inbox Drafter',
        role: 'Communication Specialist',
        avatar: '✍️',
        status: 'online',
        specialty: 'Patient communication, message drafting, triage',
        capabilities: ['communication', 'drafting', 'triage', 'patient-interaction'],
        description: 'Assists with patient communication and message composition',
        systemPrompt: 'You are an Inbox Drafter agent specializing in patient communication. Help draft clear, empathetic, and medically accurate responses to patient messages. Ensure appropriate tone and include necessary medical information while being patient-friendly.'
      }
    ],
    
    
    // Get active conversations
    get activeConversations() {
      return this.conversations.filter(c => c.messages.length > 0)
        .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
    },
    
    // Get unread count
    get totalUnread() {
      return this.conversations.reduce((sum, conv) => sum + (conv.unread || 0), 0);
    },
    
    // Toggle chat panel
    toggleChat() {
      this.isOpen = !this.isOpen;
      if (this.isOpen && this.conversations.length === 0) {
        this.loadConversations();
      }
    },
    
    // Minimize/restore chat
    toggleMinimize() {
      this.isMinimized = !this.isMinimized;
    },
    
    // Close chat
    closeChat() {
      this.isOpen = false;
      this.activeThread = null;
    },
    
    // Start conversation with specific agent
    async startConversation(agentId, context = null) {
      const agent = this.availableAgents.find(a => a.id === agentId);
      if (!agent) return;
      
      // Check if conversation already exists
      let conversation = this.conversations.find(c => c.agentId === agentId && !c.patientContext);
      
      if (!conversation) {
        // Create new Agent Zero context for this agent
        const agentContext = await this.createAgentContext(agent, context);
        
        conversation = {
          id: `conv-${Date.now()}`,
          agentId: agentId,
          contextId: agentContext.id,
          subject: `Chat with ${agent.name}`,
          patientContext: context?.patient || null,
          lastMessage: '',
          timestamp: new Date().toISOString(),
          unread: 0,
          messages: []
        };
        this.conversations.unshift(conversation);
        this.agentContexts.set(agentId, agentContext.id);
      }
      
      this.selectConversation(conversation);
      this.isOpen = true;
    },

    // Create Agent Zero context for specialized agent
    async createAgentContext(agent, context = null) {
      try {
        // Initialize context with agent-specific system message
        let systemMessage = agent.systemPrompt;
        if (context?.patient) {
          systemMessage += `\n\nCurrent patient context: ${context.patient}`;
        }
        
        const response = await callJsonApi('/context_new', {
          name: `${agent.name} - Clinical Inbox`,
          system_prompt: systemMessage
        });
        
        if (response.success) {
          return {
            id: response.context_id,
            name: response.name
          };
        } else {
          throw new Error(response.message || 'Failed to create context');
        }
      } catch (error) {
        console.error('Failed to create agent context:', error);
        throw error;
      }
    },
    
    // Select conversation thread
    selectConversation(conversation) {
      this.activeThread = conversation;
      this.activeAgent = this.availableAgents.find(a => a.id === conversation.agentId);
      
      // Mark as read
      conversation.unread = 0;
      
      // Auto-scroll to bottom when selecting a conversation
      this.scrollToBottom();
    },
    
    // Send message to Agent Zero
    async sendMessage() {
      console.log('sendMessage called'); // Debug
      
      if (!this.currentMessage.trim() || !this.activeThread) {
        console.log('Message validation failed:', { 
          hasMessage: !!this.currentMessage.trim(), 
          hasActiveThread: !!this.activeThread 
        }); // Debug
        return;
      }
      
      console.log('Sending message to active thread:', this.activeThread.id, this.activeThread.contextId); // Debug
      
      const userMessage = {
        id: `m-${Date.now()}`,
        sender: 'user',
        content: this.currentMessage.trim(),
        timestamp: new Date().toISOString(),
        context: this.activeThread.patientContext ? { patient: this.activeThread.patientContext } : null
      };
      
      this.activeThread.messages.push(userMessage);
      this.activeThread.lastMessage = this.currentMessage.trim();
      this.activeThread.timestamp = new Date().toISOString();
      
      // Force Alpine.js reactivity by reassigning the active thread
      this.activeThread = { ...this.activeThread };
      
      console.log('User message added, total messages now:', this.activeThread.messages.length); // Debug
      
      // Auto-scroll after adding user message
      this.scrollToBottom();
      
      const messageToSend = this.currentMessage;
      this.currentMessage = '';
      
      // Show agent typing
      this.addTypingAgent(this.activeAgent.id);
      console.log('Added typing indicator for agent:', this.activeAgent.id); // Debug
      
      try {
        // Send message to Agent Zero backend
        await this.sendToAgentZero(this.activeThread.contextId, messageToSend);
        console.log('Message sending completed successfully'); // Debug
      } catch (error) {
        console.error('Failed to send message to Agent Zero:', error);
        this.removeTypingAgent(this.activeAgent.id);
        
        // Add error message
        const errorMessage = {
          id: `m-${Date.now()}`,
          sender: 'system',
          content: 'Failed to send message. Please try again.',
          timestamp: new Date().toISOString(),
          isError: true
        };
        this.activeThread.messages.push(errorMessage);
      }
    },

    // Send message to Agent Zero backend
    async sendToAgentZero(contextId, message) {
      console.log('Sending message to Agent Zero:', contextId, message); // Debug
      
      try {
        const response = await callJsonApi('/message_async', {
          context_id: contextId,
          message: message,
          attachments: []
        });
        
        console.log('Message sent successfully, response:', response); // Debug
        
        // Start polling for responses
        console.log('Starting polling for responses...'); // Debug
        this.pollForResponse(contextId);
        
        return response;
      } catch (error) {
        console.error('Error sending to Agent Zero:', error);
        throw error;
      }
    },

    // Poll for Agent Zero responses
    async pollForResponse(contextId) {
      console.log('Starting to poll for response, context:', contextId); // Debug
      
      const pollInterval = 1000; // Poll every second
      const maxPolls = 60; // Max 60 seconds
      let pollCount = 0;
      
      const poll = async () => {
        console.log(`Polling attempt ${pollCount + 1} for context:`, contextId); // Debug
        
        try {
          const lastLogIndex = this.getLastLogIndex(contextId);
          console.log('Requesting logs after index:', lastLogIndex); // Debug
          
          const response = await callJsonApi('/logs_get', {
            context_id: contextId,
            after_log_index: lastLogIndex
          });
          
          console.log('Poll response:', response); // Debug
          
          if (response.logs && response.logs.length > 0) {
            console.log('Found logs, processing:', response.logs.length); // Debug
            this.processAgentZeroLogs(contextId, response.logs);
          } else {
            console.log('No new logs found'); // Debug
            
            // If no new logs and this is early in polling, try getting all logs
            if (pollCount < 3 && lastLogIndex === 0) {
              console.log('Trying to get all logs for new context...'); // Debug
              try {
                const allLogsResponse = await callJsonApi('/logs_get', {
                  context_id: contextId,
                  after_log_index: -1, // Get all logs
                  limit: 100
                });
                console.log('All logs response:', allLogsResponse); // Debug
                if (allLogsResponse.logs && allLogsResponse.logs.length > 0) {
                  console.log('Found logs when requesting all, processing:', allLogsResponse.logs.length); // Debug
                  this.processAgentZeroLogs(contextId, allLogsResponse.logs);
                }
              } catch (error) {
                console.error('Error getting all logs:', error);
              }
            }
          }
          
          // Continue polling if agent is still working
          if (response.is_running && pollCount < maxPolls) {
            pollCount++;
            console.log(`Agent still running, continuing to poll (${pollCount}/${maxPolls})`); // Debug
            setTimeout(poll, pollInterval);
          } else {
            console.log('Stopping poll - is_running:', response.is_running, 'pollCount:', pollCount); // Debug
            
            // When agent stops running, do one final comprehensive log fetch to catch any final outputs
            if (!response.is_running) {
              console.log('Agent stopped - doing final comprehensive log fetch...'); // Debug
              try {
                const finalResponse = await callJsonApi('/logs_get', {
                  context_id: contextId,
                  after_log_index: -1, // Get ALL logs
                  limit: 200
                });
                console.log('Final logs response:', finalResponse); // Debug
                if (finalResponse.logs && finalResponse.logs.length > 0) {
                  console.log('Processing final logs:', finalResponse.logs.length); // Debug
                  this.processAgentZeroLogs(contextId, finalResponse.logs);
                }
              } catch (error) {
                console.error('Error getting final logs:', error);
              }
            }
            
            this.removeTypingAgent(this.activeAgent?.id);
          }
        } catch (error) {
          console.error('Error polling for response:', error);
          this.removeTypingAgent(this.activeAgent?.id);
        }
      };
      
      console.log('Setting initial poll timeout'); // Debug
      setTimeout(poll, pollInterval);
    },

    // Auto-scroll to bottom of messages container
    scrollToBottom() {
      // Use setTimeout to ensure DOM has updated with new messages
      setTimeout(() => {
        const messagesContainer = document.querySelector('.messages-container');
        console.log('Scroll attempt - container found:', !!messagesContainer);
        if (messagesContainer) {
          console.log('Container dimensions:', {
            scrollHeight: messagesContainer.scrollHeight,
            clientHeight: messagesContainer.clientHeight,
            scrollTop: messagesContainer.scrollTop
          });
          messagesContainer.scrollTop = messagesContainer.scrollHeight;
          console.log('After scroll - scrollTop:', messagesContainer.scrollTop);
        }
      }, 100);
    },

    // Process Agent Zero log entries into chat messages
    processAgentZeroLogs(contextId, logs) {
      const conversation = this.conversations.find(c => c.contextId === contextId);
      if (!conversation) {
        console.warn('No conversation found for context:', contextId);
        return;
      }
      
      // Ensure messages array exists
      if (!conversation.messages) {
        conversation.messages = [];
        console.log('Initialized messages array for conversation:', conversation.id);
      }
      
      console.log('Processing logs for context:', contextId, logs); // Debug logging
      
      let messagesAdded = false;
      logs.forEach(log => {
        console.log('Processing log:', log.type, log.content ? log.content.substring(0, 100) + '...' : 'NO CONTENT'); // Debug logging
        console.log('Full log object:', log); // Show full log for debugging
        
        // Handle ALL agent responses - capture everything that's not user input
        if (log.content && log.content.trim().length > 0 && log.type !== 'user' && log.type !== 'input') {
          const agentMessage = {
            id: `m-${Date.now()}-${log.id}`,
            sender: conversation.agentId,
            content: log.content,
            timestamp: log.timestamp || new Date().toISOString(),
            reasoning: log.kvps?.reasoning || null,
            logId: log.id,
            logType: log.type,
            heading: log.heading
          };
          
          // Avoid duplicate messages - check both logId and content
          const isDuplicate = conversation.messages.find(m => 
            m.logId === log.id || 
            (m.content === log.content && m.sender === conversation.agentId && Math.abs(new Date(m.timestamp) - new Date(log.timestamp || new Date())) < 1000)
          );
          
          if (!isDuplicate) {
            console.log('Adding agent message:', agentMessage); // Debug logging
            conversation.messages.push(agentMessage);
            conversation.lastMessage = log.content;
            conversation.timestamp = new Date().toISOString();
            messagesAdded = true;
            
            console.log('Conversation now has', conversation.messages.length, 'messages'); // Debug logging
            console.log('Active thread messages:', this.activeThread?.messages?.length); // Debug logging
            
            // Force Alpine.js reactivity by reassigning the active thread if this is the active conversation
            if (this.activeThread?.id === conversation.id) {
              console.log('Updating active thread to trigger reactivity...'); // Debug
              // Create a shallow copy to trigger Alpine's reactivity
              this.activeThread = { ...conversation };
              console.log('Active thread updated, message count:', this.activeThread.messages?.length); // Debug
            }
            
            // Mark conversation as having unread messages if not active
            if (this.activeThread?.id !== conversation.id) {
              conversation.unread = (conversation.unread || 0) + 1;
            }
          } else {
            console.log('Skipping duplicate message:', log.id, log.content?.substring(0, 50)); // Debug logging
          }
        }
      });
      
      // Update last log index
      if (logs.length > 0) {
        const maxLogId = Math.max(...logs.map(l => l.id || 0));
        console.log('Updating last log index from', this.getLastLogIndex(contextId), 'to', maxLogId);
        this.setLastLogIndex(contextId, maxLogId);
      }
      
      // Remove typing indicator if we got any substantial response
      if (logs.some(log => 
        log.content && log.content.trim().length > 0 && (
          log.type === 'response' || 
          log.type === 'agent_response' || 
          log.type === 'message' ||
          log.type === 'assistant' ||
          (log.heading && log.heading.toLowerCase().includes('response')) ||
          (log.heading && log.heading.toLowerCase().includes('assistant')) ||
          (log.content.length > 10 && log.type !== 'user')
        )
      )) {
        this.removeTypingAgent(conversation.agentId);
      }
      
      // Auto-scroll if messages were added to the active conversation
      if (messagesAdded && this.activeThread?.contextId === contextId) {
        this.scrollToBottom();
      }
      
      // Debug message state after processing
      this.debugMessages();
    },

    // Track last processed log index per context
    getLastLogIndex(contextId) {
      return this.messageHistory.get(contextId)?.lastLogIndex || 0;
    },

    setLastLogIndex(contextId, index) {
      const history = this.messageHistory.get(contextId) || {};
      history.lastLogIndex = index;
      this.messageHistory.set(contextId, history);
    },
    
    
    // Typing indicators
    addTypingAgent(agentId) {
      if (!this.typingAgents.includes(agentId)) {
        this.typingAgents.push(agentId);
      }
    },
    
    removeTypingAgent(agentId) {
      this.typingAgents = this.typingAgents.filter(id => id !== agentId);
    },
    
    isAgentTyping(agentId) {
      return this.typingAgents.includes(agentId);
    },
    
    // Quick actions
    quickMessage(preset) {
      const presets = {
        'review-labs': 'Please review the latest lab results and provide your analysis.',
        'draft-response': 'Can you help me draft a response to this patient message?',
        'check-medications': 'Please check this medication request for any issues or interactions.',
        'schedule-followup': 'What would be the appropriate follow-up timeline for this case?'
      };
      
      this.currentMessage = presets[preset] || preset;
    },
    
    // Load conversations from Agent Zero contexts
    async loadConversations() {
      try {
        const response = await callJsonApi('/contexts_get', {});
        
        if (response.contexts) {
          // Filter contexts that belong to clinical inbox
          const clinicalContexts = response.contexts.filter(ctx => 
            ctx.name && ctx.name.includes('Clinical Inbox')
          );
          
          // Convert to conversation format
          this.conversations = clinicalContexts.map(ctx => {
            const agent = this.availableAgents.find(a => ctx.name.includes(a.name));
            return {
              id: `conv-${ctx.id}`,
              agentId: agent?.id || 'agent-zero',
              contextId: ctx.id,
              subject: ctx.name,
              patientContext: null, // TODO: Extract from context if available
              lastMessage: '',
              timestamp: ctx.created_at || new Date().toISOString(),
              unread: 0,
              messages: []
            };
          });
          
          // Load recent messages for each conversation
          for (const conv of this.conversations) {
            await this.loadConversationMessages(conv);
          }
        }
      } catch (error) {
        console.error('Failed to load conversations:', error);
        this.conversations = [];
      }
    },

    // Load messages for a specific conversation
    async loadConversationMessages(conversation) {
      try {
        const response = await callJsonApi('/logs_get', {
          context_id: conversation.contextId,
          limit: 50 // Load last 50 log entries
        });
        
        if (response.logs) {
          conversation.messages = [];
          this.processAgentZeroLogs(conversation.contextId, response.logs);
          
          // Update conversation metadata
          if (conversation.messages.length > 0) {
            const lastMessage = conversation.messages[conversation.messages.length - 1];
            conversation.lastMessage = lastMessage.content;
            conversation.timestamp = lastMessage.timestamp;
          }
        }
      } catch (error) {
        console.error('Failed to load conversation messages:', error);
      }
    },
    
    // Debug function to check message state
    debugMessages() {
      console.log('=== MESSAGE DEBUG ===');
      console.log('Active thread:', this.activeThread?.id);
      console.log('Active thread messages:', this.activeThread?.messages?.length);
      console.log('All conversations:', this.conversations.length);
      this.conversations.forEach(conv => {
        console.log(`Conversation ${conv.id}: ${conv.messages?.length || 0} messages`);
        if (conv.messages) {
          conv.messages.forEach((msg, idx) => {
            console.log(`  Message ${idx}: ${msg.sender} - ${msg.content?.substring(0, 50)}...`);
          });
        }
      });
      console.log('=== END DEBUG ===');
    },
    
    // Clear conversation
    clearConversation(conversationId) {
      const index = this.conversations.findIndex(c => c.id === conversationId);
      if (index !== -1) {
        this.conversations.splice(index, 1);
        if (this.activeThread?.id === conversationId) {
          this.activeThread = null;
          this.activeAgent = null;
        }
      }
    },
    
    // Format timestamp
    formatTime(timestamp) {
      const date = new Date(timestamp);
      const now = new Date();
      const diff = now - date;
      
      if (diff < 60000) return 'Just now';
      if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
      if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
      return date.toLocaleDateString();
    },
    
    // Render Markdown to HTML
    renderMarkdown(text) {
      if (!text) return '';
      
      let html = text;
      
      // Headers
      html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
      html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
      html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');
      
      // Bold
      html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
      html = html.replace(/__(.*?)__/g, '<strong>$1</strong>');
      
      // Italic
      html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
      html = html.replace(/_(.*?)_/g, '<em>$1</em>');
      
      // Code blocks (```code```)
      html = html.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
      
      // Inline code (`code`)
      html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
      
      // Links
      html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
      
      // Unordered lists
      html = html.replace(/^\* (.+)$/gm, '<li>$1</li>');
      html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
      html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');
      
      // Ordered lists
      html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');
      
      // Line breaks
      html = html.replace(/\n\n/g, '</p><p>');
      html = html.replace(/\n/g, '<br>');
      
      // Wrap in paragraphs if not already wrapped
      if (!html.includes('<p>') && !html.includes('<h') && !html.includes('<ul>') && !html.includes('<pre>')) {
        html = '<p>' + html + '</p>';
      }
      
      return html;
    },
    
    // Initialize
    async init() {
      await this.loadConversations();
      this.lastActivity = new Date();
      
      // Check connection status periodically
      setInterval(async () => {
        try {
          const response = await fetchApi('/health', { method: 'GET' });
          this.isConnected = response.ok;
        } catch (error) {
          this.isConnected = false;
        }
      }, 10000);
    }
  }
}