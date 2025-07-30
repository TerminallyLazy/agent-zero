/**
 * AgentFlowGraph - Real GitGraph.js-based agent flow visualization
 * Uses the actual GitGraph.js library to visualize subordinate agents as git branches
 */

// Prevent duplicate class declarations
if (typeof window.AgentFlowGraph === 'undefined') {

class AgentFlowGraph {
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
    
    init() {
        console.log('AgentFlowGraph.init() called');
        console.log('Container:', this.container);
        console.log('Options:', this.options);

        if (!this.container) {
            console.error('Container not found!');
            return;
        }

        // Create SVG container
        this.container.innerHTML = `
            <div class="agent-flow-header">
                <h3>Agent Flow Visualization</h3>
                <div class="flow-controls">
                    <button id="pauseBtn" class="btn-sm">Pause</button>
                    <button id="clearBtn" class="btn-sm">Clear</button>
                </div>
            </div>
            <div class="flow-svg-container">
                <svg id="flowSvg" width="${this.options.width}">
                    <defs>
                        <marker id="arrowhead" markerWidth="10" markerHeight="7"
                                refX="9" refY="3.5" orient="auto">
                            <polygon points="0 0, 10 3.5, 0 7" fill="#666" />
                        </marker>
                    
                    <!-- Dynamic gradients will be added here as agents are discovered -->
                </defs>
                
                    <!-- Background grid -->
                    <pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse">
                        <path d="M 20 0 L 0 0 0 20" fill="none" stroke="#f0f0f0" stroke-width="1"/>
                    </pattern>
                    <rect width="100%" height="100%" fill="url(#grid)" opacity="0.3" />
                    
                    <!-- Main visualization groups -->
                    <g id="connections"></g>
                    <g id="agents"></g>
                    <g id="labels"></g>
                </svg>
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
        
        this.svg = document.getElementById('flowSvg');
        this.connectionsGroup = document.getElementById('connections');
        this.agentsGroup = document.getElementById('agents');
        this.labelsGroup = document.getElementById('labels');

        console.log('SVG elements:', {
            svg: this.svg,
            connectionsGroup: this.connectionsGroup,
            agentsGroup: this.agentsGroup,
            labelsGroup: this.labelsGroup
        });

        // Event listeners
        document.getElementById('pauseBtn').addEventListener('click', () => this.togglePause());
        document.getElementById('clearBtn').addEventListener('click', () => this.clearFlows());

        console.log('AgentFlowGraph initialization complete');

        // Start periodic updates
        this.startUpdates();
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
        this.render();
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

            console.log('Response status:', response.status);
            console.log('Response ok:', response.ok);

            if (!response.ok) {
                console.error('HTTP error:', response.status, response.statusText);
                return;
            }

            const data = await response.json();

            console.log('Flow data received:', data);

            if (data.success && data.flows) {
                console.log(`Processing ${data.flows.length} flows`);
                data.flows.forEach(flow => {
                    console.log('Processing flow:', flow.id, 'with', flow.agents?.length || 0, 'agents');
                    this.updateFlow(flow);
                });
                this.render();
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
        
        // Register any new agent types we encounter
        if (flowData.agents) {
            flowData.agents.forEach(agent => {
                this.registerAgentType(agent.type || agent.role || 'default');
            });
        }
    }
    
    registerAgentType(agentType) {
        if (!this.dynamicColors.has(agentType)) {
            const color = this.availableColors[this.colorIndex % this.availableColors.length];
            this.dynamicColors.set(agentType, color);
            this.colorIndex++;
            
            // Create dynamic gradient for this agent type
            this.createDynamicGradient(agentType, color);
            
            // Update legend
            this.updateLegend();
        }
    }
    
    createDynamicGradient(agentType, color) {
        const defs = this.svg.querySelector('defs');
        const gradientId = `${agentType}Grad`;
        
        // Remove existing gradient if it exists
        const existingGradient = defs.querySelector(`#${gradientId}`);
        if (existingGradient) {
            existingGradient.remove();
        }
        
        // Create new gradient
        const gradient = document.createElementNS('http://www.w3.org/2000/svg', 'linearGradient');
        gradient.setAttribute('id', gradientId);
        gradient.setAttribute('x1', '0%');
        gradient.setAttribute('y1', '0%');
        gradient.setAttribute('x2', '100%');
        gradient.setAttribute('y2', '100%');
        
        const stop1 = document.createElementNS('http://www.w3.org/2000/svg', 'stop');
        stop1.setAttribute('offset', '0%');
        stop1.setAttribute('style', `stop-color:${color};stop-opacity:1`);
        
        const stop2 = document.createElementNS('http://www.w3.org/2000/svg', 'stop');
        stop2.setAttribute('offset', '100%');
        stop2.setAttribute('style', `stop-color:${this.darkenColor(color)};stop-opacity:1`);
        
        gradient.appendChild(stop1);
        gradient.appendChild(stop2);
        defs.appendChild(gradient);
    }
    
    darkenColor(color) {
        // Simple color darkening
        const hex = color.replace('#', '');
        const r = Math.max(0, parseInt(hex.substr(0, 2), 16) - 30);
        const g = Math.max(0, parseInt(hex.substr(2, 2), 16) - 30);
        const b = Math.max(0, parseInt(hex.substr(4, 2), 16) - 30);
        return `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}`;
    }
    
    updateLegend() {
        const legendContainer = document.getElementById('flowLegend');
        legendContainer.innerHTML = '';
        
        // Only show legend items for agent types that are currently active
        const activeTypes = new Set();
        Array.from(this.flows.values()).forEach(flow => {
            if (flow.agents) {
                flow.agents.forEach(agent => {
                    activeTypes.add(agent.type || agent.role || 'default');
                });
            }
        });
        
        activeTypes.forEach(agentType => {
            const color = this.dynamicColors.get(agentType);
            if (color) {
                const legendItem = document.createElement('div');
                legendItem.className = 'legend-item';
                
                const colorDiv = document.createElement('div');
                colorDiv.className = 'legend-color';
                colorDiv.style.background = color;
                
                const label = document.createElement('span');
                label.textContent = this.formatAgentTypeName(agentType);
                
                legendItem.appendChild(colorDiv);
                legendItem.appendChild(label);
                legendContainer.appendChild(legendItem);
            }
        });
        
        // Hide legend if no active types
        legendContainer.style.display = activeTypes.size > 0 ? 'flex' : 'none';
    }
    
    formatAgentTypeName(agentType) {
        // Convert agent type to human-readable format
        return agentType
            .replace(/_/g, ' ')
            .replace(/([A-Z])/g, ' $1')
            .replace(/^./, str => str.toUpperCase())
            .trim();
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

    render() {
        // Clear existing elements
        this.connectionsGroup.innerHTML = '';
        this.agentsGroup.innerHTML = '';
        this.labelsGroup.innerHTML = '';
        
        let yOffset = 50;
        let maxHeight = 100;
        
        // Render each flow vertically
        Array.from(this.flows.values()).forEach(flow => {
            const flowHeight = this.renderFlow(flow, yOffset);
            yOffset += flowHeight + 80; // Space between flows
            maxHeight = Math.max(maxHeight, yOffset);
        });
        
        // Dynamically adjust SVG height
        this.svg.setAttribute('height', maxHeight + 50);
        
        // Update legend and progress panel after rendering
        this.updateLegend();
        this.updateProgressPanel();
    }
    
    renderFlow(flow, yOffset) {
        const agents = flow.agents || [];
        const connections = flow.connections || [];
        
        if (agents.length === 0) return 0;
        
        // Calculate positions for vertical GitGraph-style layout
        const positions = this.calculateVerticalPositions(agents, yOffset);
        
        // Render explicit connections first (so they appear behind nodes)
        connections.forEach(conn => {
            this.renderConnection(conn, positions);
        });

        // Render hierarchical connections (parent-subordinate relationships)
        agents.forEach(agent => {
            const agentPos = positions[agent.id];
            if (agentPos && agentPos.parent) {
                const parentPos = positions[agentPos.parent];
                if (parentPos) {
                    this.renderHierarchicalConnection(parentPos, agentPos, agent.status);
                }
            }
        });

        // Render agents
        agents.forEach((agent, index) => {
            this.renderAgent(agent, positions[agent.id], index);
        });
        
        // Render flow title
        this.renderFlowTitle(flow, yOffset - 30);
        
        // Return the height used by this flow
        const maxY = Math.max(...Object.values(positions).map(p => p.y));
        return maxY - yOffset + 50; // Add padding
    }
    
    calculateVerticalPositions(agents, yOffset) {
        const positions = {};

        // Build agent hierarchy for GitGraph-style layout
        const hierarchy = this.buildAgentHierarchy(agents);
        const branches = this.organizeBranchesByHierarchy(hierarchy);
        const totalBranches = Object.keys(branches).length;
        const branchWidth = Math.max(80, (this.options.width - 60) / Math.max(totalBranches, 1));

        let branchIndex = 0;
        let globalY = yOffset;

        Object.entries(branches).forEach(([branchName, branchData]) => {
            const baseX = 40 + (branchIndex * branchWidth);
            let branchY = globalY;

            // Position main agent first
            if (branchData.main) {
                positions[branchData.main.id] = {
                    x: baseX,
                    y: branchY,
                    branch: branchIndex,
                    branchName: branchName,
                    level: 0
                };
                branchY += this.options.commitSpacing;
            }

            // Position subordinate agents with slight horizontal offset
            branchData.subordinates.forEach((agent, subIndex) => {
                const subordinateOffset = 15; // Offset subordinates to show hierarchy
                const progressOffset = (agent.progress || 0) / 100 * 10;

                positions[agent.id] = {
                    x: baseX + subordinateOffset + progressOffset,
                    y: branchY + (subIndex * this.options.commitSpacing * 0.8),
                    branch: branchIndex,
                    branchName: branchName,
                    level: 1,
                    parent: branchData.main?.id
                };
            });

            // Update global Y for next branch
            const branchHeight = (branchData.subordinates.length + (branchData.main ? 1 : 0)) * this.options.commitSpacing;
            globalY = Math.max(globalY, yOffset + branchHeight);
            branchIndex++;
        });

        return positions;
    }
    
    buildAgentHierarchy(agents) {
        const hierarchy = {
            main: [],
            subordinates: new Map() // parent_id -> [subordinate_agents]
        };

        // Separate main agents from subordinates
        agents.forEach(agent => {
            if (agent.parent_id || agent.superior_id) {
                const parentId = agent.parent_id || agent.superior_id;
                if (!hierarchy.subordinates.has(parentId)) {
                    hierarchy.subordinates.set(parentId, []);
                }
                hierarchy.subordinates.get(parentId).push(agent);
            } else {
                hierarchy.main.push(agent);
            }
        });

        return hierarchy;
    }

    organizeBranchesByHierarchy(hierarchy) {
        const branches = {};

        // Create branches for each main agent and its subordinates
        hierarchy.main.forEach((mainAgent, index) => {
            const branchKey = mainAgent.type || mainAgent.role || `branch_${index}`;
            branches[branchKey] = {
                main: mainAgent,
                subordinates: hierarchy.subordinates.get(mainAgent.id) || []
            };
        });

        // Handle orphaned subordinates (subordinates without main agents in current flow)
        hierarchy.subordinates.forEach((subordinates, parentId) => {
            const parentExists = hierarchy.main.some(agent => agent.id === parentId);
            if (!parentExists) {
                const branchKey = `orphaned_${parentId.substring(0, 8)}`;
                branches[branchKey] = {
                    main: null,
                    subordinates: subordinates
                };
            }
        });

        // If no branches created, create a default branch
        if (Object.keys(branches).length === 0) {
            branches['default'] = {
                main: null,
                subordinates: hierarchy.main
            };
        }

        return branches;
    }
    
    renderAgent(agent, position, index) {
        // Create agent node group
        const agentGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        agentGroup.setAttribute('class', 'agent-node');
        agentGroup.setAttribute('transform', `translate(${position.x}, ${position.y})`);

        // Enhanced radius based on agent level (main vs subordinate)
        const isMainAgent = position.level === 0;
        const nodeRadius = isMainAgent ? this.options.nodeRadius + 3 : this.options.nodeRadius;

        // Main circle
        const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        circle.setAttribute('r', nodeRadius);
        circle.setAttribute('fill', this.getAgentGradient(agent.type));
        circle.setAttribute('stroke', '#fff');
        circle.setAttribute('stroke-width', '2');
        circle.setAttribute('class', `agent-${agent.status}`);

        // Add hierarchy indicator for subordinate agents
        if (position.level > 0) {
            const hierarchyIndicator = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
            hierarchyIndicator.setAttribute('r', '3');
            hierarchyIndicator.setAttribute('cx', nodeRadius - 3);
            hierarchyIndicator.setAttribute('cy', -nodeRadius + 3);
            hierarchyIndicator.setAttribute('fill', '#8B5CF6');
            hierarchyIndicator.setAttribute('stroke', '#fff');
            hierarchyIndicator.setAttribute('stroke-width', '1');
            hierarchyIndicator.setAttribute('class', 'hierarchy-indicator');
            agentGroup.appendChild(hierarchyIndicator);
        }
        
        // Progress ring
        if (agent.progress > 0) {
            const progressRing = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
            progressRing.setAttribute('r', this.options.nodeRadius + 3);
            progressRing.setAttribute('fill', 'none');
            progressRing.setAttribute('stroke', agent.color);
            progressRing.setAttribute('stroke-width', '2');
            progressRing.setAttribute('stroke-dasharray', `${2 * Math.PI * (this.options.nodeRadius + 3)}`);
            progressRing.setAttribute('stroke-dashoffset', 
                `${2 * Math.PI * (this.options.nodeRadius + 3) * (1 - agent.progress / 100)}`);
            progressRing.setAttribute('transform', 'rotate(-90)');
            agentGroup.appendChild(progressRing);
        }
        
        agentGroup.appendChild(circle);
        
        // Status indicator
        if (agent.status === 'running') {
            const pulse = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
            pulse.setAttribute('r', this.options.nodeRadius + 5);
            pulse.setAttribute('fill', 'none');
            pulse.setAttribute('stroke', agent.color);
            pulse.setAttribute('stroke-width', '1');
            pulse.setAttribute('opacity', '0.6');
            
            const pulseAnim = document.createElementNS('http://www.w3.org/2000/svg', 'animate');
            pulseAnim.setAttribute('attributeName', 'r');
            pulseAnim.setAttribute('values', `${this.options.nodeRadius + 5};${this.options.nodeRadius + 15};${this.options.nodeRadius + 5}`);
            pulseAnim.setAttribute('dur', '2s');
            pulseAnim.setAttribute('repeatCount', 'indefinite');
            
            pulse.appendChild(pulseAnim);
            agentGroup.appendChild(pulse);
        }
        
        // Agent label (positioned to the right of the node for vertical layout)
        const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        label.setAttribute('x', this.options.nodeRadius + 15);
        label.setAttribute('y', 5);
        label.setAttribute('text-anchor', 'start');
        label.setAttribute('class', 'agent-label');
        label.setAttribute('font-size', '11');
        label.setAttribute('fill', '#333');
        label.textContent = (agent.name || agent.role || 'Agent').substring(0, 20);
        
        agentGroup.appendChild(label);
        
        // Enhanced tooltip with Agent Card information
        const tooltip = document.createElementNS('http://www.w3.org/2000/svg', 'title');
        let tooltipText = `${agent.name || agent.role || 'Agent'}`;

        // Add protocol and version if available
        if (agent.protocol && agent.protocol !== 'local') {
            tooltipText += `\nProtocol: ${agent.protocol}`;
            if (agent.version) {
                tooltipText += ` v${agent.version}`;
            }
        }

        // Add description if available
        if (agent.description) {
            tooltipText += `\nDescription: ${agent.description}`;
        }

        // Add current task
        if (agent.current_task) {
            tooltipText += `\nCurrent Task: ${agent.current_task.substring(0, 100)}${agent.current_task.length > 100 ? '...' : ''}`;
        }

        // Add skills if available
        if (agent.skills && agent.skills.length > 0) {
            tooltipText += `\nSkills: ${agent.skills.slice(0, 3).map(skill => skill.name || skill.id).join(', ')}`;
            if (agent.skills.length > 3) {
                tooltipText += ` (+${agent.skills.length - 3} more)`;
            }
        }

        // Add endpoint if it's a remote agent
        if (agent.endpoint && agent.endpoint !== 'local') {
            tooltipText += `\nEndpoint: ${agent.endpoint}`;
        }

        tooltip.textContent = tooltipText;
        agentGroup.appendChild(tooltip);
        
        this.agentsGroup.appendChild(agentGroup);
        
        // Animate entrance
        agentGroup.style.opacity = '0';
        agentGroup.style.transform += ' scale(0.5)';
        
        setTimeout(() => {
            agentGroup.style.transition = 'all 0.5s ease-out';
            agentGroup.style.opacity = '1';
            agentGroup.style.transform = agentGroup.style.transform.replace('scale(0.5)', 'scale(1)');
        }, index * 100);
    }
    
    renderConnection(connection, positions) {
        const fromPos = positions[connection.from];
        const toPos = positions[connection.to];

        if (!fromPos || !toPos) return;

        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', fromPos.x);
        line.setAttribute('y1', fromPos.y);
        line.setAttribute('x2', toPos.x);
        line.setAttribute('y2', toPos.y);
        line.setAttribute('stroke', '#666');
        line.setAttribute('stroke-width', '2');
        line.setAttribute('marker-end', 'url(#arrowhead)');
        line.setAttribute('class', `connection-${connection.status}`);

        this.connectionsGroup.appendChild(line);
    }

    renderHierarchicalConnection(parentPos, childPos, childStatus) {
        // Create a curved connection to show hierarchy
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');

        // Calculate control points for a smooth curve
        const midX = (parentPos.x + childPos.x) / 2;
        const midY = (parentPos.y + childPos.y) / 2;
        const controlX = midX - 10; // Slight curve to the left

        const pathData = `M ${parentPos.x} ${parentPos.y} Q ${controlX} ${midY} ${childPos.x} ${childPos.y}`;

        path.setAttribute('d', pathData);
        path.setAttribute('stroke', this.getHierarchicalConnectionColor(childStatus));
        path.setAttribute('stroke-width', '1.5');
        path.setAttribute('fill', 'none');
        path.setAttribute('stroke-dasharray', '3,3');
        path.setAttribute('marker-end', 'url(#arrowhead)');
        path.setAttribute('class', `hierarchical-connection connection-${childStatus}`);
        path.setAttribute('opacity', '0.7');

        this.connectionsGroup.appendChild(path);
    }

    getHierarchicalConnectionColor(status) {
        switch (status) {
            case 'running': return '#3B82F6';
            case 'completed': return '#10B981';
            case 'failed': return '#EF4444';
            default: return '#6B7280';
        }
    }
    
    renderFlowTitle(flow, y) {
        const title = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        title.setAttribute('x', 10);
        title.setAttribute('y', y);
        title.setAttribute('font-size', '12');
        title.setAttribute('font-weight', 'bold');
        title.setAttribute('fill', '#333');
        
        // Wrap text to fit width
        const maxChars = Math.floor(this.options.width / 7);
        const description = flow.task_description.substring(0, maxChars);
        title.textContent = `${description}${description.length < flow.task_description.length ? '...' : ''} (${flow.progress}%)`;
        
        this.labelsGroup.appendChild(title);
        
        // Add branch lines for visual separation
        const separatorLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        separatorLine.setAttribute('x1', 10);
        separatorLine.setAttribute('y1', y + 10);
        separatorLine.setAttribute('x2', this.options.width - 10);
        separatorLine.setAttribute('y2', y + 10);
        separatorLine.setAttribute('stroke', '#e5e7eb');
        separatorLine.setAttribute('stroke-width', '1');
        
        this.labelsGroup.appendChild(separatorLine);
    }
    
    getAgentGradient(agentType) {
        // Ensure agent type is registered
        this.registerAgentType(agentType);
        
        // Return dynamic gradient or fallback color
        const gradientId = `${agentType}Grad`;
        const existingGradient = this.svg.querySelector(`#${gradientId}`);
        
        if (existingGradient) {
            return `url(#${gradientId})`;
        } else {
            // Fallback to solid color if gradient not available
            return this.dynamicColors.get(agentType) || '#6B7280';
        }
    }
}

// CSS styles for the flow graph
const flowGraphStyles = `
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

.flow-svg-container {
    flex: 1;
    overflow: auto;
    padding: 16px;
    background: var(--color-background);
}

.flow-svg-container svg {
    border: 1px solid var(--color-border);
    border-radius: 8px;
    background: var(--color-panel);
    display: block;
    min-height: 200px;
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

.agent-running circle {
    filter: drop-shadow(0 0 8px rgba(59, 130, 246, 0.5));
}

.agent-completed circle {
    filter: drop-shadow(0 0 4px rgba(34, 197, 94, 0.3));
}

.agent-failed circle {
    filter: drop-shadow(0 0 4px rgba(239, 68, 68, 0.5));
}

.connection-active {
    stroke-dasharray: 5,5;
    animation: dash 1s linear infinite;
}

@keyframes dash {
    to {
        stroke-dashoffset: -10;
    }
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
document.head.insertAdjacentHTML('beforeend', flowGraphStyles);

// Export for use
window.AgentFlowGraph = AgentFlowGraph;

} // End of duplicate prevention check