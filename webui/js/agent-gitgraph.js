/**
 * AgentGitGraph - Real GitGraph.js-based agent flow visualization
 * Uses the actual GitGraph.js library to visualize subordinate agents as git branches
 */

// Prevent duplicate class declarations
if (typeof window.AgentGitGraph === 'undefined') {

class AgentGitGraph {
    constructor(containerId, options = {}) {
        this.container = document.getElementById(containerId);
        this.containerId = containerId;
        this.options = {
            width: options.width || 320,
            height: options.height || 600,
            ...options
        };
        
        this.flows = new Map();
        this.activeFlows = new Set();
        this.gitgraph = null;
        this.branches = new Map(); // Track git branches for agents
        this.updateInterval = null;
        this.agentColors = new Map();
        this.colorIndex = 0;
        this.availableColors = [
            '#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6', 
            '#F97316', '#06B6D4', '#84CC16', '#EC4899', '#14B8A6',
            '#F43F5E', '#6366F1', '#059669', '#DC2626', '#7C3AED'
        ];
        
        this.init();
    }
    
    async init() {
        console.log('AgentGitGraph.init() called');
        console.log('Container:', this.container);

        if (!this.container) {
            console.error('Container not found!');
            return;
        }

        // Load GitGraph.js library if not already loaded
        await this.loadGitGraphLibrary();

        // Create container structure
        this.container.innerHTML = `
            <div class="agent-flow-header">
                <h3>Agent Flow Visualization (GitGraph.js)</h3>
                <div class="flow-controls">
                    <button id="pauseBtn" class="btn-sm">Pause</button>
                    <button id="clearBtn" class="btn-sm">Clear</button>
                    <button id="refreshBtn" class="btn-sm">Refresh</button>
                </div>
            </div>
            <div class="gitgraph-container" id="gitgraphContainer">
                <!-- GitGraph.js will render here -->
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

        // Initialize GitGraph
        this.initializeGitGraph();

        // Set up event handlers
        document.getElementById('pauseBtn').addEventListener('click', () => this.togglePause());
        document.getElementById('clearBtn').addEventListener('click', () => this.clearFlows());
        document.getElementById('refreshBtn').addEventListener('click', () => this.refreshGraph());

        // Start periodic updates
        this.startUpdates();
    }

    async loadGitGraphLibrary() {
        // Check if GitGraph is already loaded
        if (window.GitgraphJS) {
            console.log('GitGraph.js already loaded');
            return;
        }

        console.log('Loading GitGraph.js library...');
        
        return new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = 'https://unpkg.com/@gitgraph/js@1.4.0/lib/gitgraph.umd.js';
            script.onload = () => {
                console.log('GitGraph.js loaded successfully');
                resolve();
            };
            script.onerror = () => {
                console.error('Failed to load GitGraph.js');
                reject(new Error('Failed to load GitGraph.js'));
            };
            document.head.appendChild(script);
        });
    }

    initializeGitGraph() {
        const graphContainer = document.getElementById('gitgraphContainer');
        if (!graphContainer || !window.GitgraphJS) {
            console.error('GitGraph container or library not available');
            return;
        }

        try {
            // Create GitGraph instance with custom options
            this.gitgraph = window.GitgraphJS.createGitgraph(graphContainer, {
                orientation: 'vertical',
                template: window.GitgraphJS.templateExtend(window.GitgraphJS.TemplateName.Metro, {
                    colors: this.availableColors,
                    branch: {
                        lineWidth: 3,
                        spacing: 50,
                        label: {
                            font: 'normal 12px Arial',
                            color: '#374151'
                        }
                    },
                    commit: {
                        spacing: 60,
                        dot: {
                            size: 8
                        },
                        message: {
                            font: 'normal 11px Arial',
                            color: '#374151'
                        }
                    }
                }),
                mode: 'compact'
            });

            console.log('GitGraph initialized successfully');
        } catch (error) {
            console.error('Error initializing GitGraph:', error);
        }
    }

    startUpdates() {
        this.updateInterval = setInterval(() => {
            this.fetchAndUpdateFlows();
        }, 2000); // Update every 2 seconds
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
        this.branches.clear();
        this.refreshGraph();
    }

    refreshGraph() {
        if (this.gitgraph) {
            // Clear the container and reinitialize
            const graphContainer = document.getElementById('gitgraphContainer');
            if (graphContainer) {
                graphContainer.innerHTML = '';
                this.initializeGitGraph();
                this.renderFlowsAsGitGraph();
            }
        }
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
                this.renderFlowsAsGitGraph();
                this.updateProgressPanel();
            } else {
                console.log('No flows received or request failed:', data);
                // No test data fallback - show empty state
            }
        } catch (error) {
            console.error('Error fetching agent flows:', error);
            // No test data fallback - show empty state
        }
    }



    updateFlow(flowData) {
        this.flows.set(flowData.id, flowData);
        if (flowData.status === 'initializing' || flowData.status === 'running') {
            this.activeFlows.add(flowData.id);
        } else {
            this.activeFlows.delete(flowData.id);
        }
    }

    renderFlowsAsGitGraph() {
        if (!this.gitgraph) {
            console.error('GitGraph not initialized');
            return;
        }

        // Clear existing branches
        this.branches.clear();

        // Process all flows
        Array.from(this.flows.values()).forEach(flow => {
            this.renderFlowAsGitBranches(flow);
        });

        this.updateLegend();
    }

    renderFlowAsGitBranches(flow) {
        const agents = flow.agents || [];
        if (agents.length === 0) return;

        // Organize agents by hierarchy
        const mainAgents = agents.filter(agent => !agent.parent_id && !agent.superior_id);
        const subordinateAgents = agents.filter(agent => agent.parent_id || agent.superior_id);

        // Create main branches for each main agent
        mainAgents.forEach(mainAgent => {
            const branchName = this.sanitizeBranchName(mainAgent.name || mainAgent.id);

            if (!this.branches.has(branchName)) {
                const branch = this.gitgraph.branch({
                    name: branchName,
                    style: {
                        color: this.getAgentColor(mainAgent.type || mainAgent.role)
                    }
                });
                this.branches.set(branchName, branch);

                // Initial commit for main agent
                branch.commit({
                    subject: `${mainAgent.name} initialized`,
                    body: `Status: ${mainAgent.status}\nProgress: ${mainAgent.progress || 0}%`,
                    dotText: this.getStatusEmoji(mainAgent.status),
                    onMessageClick: (commit) => {
                        this.showAgentDetails(mainAgent);
                    }
                });

                // Add progress commits
                if (mainAgent.progress > 0) {
                    branch.commit({
                        subject: `Progress: ${mainAgent.progress}%`,
                        body: `Current task: ${mainAgent.current_task || 'Processing...'}`,
                        dotText: '⚡',
                        style: {
                            dot: {
                                color: this.getProgressColor(mainAgent.progress)
                            }
                        }
                    });
                }
            }

            // Create subordinate branches
            const subordinates = subordinateAgents.filter(sub =>
                sub.parent_id === mainAgent.id || sub.superior_id === mainAgent.id
            );

            subordinates.forEach(subAgent => {
                const subBranchName = this.sanitizeBranchName(`${subAgent.name || subAgent.id}-sub`);
                const mainBranch = this.branches.get(branchName);

                if (mainBranch && !this.branches.has(subBranchName)) {
                    const subBranch = this.gitgraph.branch({
                        name: subBranchName,
                        from: mainBranch,
                        style: {
                            color: this.getAgentColor(subAgent.type || subAgent.role)
                        }
                    });
                    this.branches.set(subBranchName, subBranch);

                    // Subordinate agent commits
                    subBranch.commit({
                        subject: `${subAgent.name} started`,
                        body: `Type: ${subAgent.type}\nStatus: ${subAgent.status}`,
                        dotText: this.getStatusEmoji(subAgent.status),
                        onMessageClick: (commit) => {
                            this.showAgentDetails(subAgent);
                        }
                    });

                    if (subAgent.progress > 0) {
                        subBranch.commit({
                            subject: `Progress: ${subAgent.progress}%`,
                            body: `Task: ${subAgent.current_task || 'Working...'}`,
                            dotText: '🔄',
                            style: {
                                dot: {
                                    color: this.getProgressColor(subAgent.progress)
                                }
                            }
                        });
                    }

                    // If subordinate is completed, merge back to main
                    if (subAgent.status === 'completed') {
                        mainBranch.merge({
                            branch: subBranch,
                            commitOptions: {
                                subject: `Completed: ${subAgent.name}`,
                                body: `Task completed successfully`,
                                dotText: '✅'
                            }
                        });
                    }
                }
            });
        });
    }

    sanitizeBranchName(name) {
        return name.replace(/[^a-zA-Z0-9-_]/g, '-').toLowerCase();
    }

    getAgentColor(type) {
        if (!this.agentColors.has(type)) {
            this.agentColors.set(type, this.availableColors[this.colorIndex % this.availableColors.length]);
            this.colorIndex++;
        }
        return this.agentColors.get(type);
    }

    getStatusEmoji(status) {
        switch (status) {
            case 'running': return '🏃';
            case 'completed': return '✅';
            case 'failed': return '❌';
            case 'idle': return '⏸️';
            default: return '⚪';
        }
    }

    getProgressColor(progress) {
        if (progress >= 100) return '#10B981'; // Green
        if (progress >= 75) return '#84CC16';  // Light green
        if (progress >= 50) return '#F59E0B';  // Orange
        if (progress >= 25) return '#EF4444';  // Red
        return '#6B7280'; // Gray
    }

    showAgentDetails(agent) {
        alert(`Agent: ${agent.name}\nType: ${agent.type}\nStatus: ${agent.status}\nProgress: ${agent.progress || 0}%`);
    }

    updateLegend() {
        const legendContainer = document.getElementById('flowLegend');
        if (!legendContainer) return;

        legendContainer.innerHTML = '';

        this.agentColors.forEach((color, type) => {
            const legendItem = document.createElement('div');
            legendItem.className = 'legend-item';
            legendItem.innerHTML = `
                <div class="legend-color" style="background-color: ${color}"></div>
                <span>${type.replace(/_/g, ' ')}</span>
            `;
            legendContainer.appendChild(legendItem);
        });
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

// CSS styles for the GitGraph flow visualization
const gitGraphStyles = `
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

.gitgraph-container {
    flex: 1;
    overflow: auto;
    padding: 16px;
    background: var(--color-background);
    min-height: 300px;
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
</style>
`;

// Inject styles
document.head.insertAdjacentHTML('beforeend', gitGraphStyles);

// Export for use
window.AgentGitGraph = AgentGitGraph;

} // End of duplicate prevention check
