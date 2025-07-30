/**
 * AgentMermaid - Mermaid.js-based agent flow visualization
 * Uses Mermaid.js gitgraph and flowchart diagrams to visualize subordinate agents
 */

// Prevent duplicate class declarations
if (typeof window.AgentMermaid === 'undefined') {

class AgentMermaid {
    constructor(containerId, options = {}) {
        this.container = document.getElementById(containerId);
        this.containerId = containerId;
        this.options = {
            width: options.width || 320,
            height: options.height || 600,
            theme: options.theme || 'default',
            ...options
        };

        this.flows = new Map();
        this.activeFlows = new Set();
        this.updateInterval = null;
        this.mermaidInitialized = false;

        // Dynamic agent tracking
        this.agentBranches = new Map(); // agent_id -> branch_info
        this.agentColors = new Map(); // agent_id -> color
        this.availableColors = ['c1', 'c2', 'c3', 'c4', 'c5', 'c6', 'c7', 'c8'];
        this.colorIndex = 0;
        this.lastRenderState = null; // Track last render to detect changes

        this.init();
    }
    
    async init() {
        console.log('AgentMermaid.init() called');
        console.log('Container:', this.container);

        if (!this.container) {
            console.error('Container not found!');
            return;
        }

        // Load Mermaid.js library if not already loaded
        await this.loadMermaidLibrary();

        // Create container structure
        this.container.innerHTML = `
            <div class="agent-flow-header">
                <h3>Agent Flow Visualization (Mermaid GitGraph)</h3>
                <div class="flow-controls">
                    <button id="pauseBtn" class="btn-sm">Pause</button>
                    <button id="clearBtn" class="btn-sm">Clear</button>
                    <button id="refreshBtn" class="btn-sm">Refresh</button>
                </div>
            </div>
            <div class="mermaid-container" id="mermaidContainer">
                <div class="loading">Loading Mermaid.js...</div>
            </div>
            
            <div class="flow-legend" id="flowLegend">
                <!-- Dynamic legend items will be added here -->
            </div>

            <div class="flow-progress-panel" id="flowProgressPanel">
                <h4>Agent Progress & Status</h4>
                <div class="progress-content" id="progressContent">
                    <!-- Agent progress and status will be populated here -->
                </div>
            </div>
        `;

        // Initialize Mermaid
        this.initializeMermaid();

        // Set up event handlers
        document.getElementById('pauseBtn').addEventListener('click', () => this.togglePause());
        document.getElementById('clearBtn').addEventListener('click', () => this.clearFlows());
        document.getElementById('refreshBtn').addEventListener('click', () => this.refreshDiagram());

        // Start periodic updates
        this.startUpdates();
    }

    async loadMermaidLibrary() {
        // Check if Mermaid is already loaded
        if (window.mermaid) {
            console.log('Mermaid.js already loaded');
            return;
        }

        console.log('Loading Mermaid.js library...');

        return new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = 'https://unpkg.com/mermaid@10.9.1/dist/mermaid.min.js';
            script.onload = () => {
                console.log('Mermaid.js loaded successfully');
                resolve();
            };
            script.onerror = () => {
                console.error('Failed to load Mermaid.js');
                reject(new Error('Failed to load Mermaid.js'));
            };
            document.head.appendChild(script);
        });
    }

    initializeMermaid() {
        if (!window.mermaid) {
            console.error('Mermaid library not available');
            return;
        }

        try {
            // Initialize Mermaid with gitgraph configuration
            window.mermaid.initialize({
                startOnLoad: false,
                theme: 'dark',
                gitGraph: {
                    theme: 'dark',
                    themeVariables: {
                        primaryColor: '#3B82F6',
                        primaryTextColor: '#ffffff',
                        primaryBorderColor: '#E5E7EB',
                        lineColor: '#6B7280',
                        secondaryColor: '#F3F4F6',
                        tertiaryColor: '#F9FAFB',
                        background: '#1a1a1a',
                        mainBranchName: 'main'
                    },
                    mainBranchName: 'main',
                    showBranches: true,
                    showCommitLabel: true,
                    rotateCommitLabel: false
                },
                securityLevel: 'loose'
            });

            this.mermaidInitialized = true;
            console.log('Mermaid initialized successfully');
        } catch (error) {
            console.error('Error initializing Mermaid:', error);
        }
    }

    startUpdates() {
        this.updateInterval = setInterval(() => {
            this.fetchAndUpdateFlows();
        }, 1000); // Update every 1 second for real-time agent tracking
    }
    
    togglePause() {
        const btn = document.getElementById('pauseBtn');
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
            this.updateInterval = null;
            btn.textContent = 'Resume';
        } else {
            this.startUpdates();
            btn.textContent = 'Pause';
        }
    }

    clearFlows() {
        this.flows.clear();
        this.activeFlows.clear();
        this.agentBranches.clear();
        this.agentColors.clear();
        this.colorIndex = 0;
        this.lastRenderState = null;
        this.refreshDiagram();
    }



    refreshDiagram() {
        if (!this.mermaidInitialized) return;

        // Check if render state has changed to avoid unnecessary re-renders
        const currentState = this.getCurrentRenderState();
        if (this.lastRenderState && this.statesEqual(this.lastRenderState, currentState)) {
            return; // No changes, skip re-render
        }

        const container = document.getElementById('mermaidContainer');
        if (!container) return;

        // Clear the container
        container.innerHTML = '';

        // Render the vertical gitgraph using Mermaid
        this.renderMermaidGitGraph();

        // Update last render state
        this.lastRenderState = currentState;
    }

    getCurrentRenderState() {
        const state = {
            flows: {},
            agents: {}
        };

        this.flows.forEach((flow, flowId) => {
            state.flows[flowId] = {
                status: flow.status,
                progress: flow.progress,
                agentCount: flow.agents?.length || 0
            };

            flow.agents?.forEach(agent => {
                state.agents[agent.id] = {
                    status: agent.status,
                    progress: agent.progress,
                    lifecycle_stage: agent.lifecycle_stage,
                    name: agent.name
                };
            });
        });

        return state;
    }

    statesEqual(state1, state2) {
        return JSON.stringify(state1) === JSON.stringify(state2);
    }

    async fetchAndUpdateFlows() {
        try {
            console.log('Fetching agent flows...');
            const response = await fetch('/agent_flow', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    action: 'get_active_flows'
                })
            });

            if (!response.ok) {
                console.error('HTTP error:', response.status, response.statusText);
                return;
            }

            const data = await response.json();
            console.log('Flow data received:', data);

            if (data.success && data.flows) {
                console.log(`Processing ${data.flows.length} flows`);
                data.flows.forEach(flow => {
                    this.updateFlow(flow);
                });
                this.refreshDiagram();
                this.updateProgressPanel();
            } else {
                console.log('No flows received or request failed:', data);
                this.refreshDiagram();
                this.updateProgressPanel();
            }
        } catch (error) {
            console.error('Error fetching agent flows:', error);
            this.refreshDiagram();
            this.updateProgressPanel();
        }
    }



    updateFlow(flowData) {
        const oldFlow = this.flows.get(flowData.id);
        this.flows.set(flowData.id, flowData);

        if (flowData.status === 'initializing' || flowData.status === 'running') {
            this.activeFlows.add(flowData.id);
        } else {
            this.activeFlows.delete(flowData.id);
        }

        // Track agent changes for dynamic updates
        this.trackAgentChanges(oldFlow, flowData);
    }

    trackAgentChanges(oldFlow, newFlow) {
        const oldAgents = oldFlow?.agents || [];
        const newAgents = newFlow?.agents || [];

        // Create maps for easier comparison
        const oldAgentMap = new Map(oldAgents.map(agent => [agent.id, agent]));
        const newAgentMap = new Map(newAgents.map(agent => [agent.id, agent]));

        // Detect new agents
        newAgents.forEach(agent => {
            if (!oldAgentMap.has(agent.id)) {
                this.onAgentCreated(agent);
            } else {
                // Check for status/progress changes
                const oldAgent = oldAgentMap.get(agent.id);
                if (this.hasAgentChanged(oldAgent, agent)) {
                    this.onAgentUpdated(oldAgent, agent);
                }
            }
        });

        // Detect removed agents (cleanup)
        oldAgents.forEach(agent => {
            if (!newAgentMap.has(agent.id)) {
                this.onAgentRemoved(agent);
            }
        });
    }

    hasAgentChanged(oldAgent, newAgent) {
        return oldAgent.status !== newAgent.status ||
               oldAgent.progress !== newAgent.progress ||
               oldAgent.lifecycle_stage !== newAgent.lifecycle_stage;
    }

    onAgentCreated(agent) {
        console.log(`Agent created: ${agent.name} (${agent.id})`);

        // Assign color to new agent
        if (!this.agentColors.has(agent.id)) {
            const color = this.availableColors[this.colorIndex % this.availableColors.length];
            this.agentColors.set(agent.id, color);
            this.colorIndex++;
        }

        // Create branch info
        const branchName = this.sanitizeBranchName(`${agent.name || agent.id}`);
        this.agentBranches.set(agent.id, {
            name: branchName,
            color: this.agentColors.get(agent.id),
            created: Date.now(),
            lastProgress: 0,
            status: agent.status
        });
    }

    onAgentUpdated(oldAgent, newAgent) {
        console.log(`Agent updated: ${newAgent.name} (${newAgent.id}) - ${oldAgent.status} -> ${newAgent.status}`);

        const branchInfo = this.agentBranches.get(newAgent.id);
        if (branchInfo) {
            branchInfo.status = newAgent.status;
            branchInfo.lastProgress = newAgent.progress || 0;
        }
    }

    onAgentRemoved(agent) {
        console.log(`Agent removed: ${agent.name} (${agent.id})`);

        // Clean up agent tracking
        this.agentBranches.delete(agent.id);
        this.agentColors.delete(agent.id);
    }

    renderMermaidGitGraph() {
        const mermaidCode = this.generateMermaidGitGraphTB();
        this.renderMermaidDiagram(mermaidCode);
    }

    generateMermaidGitGraphTB() {
        // Check if there are any flows
        if (this.flows.size === 0) {
            return `gitGraph TB:
    commit id: "🚀 System Ready"
    commit id: "📭 No Active Flows"
    commit id: "⏳ Waiting for tasks..."`;
        }

        let mermaidCode = 'gitGraph TB:\n';
        mermaidCode += '    commit id: "🚀 System Start"\n';

        // Track active branches for parallel processing
        const activeBranches = new Map(); // agent_id -> branch_name
        const branchColors = new Map(); // branch_name -> color
        const availableColors = ['c1', 'c2', 'c3', 'c4', 'c5', 'c6', 'c7'];
        let colorIndex = 0;

        // Process all flows
        Array.from(this.flows.values()).forEach((flow, flowIndex) => {
            const agents = flow.agents || [];

            // Organize agents by hierarchy
            const mainAgents = agents.filter(agent => !agent.parent_id && !agent.superior_id);
            const subordinateAgents = agents.filter(agent => agent.parent_id || agent.superior_id);

            // Flow initialization commit on main
            const flowDesc = flow.task_description?.substring(0, 25) || 'Task';
            mermaidCode += `    commit id: "📋 ${flowDesc}..."\n`;

            mainAgents.forEach((mainAgent, mainIndex) => {
                // Main agent commit on main branch
                const statusEmoji = this.getStatusEmoji(mainAgent.status);
                mermaidCode += `    commit id: "${statusEmoji} ${mainAgent.name || 'Main'}"\n`;

                // Process subordinate agents for parallel execution
                const subordinates = subordinateAgents.filter(sub =>
                    sub.parent_id === mainAgent.id || sub.superior_id === mainAgent.id
                );

                // Create branches for all subordinate agents first (parallel setup)
                subordinates.forEach((subAgent, subIndex) => {
                    const branchName = this.sanitizeBranchName(`${subAgent.name || subAgent.id}_${subIndex}`);
                    const color = availableColors[colorIndex % availableColors.length];
                    colorIndex++;

                    activeBranches.set(subAgent.id, branchName);
                    branchColors.set(branchName, color);

                    // Create branch with color
                    mermaidCode += `    branch ${branchName}\n`;
                    mermaidCode += `    checkout ${branchName}\n`;

                    // Initial commit for agent creation
                    const subStatusEmoji = this.getStatusEmoji(subAgent.status);
                    mermaidCode += `    commit id: "${subStatusEmoji} ${subAgent.name || 'Agent'} Created"\n`;

                    // Return to main after creating branch
                    mermaidCode += '    checkout main\n';
                });

                // Now process each agent's progress as parallel work
                subordinates.forEach((subAgent, subIndex) => {
                    const branchName = activeBranches.get(subAgent.id);
                    if (!branchName) return;

                    mermaidCode += `    checkout ${branchName}\n`;

                    // Add lifecycle stage if available
                    if (subAgent.lifecycle_stage) {
                        const lifecycleEmoji = this.getLifecycleEmoji(subAgent.lifecycle_stage);
                        mermaidCode += `    commit id: "${lifecycleEmoji} ${subAgent.lifecycle_stage}"\n`;
                    }

                    // Progress bar simulation - create commits based on progress
                    const progress = subAgent.progress || 0;
                    if (progress > 0) {
                        // Create progress commits in increments
                        const progressSteps = Math.floor(progress / 25); // Every 25%
                        for (let i = 1; i <= progressSteps; i++) {
                            const stepProgress = i * 25;
                            if (stepProgress <= progress) {
                                mermaidCode += `    commit id: "📊 ${stepProgress}%"\n`;
                            }
                        }

                        // Add final progress if not exactly on a 25% boundary
                        if (progress % 25 !== 0) {
                            mermaidCode += `    commit id: "📈 ${progress}%"\n`;
                        }
                    }

                    // Add status-specific commits
                    if (subAgent.status === 'running') {
                        mermaidCode += `    commit id: "⚡ Processing..."\n`;
                    } else if (subAgent.status === 'completed') {
                        mermaidCode += `    commit id: "✅ Task Complete"\n`;
                        // Merge completed agents back to main
                        mermaidCode += '    checkout main\n';
                        mermaidCode += `    merge ${branchName}\n`;
                    } else if (subAgent.status === 'failed') {
                        mermaidCode += `    commit id: "❌ Task Failed"\n`;
                        // Merge failed agents back to main to show the failure
                        mermaidCode += '    checkout main\n';
                        mermaidCode += `    merge ${branchName}\n`;
                    } else if (subAgent.status === 'initializing') {
                        mermaidCode += `    commit id: "🔄 Initializing..."\n`;
                    }
                });

                // Return to main branch for main agent status
                mermaidCode += '    checkout main\n';

                // Main agent progress/status commit
                if (mainAgent.progress > 0) {
                    mermaidCode += `    commit id: "📊 Main: ${mainAgent.progress}%"\n`;
                }

                // Main agent final status
                if (mainAgent.status === 'completed') {
                    mermaidCode += `    commit id: "🏁 Main Complete"\n`;
                } else if (mainAgent.status === 'running') {
                    mermaidCode += `    commit id: "🔄 Main Running"\n`;
                } else if (mainAgent.status === 'failed') {
                    mermaidCode += `    commit id: "💥 Main Failed"\n`;
                }
            });

            // Flow completion
            if (flow.status === 'completed') {
                mermaidCode += `    commit id: "🎯 Flow Complete"\n`;
            } else if (flow.status === 'running') {
                mermaidCode += `    commit id: "🔄 Flow Active"\n`;
            }
        });

        // Final status
        mermaidCode += '    commit id: "🔚 Current Status"\n';

        return mermaidCode;
    }

    generateVerticalFlowMermaid() {
        // Check if there are any flows
        if (this.flows.size === 0) {
            return `flowchart TD
    START["🚀 System Ready"]:::start
    EMPTY["📭 No Active Flows<br/>Waiting for agent tasks..."]:::idle
    START --> EMPTY

    classDef start fill:#e3f2fd,stroke:#1976d2,stroke-width:3px
    classDef idle fill:#f5f5f5,stroke:#757575,stroke-width:2px`;
        }

        let mermaidCode = 'flowchart TD\n';
        let nodeId = 0;
        const nodeMap = new Map();

        // Start node
        const startNodeId = `START`;
        mermaidCode += `    ${startNodeId}["🚀 System Start"]:::start\n`;
        let lastMainNode = startNodeId;

        // Process all flows to create vertical flow
        Array.from(this.flows.values()).forEach(flow => {
            const agents = flow.agents || [];

            // Organize agents by hierarchy
            const mainAgents = agents.filter(agent => !agent.parent_id && !agent.superior_id);
            const subordinateAgents = agents.filter(agent => agent.parent_id || agent.superior_id);

            mainAgents.forEach((mainAgent, mainIndex) => {
                // Create main agent node
                const mainNodeId = `M${nodeId++}`;
                nodeMap.set(mainAgent.id, mainNodeId);

                const mainProgressText = mainAgent.progress > 0 ? `<br/>📊 ${mainAgent.progress}%` : '';
                mermaidCode += `    ${mainNodeId}["${this.getStatusEmoji(mainAgent.status)} ${mainAgent.name}${mainProgressText}"]:::${this.getStatusColor(mainAgent.status)}\n`;

                // Connect to previous node (creating vertical flow)
                mermaidCode += `    ${lastMainNode} --> ${mainNodeId}\n`;

                // Create subordinate nodes for this main agent
                const subordinates = subordinateAgents.filter(sub =>
                    sub.parent_id === mainAgent.id || sub.superior_id === mainAgent.id
                );

                let lastSubNode = mainNodeId;
                subordinates.forEach((subAgent, subIndex) => {
                    const subNodeId = `S${nodeId++}`;
                    nodeMap.set(subAgent.id, subNodeId);

                    const subProgressText = subAgent.progress > 0 ? `<br/>📈 ${subAgent.progress}%` : '';
                    const lifecycleEmoji = this.getLifecycleEmoji(subAgent.lifecycle_stage);

                    mermaidCode += `    ${subNodeId}["${lifecycleEmoji} ${subAgent.name}${subProgressText}<br/>${this.getStatusEmoji(subAgent.status)} ${subAgent.status}"]:::${this.getStatusColor(subAgent.status)}\n`;

                    // Create vertical flow for subordinates
                    mermaidCode += `    ${lastSubNode} --> ${subNodeId}\n`;

                    // If completed, show cleanup status
                    if (subAgent.status === 'completed' && subAgent.lifecycle_stage === 'completed_cleanup_scheduled') {
                        const cleanupNodeId = `CLEANUP${nodeId++}`;
                        mermaidCode += `    ${cleanupNodeId}["🧹 Cleanup Scheduled<br/>⏰ 60s delay"]:::cleanup\n`;
                        mermaidCode += `    ${subNodeId} --> ${cleanupNodeId}\n`;
                        lastSubNode = cleanupNodeId;
                    } else if (subAgent.status === 'failed' && subAgent.lifecycle_stage === 'failed_cleanup_pending') {
                        const failCleanupNodeId = `FAILCLEANUP${nodeId++}`;
                        mermaidCode += `    ${failCleanupNodeId}["🚨 Failed - Cleanup Pending<br/>🧹 Scheduled"]:::failed_cleanup\n`;
                        mermaidCode += `    ${subNodeId} --> ${failCleanupNodeId}\n`;
                        lastSubNode = failCleanupNodeId;
                    } else {
                        lastSubNode = subNodeId;
                    }
                });

                // Update last main node for next iteration
                lastMainNode = lastSubNode;
            });
        });

        // End node
        const endNodeId = `END`;
        mermaidCode += `    ${endNodeId}["🔚 Flow Status"]:::endnode\n`;
        mermaidCode += `    ${lastMainNode} --> ${endNodeId}\n`;

        // Add CSS classes for all status types
        mermaidCode += '\n';
        mermaidCode += '    classDef start fill:#e3f2fd,stroke:#1976d2,stroke-width:3px\n';
        mermaidCode += '    classDef endnode fill:#f3e5f5,stroke:#7b1fa2,stroke-width:3px\n';
        mermaidCode += '    classDef cleanup fill:#fff3e0,stroke:#f57c00,stroke-width:2px\n';
        mermaidCode += '    classDef failed_cleanup fill:#ffebee,stroke:#d32f2f,stroke-width:2px\n';
        mermaidCode += '    classDef initializing fill:#f1f8e9,stroke:#689f38,stroke-width:2px\n';
        mermaidCode += '    classDef running fill:#e3f2fd,stroke:#1976d2,stroke-width:2px\n';
        mermaidCode += '    classDef completed fill:#e8f5e8,stroke:#388e3c,stroke-width:2px\n';
        mermaidCode += '    classDef failed fill:#ffebee,stroke:#d32f2f,stroke-width:2px\n';
        mermaidCode += '    classDef idle fill:#f5f5f5,stroke:#757575,stroke-width:2px\n';
        mermaidCode += '    classDef archived fill:#fafafa,stroke:#9e9e9e,stroke-width:1px\n';

        return mermaidCode;
    }

    generateProperGitGraph() {
        // Check if there are any flows
        if (this.flows.size === 0) {
            return `gitGraph
    commit id: "🚀 System Ready"
    commit id: "📭 No Active Flows"
    commit id: "⏳ Waiting for tasks..."`;
        }

        let mermaidCode = 'gitGraph\n';
        mermaidCode += '    commit id: "🚀 System Start"\n';

        // Process all flows
        Array.from(this.flows.values()).forEach((flow, flowIndex) => {
            const agents = flow.agents || [];

            // Organize agents by hierarchy
            const mainAgents = agents.filter(agent => !agent.parent_id && !agent.superior_id);
            const subordinateAgents = agents.filter(agent => agent.parent_id || agent.superior_id);

            // Flow initialization commit on main
            const flowDesc = flow.task_description?.substring(0, 25) || 'Task';
            mermaidCode += `    commit id: "📋 ${flowDesc}..."\n`;

            mainAgents.forEach((mainAgent, mainIndex) => {
                // Main agent commit on main branch
                const statusEmoji = this.getStatusEmoji(mainAgent.status);
                mermaidCode += `    commit id: "${statusEmoji} ${mainAgent.name || 'Main'}"\n`;

                // Process subordinate agents for this main agent
                const subordinates = subordinateAgents.filter(sub =>
                    sub.parent_id === mainAgent.id || sub.superior_id === mainAgent.id
                );

                subordinates.forEach((subAgent, subIndex) => {
                    // Create branch for subordinate
                    const branchName = this.sanitizeBranchName(`${subAgent.name || subAgent.id}_${subIndex}`);
                    mermaidCode += `    branch ${branchName}\n`;
                    mermaidCode += `    checkout ${branchName}\n`;

                    // Subordinate agent commits
                    const subStatusEmoji = this.getStatusEmoji(subAgent.status);
                    mermaidCode += `    commit id: "${subStatusEmoji} ${subAgent.name || 'Sub'}"\n`;

                    // Add lifecycle stage if available
                    if (subAgent.lifecycle_stage) {
                        const lifecycleEmoji = this.getLifecycleEmoji(subAgent.lifecycle_stage);
                        mermaidCode += `    commit id: "${lifecycleEmoji} ${subAgent.lifecycle_stage}"\n`;
                    }

                    // Add progress commit
                    if (subAgent.progress > 0) {
                        mermaidCode += `    commit id: "📈 ${subAgent.progress}%"\n`;
                    }

                    // Add status-specific commits
                    if (subAgent.status === 'running') {
                        mermaidCode += `    commit id: "⚡ Processing"\n`;
                    } else if (subAgent.status === 'completed') {
                        mermaidCode += `    commit id: "✅ Complete"\n`;
                    } else if (subAgent.status === 'failed') {
                        mermaidCode += `    commit id: "❌ Failed"\n`;
                    }

                    // Merge back to main
                    mermaidCode += '    checkout main\n';
                    mermaidCode += `    merge ${branchName}\n`;
                });

                // Main agent progress/status commit
                if (mainAgent.progress > 0) {
                    mermaidCode += `    commit id: "📊 ${mainAgent.progress}%"\n`;
                }

                // Main agent final status
                if (mainAgent.status === 'completed') {
                    mermaidCode += `    commit id: "🏁 Complete"\n`;
                } else if (mainAgent.status === 'running') {
                    mermaidCode += `    commit id: "🔄 Running"\n`;
                } else if (mainAgent.status === 'failed') {
                    mermaidCode += `    commit id: "💥 Failed"\n`;
                }
            });

            // Flow completion
            if (flow.status === 'completed') {
                mermaidCode += `    commit id: "🎯 Flow Done"\n`;
            } else if (flow.status === 'running') {
                mermaidCode += `    commit id: "🔄 Flow Active"\n`;
            }
        });

        // Final status
        mermaidCode += '    commit id: "🔚 Current"\n';

        return mermaidCode;
    }

    generateVerticalGitStyleFlowchart() {
        // Check if there are any flows
        if (this.flows.size === 0) {
            return `flowchart TD
    START["🚀 System Ready"]:::start
    EMPTY["📭 No Active Flows<br/>⏳ Waiting for tasks..."]:::idle
    START --> EMPTY

    classDef start fill:#e3f2fd,stroke:#1976d2,stroke-width:3px
    classDef idle fill:#f5f5f5,stroke:#757575,stroke-width:2px`;
        }

        let mermaidCode = 'flowchart TD\n';
        let nodeId = 0;

        // Start node
        const startNodeId = `START`;
        mermaidCode += `    ${startNodeId}["🚀 System Start"]:::start\n`;
        let lastMainNode = startNodeId;

        // Process all flows in a vertical git-style layout
        Array.from(this.flows.values()).forEach((flow, flowIndex) => {
            const agents = flow.agents || [];

            // Organize agents by hierarchy
            const mainAgents = agents.filter(agent => !agent.parent_id && !agent.superior_id);
            const subordinateAgents = agents.filter(agent => agent.parent_id || agent.superior_id);

            // Flow header node
            const flowNodeId = `FLOW${nodeId++}`;
            const flowDesc = flow.task_description?.substring(0, 40) || 'Task';
            mermaidCode += `    ${flowNodeId}["📋 Flow: ${flowDesc}..."]:::flow\n`;
            mermaidCode += `    ${lastMainNode} --> ${flowNodeId}\n`;
            lastMainNode = flowNodeId;

            mainAgents.forEach((mainAgent, mainIndex) => {
                // Main agent node
                const mainNodeId = `MAIN${nodeId++}`;
                const statusEmoji = this.getStatusEmoji(mainAgent.status);
                const progressText = mainAgent.progress > 0 ? `<br/>📊 ${mainAgent.progress}%` : '';
                mermaidCode += `    ${mainNodeId}["${statusEmoji} ${mainAgent.name || 'Main Agent'}${progressText}"]:::${this.getStatusColor(mainAgent.status)}\n`;
                mermaidCode += `    ${lastMainNode} --> ${mainNodeId}\n`;

                // Process subordinate agents
                const subordinates = subordinateAgents.filter(sub =>
                    sub.parent_id === mainAgent.id || sub.superior_id === mainAgent.id
                );

                let lastSubNode = mainNodeId;
                subordinates.forEach((subAgent, subIndex) => {
                    const subNodeId = `SUB${nodeId++}`;
                    const subStatusEmoji = this.getStatusEmoji(subAgent.status);
                    const subProgressText = subAgent.progress > 0 ? `<br/>📈 ${subAgent.progress}%` : '';
                    const lifecycleEmoji = subAgent.lifecycle_stage ? this.getLifecycleEmoji(subAgent.lifecycle_stage) : '';
                    const lifecycleText = subAgent.lifecycle_stage ? `<br/>${lifecycleEmoji} ${subAgent.lifecycle_stage}` : '';

                    mermaidCode += `    ${subNodeId}["${subStatusEmoji} ${subAgent.name || 'Sub Agent'}${subProgressText}${lifecycleText}"]:::${this.getStatusColor(subAgent.status)}\n`;
                    mermaidCode += `    ${lastSubNode} --> ${subNodeId}\n`;
                    lastSubNode = subNodeId;

                    // Add status-specific nodes
                    if (subAgent.status === 'running') {
                        const runningNodeId = `RUN${nodeId++}`;
                        mermaidCode += `    ${runningNodeId}["⚡ Processing..."]:::running\n`;
                        mermaidCode += `    ${subNodeId} --> ${runningNodeId}\n`;
                        lastSubNode = runningNodeId;
                    } else if (subAgent.status === 'completed') {
                        const completeNodeId = `COMP${nodeId++}`;
                        mermaidCode += `    ${completeNodeId}["✅ Task Complete"]:::completed\n`;
                        mermaidCode += `    ${subNodeId} --> ${completeNodeId}\n`;
                        lastSubNode = completeNodeId;
                    } else if (subAgent.status === 'failed') {
                        const failNodeId = `FAIL${nodeId++}`;
                        mermaidCode += `    ${failNodeId}["❌ Task Failed"]:::failed\n`;
                        mermaidCode += `    ${subNodeId} --> ${failNodeId}\n`;
                        lastSubNode = failNodeId;
                    }
                });

                // Main agent completion
                const mainCompleteNodeId = `MAINCOMP${nodeId++}`;
                if (mainAgent.status === 'completed') {
                    mermaidCode += `    ${mainCompleteNodeId}["🏁 ${mainAgent.name} Complete"]:::completed\n`;
                } else if (mainAgent.status === 'running') {
                    mermaidCode += `    ${mainCompleteNodeId}["🔄 In Progress"]:::running\n`;
                } else if (mainAgent.status === 'failed') {
                    mermaidCode += `    ${mainCompleteNodeId}["💥 Failed"]:::failed\n`;
                } else {
                    mermaidCode += `    ${mainCompleteNodeId}["⏸️ ${mainAgent.status}"]:::idle\n`;
                }
                mermaidCode += `    ${lastSubNode} --> ${mainCompleteNodeId}\n`;
                lastMainNode = mainCompleteNodeId;
            });

            // Flow completion
            const flowCompleteNodeId = `FLOWCOMP${nodeId++}`;
            if (flow.status === 'completed') {
                mermaidCode += `    ${flowCompleteNodeId}["🎯 Flow Complete"]:::completed\n`;
            } else if (flow.status === 'running') {
                mermaidCode += `    ${flowCompleteNodeId}["🔄 Flow Running"]:::running\n`;
            } else {
                mermaidCode += `    ${flowCompleteNodeId}["⏸️ Flow ${flow.status}"]:::idle\n`;
            }
            mermaidCode += `    ${lastMainNode} --> ${flowCompleteNodeId}\n`;
            lastMainNode = flowCompleteNodeId;
        });

        // Final status node
        const endNodeId = `END`;
        mermaidCode += `    ${endNodeId}["🔚 Current Status"]:::endnode\n`;
        mermaidCode += `    ${lastMainNode} --> ${endNodeId}\n`;

        // Add CSS classes for styling
        mermaidCode += '\n';
        mermaidCode += '    classDef start fill:#e3f2fd,stroke:#1976d2,stroke-width:3px\n';
        mermaidCode += '    classDef endnode fill:#f3e5f5,stroke:#7b1fa2,stroke-width:3px\n';
        mermaidCode += '    classDef flow fill:#fff3e0,stroke:#f57c00,stroke-width:2px\n';
        mermaidCode += '    classDef initializing fill:#f1f8e9,stroke:#689f38,stroke-width:2px\n';
        mermaidCode += '    classDef running fill:#e3f2fd,stroke:#1976d2,stroke-width:2px\n';
        mermaidCode += '    classDef completed fill:#e8f5e8,stroke:#388e3c,stroke-width:2px\n';
        mermaidCode += '    classDef failed fill:#ffebee,stroke:#d32f2f,stroke-width:2px\n';
        mermaidCode += '    classDef idle fill:#f5f5f5,stroke:#757575,stroke-width:2px\n';

        return mermaidCode;
    }

    generateFlowchartMermaid() {
        let mermaidCode = 'flowchart TD\n';
        let nodeId = 0;
        const nodeMap = new Map();

        // Start node
        const startNodeId = `START`;
        mermaidCode += `    ${startNodeId}["🚀 System Start"]:::start\n`;
        let lastMainNode = startNodeId;

        // Process all flows to create a vertical git-style flow
        Array.from(this.flows.values()).forEach(flow => {
            const agents = flow.agents || [];

            // Organize agents by hierarchy
            const mainAgents = agents.filter(agent => !agent.parent_id && !agent.superior_id);
            const subordinateAgents = agents.filter(agent => agent.parent_id || agent.superior_id);

            mainAgents.forEach((mainAgent, mainIndex) => {
                // Create main agent node
                const mainNodeId = `M${nodeId++}`;
                nodeMap.set(mainAgent.id, mainNodeId);

                const mainProgressText = mainAgent.progress > 0 ? `<br/>📊 ${mainAgent.progress}%` : '';
                mermaidCode += `    ${mainNodeId}["${this.getStatusEmoji(mainAgent.status)} ${mainAgent.name}${mainProgressText}"]:::${this.getStatusColor(mainAgent.status)}\n`;

                // Connect to previous node (creating vertical flow)
                mermaidCode += `    ${lastMainNode} --> ${mainNodeId}\n`;

                // Create subordinate nodes for this main agent
                const subordinates = subordinateAgents.filter(sub =>
                    sub.parent_id === mainAgent.id || sub.superior_id === mainAgent.id
                );

                let lastSubNode = mainNodeId;
                subordinates.forEach((subAgent, subIndex) => {
                    const subNodeId = `S${nodeId++}`;
                    nodeMap.set(subAgent.id, subNodeId);

                    const subProgressText = subAgent.progress > 0 ? `<br/>📈 ${subAgent.progress}%` : '';
                    mermaidCode += `    ${subNodeId}["${this.getStatusEmoji(subAgent.status)} ${subAgent.name}${subProgressText}"]:::${this.getStatusColor(subAgent.status)}\n`;

                    // Create vertical flow for subordinates
                    mermaidCode += `    ${lastSubNode} --> ${subNodeId}\n`;

                    // If completed, show merge back
                    if (subAgent.status === 'completed') {
                        const mergeNodeId = `MERGE${nodeId++}`;
                        mermaidCode += `    ${mergeNodeId}["✅ ${subAgent.name}<br/>Merged"]:::merged\n`;
                        mermaidCode += `    ${subNodeId} --> ${mergeNodeId}\n`;
                        lastSubNode = mergeNodeId;
                    } else {
                        lastSubNode = subNodeId;
                    }
                });

                // Update last main node for next iteration
                lastMainNode = lastSubNode;
            });
        });

        // End node
        const endNodeId = `END`;
        mermaidCode += `    ${endNodeId}["🔚 Flow Complete"]:::endnode\n`;
        mermaidCode += `    ${lastMainNode} --> ${endNodeId}\n`;

        // Add CSS classes for status colors and special nodes
        mermaidCode += '\n';
        mermaidCode += '    classDef start fill:#e0f2fe,stroke:#0277bd,stroke-width:3px\n';
        mermaidCode += '    classDef endnode fill:#f3e5f5,stroke:#7b1fa2,stroke-width:3px\n';
        mermaidCode += '    classDef merged fill:#e8f5e8,stroke:#2e7d32,stroke-width:2px\n';
        mermaidCode += '    classDef running fill:#dbeafe,stroke:#3b82f6,stroke-width:2px\n';
        mermaidCode += '    classDef completed fill:#dcfce7,stroke:#10b981,stroke-width:2px\n';
        mermaidCode += '    classDef failed fill:#fee2e2,stroke:#ef4444,stroke-width:2px\n';
        mermaidCode += '    classDef idle fill:#f3f4f6,stroke:#6b7280,stroke-width:2px\n';

        return mermaidCode;
    }

    async renderMermaidDiagram(mermaidCode) {
        const container = document.getElementById('mermaidContainer');
        if (!container || !window.mermaid) return;

        try {
            console.log('Rendering Mermaid diagram:', mermaidCode);

            // Create a unique ID for this diagram
            const diagramId = `mermaid-diagram-${Date.now()}`;

            // Create div for the diagram
            const diagramDiv = document.createElement('div');
            diagramDiv.id = diagramId;
            diagramDiv.className = 'mermaid-diagram';
            container.appendChild(diagramDiv);

            // Render the diagram
            const { svg } = await window.mermaid.render(diagramId + '-svg', mermaidCode);
            diagramDiv.innerHTML = svg;

            console.log('Mermaid diagram rendered successfully');
        } catch (error) {
            console.error('Error rendering Mermaid diagram:', error);
            container.innerHTML = `
                <div class="error-message">
                    <h4>Error rendering diagram</h4>
                    <p>${error.message}</p>
                    <details>
                        <summary>Mermaid Code</summary>
                        <pre>${mermaidCode}</pre>
                    </details>
                </div>
            `;
        }
    }

    sanitizeBranchName(name) {
        return name.replace(/[^a-zA-Z0-9]/g, '_').toLowerCase();
    }

    getStatusEmoji(status) {
        switch (status) {
            case 'initializing': return '🔄';
            case 'running': return '🏃';
            case 'completed': return '✅';
            case 'failed': return '❌';
            case 'idle': return '⏸️';
            case 'archived': return '📦';
            case 'cleanup': return '🧹';
            default: return '⚪';
        }
    }

    getLifecycleEmoji(stage) {
        switch (stage) {
            case 'spawning': return '🐣';
            case 'active': return '⚡';
            case 'completed_cleanup_scheduled': return '⏰';
            case 'failed_cleanup_pending': return '🚨';
            case 'archived': return '📦';
            default: return '🔄';
        }
    }

    getStatusColor(status) {
        switch (status) {
            case 'running': return 'running';
            case 'completed': return 'completed';
            case 'failed': return 'failed';
            case 'idle': return 'idle';
            default: return 'idle';
        }
    }

    updateProgressPanel() {
        const progressContent = document.getElementById('progressContent');
        if (!progressContent) return;

        progressContent.innerHTML = '';

        // Collect agent progress and status information
        const agentStats = {
            total: 0,
            running: 0,
            completed: 0,
            failed: 0,
            idle: 0
        };

        const flowStats = new Map();

        Array.from(this.flows.values()).forEach(flow => {
            const flowStat = {
                id: flow.id,
                description: flow.task_description || 'Unknown Task',
                status: flow.status,
                progress: flow.progress || 0,
                agents: flow.agents?.length || 0,
                completed: flow.completed_operations || 0,
                total: flow.total_operations || 0
            };
            flowStats.set(flow.id, flowStat);

            flow.agents?.forEach(agent => {
                agentStats.total++;
                switch (agent.status) {
                    case 'running': agentStats.running++; break;
                    case 'completed': agentStats.completed++; break;
                    case 'failed': agentStats.failed++; break;
                    default: agentStats.idle++; break;
                }
            });
        });

        // Create overall stats
        const overallStats = document.createElement('div');
        overallStats.className = 'progress-stats';
        overallStats.innerHTML = `
            <div class="stats-header">Overall Agent Status</div>
            <div class="stats-grid">
                <div class="stat-item">
                    <span class="stat-value">${agentStats.total}</span>
                    <span class="stat-label">Total</span>
                </div>
                <div class="stat-item running">
                    <span class="stat-value">${agentStats.running}</span>
                    <span class="stat-label">Running</span>
                </div>
                <div class="stat-item completed">
                    <span class="stat-value">${agentStats.completed}</span>
                    <span class="stat-label">Completed</span>
                </div>
                <div class="stat-item failed">
                    <span class="stat-value">${agentStats.failed}</span>
                    <span class="stat-label">Failed</span>
                </div>
            </div>
        `;
        progressContent.appendChild(overallStats);

        // Create flow progress items
        if (flowStats.size > 0) {
            const flowsHeader = document.createElement('div');
            flowsHeader.className = 'stats-header';
            flowsHeader.textContent = 'Active Flows';
            progressContent.appendChild(flowsHeader);

            flowStats.forEach((flowStat, flowId) => {
                const flowItem = document.createElement('div');
                flowItem.className = 'flow-progress-item';

                const progressPercent = flowStat.total > 0 ?
                    Math.round((flowStat.completed / flowStat.total) * 100) : 0;

                flowItem.innerHTML = `
                    <div class="flow-header">
                        <span class="flow-id">${flowId.substring(0, 8)}...</span>
                        <span class="flow-status status-${flowStat.status}">${flowStat.status}</span>
                    </div>
                    <div class="flow-description">${flowStat.description}</div>
                    <div class="flow-progress-bar">
                        <div class="progress-fill" style="width: ${progressPercent}%"></div>
                        <span class="progress-text">${flowStat.completed}/${flowStat.total} (${progressPercent}%)</span>
                    </div>
                    <div class="flow-agents-count">${flowStat.agents} agents</div>
                `;

                progressContent.appendChild(flowItem);
            });
        } else {
            const noFlows = document.createElement('div');
            noFlows.className = 'no-flows';
            noFlows.textContent = 'No active flows';
            progressContent.appendChild(noFlows);
        }
    }
}

