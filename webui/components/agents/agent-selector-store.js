import { createStore } from "../../js/AlpineStore.js";

/**
 * Agent Selector Store - Alpine.js store for managing agent selection
 */
const agentSelectorModel = {
    // State
    agents: [],
    selectedAgentId: null,
    isLoading: false,
    error: null,
    showDropdown: false,
    showActivityDrawer: false,
    activeTab: 'agents',
    _initialized: false,
    _refreshInterval: null,
    _flowGraph: null,

    // Initialize the store
    async init() {
        // Prevent multiple initializations
        if (this._initialized) {
            return;
        }

        console.log('AgentSelector: Initializing store...');

        // Ensure agents array is properly initialized
        if (!Array.isArray(this.agents)) {
            this.agents = [];
        }

        // Wait for required functions to be available
        await this.waitForRequiredFunctions();

        console.log('AgentSelector: Required functions available, loading agents...');
        await this.loadAgents();
        // Auto-select the main agent if none selected
        if (!this.selectedAgentId && this.agents.length > 0) {
            const mainAgent = this.agents.find(a => a.type === 'main');
            if (mainAgent) {
                this.selectedAgentId = mainAgent.id;
            }
        }

        // Set up periodic refresh for agent status (only once)
        if (!this._refreshInterval) {
            this._refreshInterval = setInterval(() => {
                if (!this.isLoading) {
                    this.loadAgents();
                }
            }, 5000); // Refresh every 5 seconds
        }

        this._initialized = true;
        
        // Initialize flow graph when drawer is opened
        this.initFlowGraph();
    },
    
    // Initialize GitGraph flow visualization
    initFlowGraph() {
        // Since we're loading the script in index.html, just create the flow graph
        if (window.AgentFlowGraph) {
            this.createFlowGraph();
        } else {
            // Wait a bit for the script to load
            setTimeout(() => {
                if (window.AgentFlowGraph) {
                    this.createFlowGraph();
                } else {
                    console.error('AgentFlowGraph not available after timeout');
                }
            }, 500);
        }
    },
    
    createFlowGraph() {
        console.log('createFlowGraph called');
        // Wait for the container to be available
        const checkContainer = () => {
            const container = document.getElementById('agentFlowGraph');
            console.log('Checking container:', container ? 'found' : 'not found');
            console.log('AgentFlowGraph class available:', window.AgentFlowGraph ? 'yes' : 'no');

            // Use Mermaid implementation for vertical subordinate agent flow
            if (container && window.AgentMermaid) {
                if (!this._flowGraph) {
                    console.log('Creating AgentMermaid instance...');
                    try {
                        this._flowGraph = new AgentMermaid('agentFlowGraph', {
                            width: 280,
                            height: 400,
                            theme: 'default'
                        });
                        console.log('AgentMermaid created successfully:', this._flowGraph);
                    } catch (error) {
                        console.error('Error creating AgentMermaid:', error);
                    }
                } else {
                    console.log('AgentMermaid already exists, skipping creation');
                }
            } else if (container && window.AgentGitGraph) {
                if (!this._flowGraph) {
                    console.log('Creating AgentGitGraph instance...');
                    try {
                        this._flowGraph = new AgentGitGraph('agentFlowGraph', {
                            width: 280,
                            height: 400
                        });
                        console.log('AgentGitGraph created successfully:', this._flowGraph);
                    } catch (error) {
                        console.error('Error creating AgentGitGraph:', error);
                    }
                } else {
                    console.log('AgentGitGraph already exists, skipping creation');
                }
            } else if (container && window.AgentFlowGraph) {
                if (!this._flowGraph) {
                    console.log('Creating AgentFlowGraph instance (fallback)...');
                    try {
                        this._flowGraph = new AgentFlowGraph('agentFlowGraph', {
                            width: 280,
                            height: 400
                        });
                        console.log('AgentFlowGraph created successfully:', this._flowGraph);
                    } catch (error) {
                        console.error('Error creating AgentFlowGraph:', error);
                    }
                } else {
                    console.log('AgentFlowGraph already exists, skipping creation');
                }
            } else {
                console.log('Container or flow graph classes not ready, retrying in 100ms...');
                setTimeout(checkContainer, 100);
            }
        };
        checkContainer();
    },
    
    // Wait for required functions to be available
    async waitForRequiredFunctions() {
        let attempts = 0;
        const maxAttempts = 50; // 5 seconds total wait time
        
        while (attempts < maxAttempts) {
            if (window.sendJsonData && window.getContext) {
                return; // Functions are available
            }
            
            // Wait 100ms before checking again
            await new Promise(resolve => setTimeout(resolve, 100));
            attempts++;
        }
        
        throw new Error('Required functions (sendJsonData, getContext) not available after waiting');
    },
    
    // Load agents from API
    async loadAgents() {
        this.isLoading = true;
        this.error = null;
        
        try {
            console.log('AgentSelector: Loading agents...');
            
            // Check if required functions are available
            if (!window.sendJsonData) {
                throw new Error('sendJsonData function not available');
            }
            if (!window.getContext) {
                throw new Error('getContext function not available');
            }
            
            console.log('AgentSelector: Calling sendJsonData...');
            
            // Try direct fetch instead of sendJsonData
            const response = await fetch('/agents_list', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    context: window.getContext()
                })
            }).then(res => res.json());
            
            console.log('AgentSelector: Response received:', response);
            
            if (response.success) {
                // Filter out duplicates by ID and ensure unique keys
                const rawAgents = response.agents || [];
                const uniqueAgents = [];
                const seenIds = new Set();
                
                rawAgents.forEach(agent => {
                    if (agent && agent.id && !seenIds.has(agent.id)) {
                        seenIds.add(agent.id);
                        uniqueAgents.push(agent);
                    }
                });
                
                this.agents = uniqueAgents;

                // Force Alpine.js reactivity update for agents list
                if (globalThis.Alpine) {
                    globalThis.Alpine.nextTick(() => {
                        const store = globalThis.Alpine.store('agentSelector');
                        if (store) {
                            store.agents = this.agents;
                        }
                    });
                }

                // Debug logging
                console.log('Agents loaded:', this.agents);
                console.log('Active agent:', response.active_agent);

                // Update selected agent if it was the active one
                if (response.active_agent && !this.selectedAgentId) {
                    this.selectedAgentId = response.active_agent;

                    // Force reactivity for selected agent too
                    if (globalThis.Alpine) {
                        globalThis.Alpine.nextTick(() => {
                            const store = globalThis.Alpine.store('agentSelector');
                            if (store) {
                                store.selectedAgentId = response.active_agent;
                            }
                        });
                    }
                }
            } else {
                throw new Error('Failed to load agents');
            }
        } catch (error) {
            this.error = error.message;
            console.error('Error loading agents:', error);
            // Ensure agents array is never undefined
            if (!Array.isArray(this.agents)) {
                this.agents = [];
            }
        } finally {
            this.isLoading = false;
        }
    },
    
    // Select an agent
    async selectAgent(agentId) {
        if (agentId === this.selectedAgentId) return;
        
        try {
            // Check if required functions are available
            if (!window.sendJsonData || !window.getContext) {
                throw new Error('Required functions not available');
            }
            
            const response = await window.sendJsonData('/agent_switch', {
                context: window.getContext(),
                target_agent_id: agentId
            });
            
            if (response.success) {
                this.selectedAgentId = agentId;
                this.showDropdown = false;

                // Force Alpine.js reactivity update
                if (globalThis.Alpine) {
                    globalThis.Alpine.nextTick(() => {
                        // Trigger reactivity for both components
                        const store = globalThis.Alpine.store('agentSelector');
                        if (store) {
                            store.selectedAgentId = agentId;
                        }
                    });
                }

                // Notify other components
                window.dispatchEvent(new CustomEvent('agentChanged', {
                    detail: { agentId, agentInfo: response.agent_info }
                }));

                // Update chat input placeholder
                this.updateChatPlaceholder(agentId);
            } else {
                throw new Error('Failed to switch agent');
            }
        } catch (error) {
            this.error = error.message;
            console.error('Error switching agent:', error);
        }
    },
    
    // Get currently selected agent info
    getSelectedAgent() {
        return this.agents.find(a => a.id === this.selectedAgentId);
    },
    
    // Get agent display name
    getAgentDisplayName(agent) {
        if (!agent) return 'Unknown Agent';
        
        switch (agent.type) {
            case 'main': return 'Agent Zero';
            case 'subordinate': return `@${agent.role || 'subordinate'}`;
            case 'peer': return `@${agent.role || 'peer'}`;
            default: return `@${agent.id.slice(0, 8)}`;
        }
    },
    
    // Get agent mention handle (for @ mentions)
    getAgentMentionHandle(agent) {
        if (!agent) return '';
        
        switch (agent.type) {
            case 'main': return '@agent0';
            case 'subordinate': return `@${agent.role || 'subordinate'}`;
            case 'peer': return `@${agent.role || 'peer'}`;
            default: return `@${agent.id.slice(0, 8)}`;
        }
    },
    
    // Get agent status indicator
    getAgentStatusClass(agent) {
        if (!agent) return 'status-unknown';
        
        switch (agent.status) {
            case 'active':
            case 'ready':
            case 'idle': return 'status-active';
            case 'busy':
            case 'working': return 'status-busy';
            case 'paused':
            case 'stopping': return 'status-paused';
            case 'error':
            case 'failed': return 'status-error';
            default: return 'status-unknown';
        }
    },
    
    // Update chat input placeholder
    updateChatPlaceholder(agentId) {
        const chatInput = document.getElementById('chat-input');
        if (chatInput) {
            const agent = this.agents.find(a => a.id === agentId);
            const agentName = this.getAgentDisplayName(agent);
            chatInput.placeholder = `Message ${agentName}...`;
        }
    },
    
    // Toggle dropdown
    toggleDropdown() {
        this.showDropdown = !this.showDropdown;
        // Close activity drawer when opening dropdown to prevent interference
        if (this.showDropdown) {
            this.showActivityDrawer = false;
        }
    },
    
    // Close dropdown
    closeDropdown() {
        this.showDropdown = false;
    },
    
    // Toggle activity drawer
    toggleActivityDrawer() {
        this.showActivityDrawer = !this.showActivityDrawer;
        // Close dropdown when opening drawer to prevent interference
        this.showDropdown = false;
    },
    
    // Close activity drawer
    closeActivityDrawer() {
        this.showActivityDrawer = false;
    },

    // Force synchronization between components
    forceSync() {
        if (globalThis.Alpine) {
            globalThis.Alpine.nextTick(() => {
                const store = globalThis.Alpine.store('agentSelector');
                if (store) {
                    store.agents = this.agents;
                    store.selectedAgentId = this.selectedAgentId;
                    store.isLoading = this.isLoading;
                    store.error = this.error;
                    store.showDropdown = this.showDropdown;
                    store.showActivityDrawer = this.showActivityDrawer;
                }
            });
        }
    },
    
    // Find agent by mention handle
    findAgentByMention(mentionText) {
        const cleanMention = mentionText.toLowerCase().replace('@', '');
        return this.agents.find(agent => {
            const handle = this.getAgentMentionHandle(agent).toLowerCase().replace('@', '');
            return handle === cleanMention;
        });
    },
    
    // Handle @ mention in chat input
    handleMentionInput(inputText, cursorPosition) {
        const textBeforeCursor = inputText.substring(0, cursorPosition);
        const mentionMatch = textBeforeCursor.match(/@(\w*)$/);
        
        if (mentionMatch) {
            const mentionPrefix = mentionMatch[1];
            const matchingAgents = this.agents.filter(agent => {
                const handle = this.getAgentMentionHandle(agent).toLowerCase().replace('@', '');
                return handle.startsWith(mentionPrefix.toLowerCase());
            });
            
            return {
                showSuggestions: true,
                suggestions: matchingAgents,
                mentionStart: mentionMatch.index,
                mentionPrefix: mentionPrefix
            };
        }
        
        return { showSuggestions: false, suggestions: [] };
    },
    
    // Apply mention selection to input
    applyMention(agent, inputElement, mentionStart, mentionPrefix) {
        const currentValue = inputElement.value;
        const beforeMention = currentValue.substring(0, mentionStart);
        const afterMention = currentValue.substring(mentionStart + mentionPrefix.length + 1); // +1 for @
        const mentionHandle = this.getAgentMentionHandle(agent);
        
        const newValue = beforeMention + mentionHandle + ' ' + afterMention;
        inputElement.value = newValue;
        
        // Set cursor position after the mention
        const cursorPos = beforeMention.length + mentionHandle.length + 1;
        inputElement.setSelectionRange(cursorPos, cursorPos);
        
        // Auto-select the mentioned agent
        this.selectAgent(agent.id);
    }
};

export const store = createStore("agentSelector", agentSelectorModel);