// CSS styles for the Mermaid flow visualization
const mermaidStyles = `
<style>
.flow-graph-container {
    height: 100%;
    display: flex;
    flex-direction: column;
    background: var(--color-background);
}

.agent-flow-header {
    flex-shrink: 0;
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    border-bottom: 1px solid var(--color-border);
    background: var(--color-panel);
}

.agent-flow-header h3 {
    margin: 0;
    font-size: 14px;
    font-weight: 600;
    color: var(--color-text);
}

.flow-controls {
    display: flex;
    gap: 8px;
}

.flow-controls button {
    padding: 4px 8px;
    font-size: 12px;
    background: var(--color-background);
    border: 1px solid var(--color-border);
    border-radius: 4px;
    cursor: pointer;
    transition: background 0.2s;
    color: var(--color-text);
}

.flow-controls button:hover {
    background: var(--color-hover);
}

.mermaid-container {
    flex: 1;
    overflow: auto;
    padding: 16px;
    background: var(--color-background);
    min-height: 400px;
    display: flex;
    justify-content: center;
    align-items: flex-start;
    flex-direction: column;
}

.mermaid-diagram {
    max-width: 100%;
    height: auto;
}

.mermaid-diagram svg {
    max-width: 100%;
    height: auto;
}

.loading {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 200px;
    color: var(--color-text-secondary);
    font-size: 14px;
}

.error-message {
    padding: 20px;
    background: #fee2e2;
    border: 1px solid #ef4444;
    border-radius: 8px;
    color: #dc2626;
    max-width: 600px;
}

.error-message h4 {
    margin: 0 0 8px 0;
    color: #dc2626;
}

.error-message details {
    margin-top: 12px;
}

.error-message pre {
    background: #f3f4f6;
    padding: 8px;
    border-radius: 4px;
    font-size: 12px;
    overflow-x: auto;
    color: #374151;
}

.flow-legend {
    flex-shrink: 0;
    display: flex;
    gap: 12px;
    padding: 12px 16px;
    border-top: 1px solid var(--color-border);
    background: var(--color-panel);
    font-size: 11px;
    flex-wrap: wrap;
}

.legend-item {
    display: flex;
    align-items: center;
    gap: 6px;
}

.legend-color {
    width: 10px;
    height: 10px;
    border-radius: 50%;
}

.flow-progress-panel {
    flex-shrink: 0;
    padding: 12px 16px;
    border-top: 1px solid var(--color-border);
    background: var(--color-panel);
    max-height: 200px;
    overflow-y: auto;
}

.flow-progress-panel h4 {
    margin: 0 0 12px 0;
    font-size: 12px;
    font-weight: 600;
    color: var(--color-text);
}

.progress-stats {
    margin-bottom: 16px;
}

.stats-header {
    font-size: 11px;
    font-weight: 600;
    color: var(--color-text);
    margin-bottom: 8px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.stats-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 8px;
}

.stat-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 6px;
    background: var(--color-background);
    border-radius: 4px;
    border: 1px solid var(--color-border);
}

.stat-item.running {
    border-color: #3B82F6;
    background: rgba(59, 130, 246, 0.1);
}

.stat-item.completed {
    border-color: #10B981;
    background: rgba(16, 185, 129, 0.1);
}

.stat-item.failed {
    border-color: #EF4444;
    background: rgba(239, 68, 68, 0.1);
}

.stat-value {
    font-size: 14px;
    font-weight: 600;
    color: var(--color-text);
}

.stat-label {
    font-size: 10px;
    color: var(--color-text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.flow-progress-item {
    margin-bottom: 12px;
    padding: 8px;
    background: var(--color-background);
    border: 1px solid var(--color-border);
    border-radius: 4px;
}

.flow-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 4px;
}

.flow-id {
    font-family: monospace;
    font-size: 10px;
    color: var(--color-text-secondary);
}

.flow-status {
    font-size: 10px;
    padding: 2px 6px;
    border-radius: 10px;
    text-transform: uppercase;
    font-weight: 500;
}

.flow-status.status-running {
    background: rgba(59, 130, 246, 0.2);
    color: #3B82F6;
}

.flow-status.status-completed {
    background: rgba(16, 185, 129, 0.2);
    color: #10B981;
}

.flow-status.status-failed {
    background: rgba(239, 68, 68, 0.2);
    color: #EF4444;
}

.flow-description {
    font-size: 11px;
    color: var(--color-text);
    margin-bottom: 6px;
    line-height: 1.3;
}

.flow-progress-bar {
    position: relative;
    height: 12px;
    background: var(--color-border);
    border-radius: 6px;
    overflow: hidden;
    margin-bottom: 4px;
}

.progress-fill {
    height: 100%;
    background: linear-gradient(90deg, #10B981, #059669);
    transition: width 0.3s ease;
}

.progress-text {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    font-size: 9px;
    color: var(--color-text);
    font-weight: 500;
    text-shadow: 0 0 2px rgba(0,0,0,0.5);
}

.flow-agents-count {
    font-size: 10px;
    color: var(--color-text-secondary);
    text-align: right;
}

.no-flows {
    text-align: center;
    color: var(--color-text-secondary);
    font-size: 11px;
    padding: 16px;
}

/* Mermaid-specific styling */
.mermaid-container .mermaid {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

.mermaid-container .node rect,
.mermaid-container .node circle,
.mermaid-container .node ellipse,
.mermaid-container .node polygon {
    stroke-width: 2px;
}

.mermaid-container .edgePath .path {
    stroke-width: 2px;
}
</style>
`;

// Inject styles
document.head.insertAdjacentHTML('beforeend', mermaidStyles);

// Export for use
window.AgentMermaid = AgentMermaid;

} // End of duplicate prevention check
