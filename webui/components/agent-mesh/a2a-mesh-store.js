import { createStore } from "/js/AlpineStore.js";
import * as API from "/js/api.js";

const model = {
  agents: {},
  tasks: {},
  provenance: {},
  selectedTask: null,
  newGoal: "",
  loading: false,

  init() {
    this.initialize();
    // Poll for updates every 2 seconds for real-time feel
    setInterval(() => {
      this.updateAgents();
    }, 2000);
  },

  // Initialize the agent mesh store
  initialize() {
    console.log("[A2A Store] Initializing...");
    this.loading = true;
    this.agents = {};
    this.tasks = {};
    this.provenance = {};
    this.selectedTask = null;
    this.newGoal = "";
    // Add a small delay to ensure DOM is ready
    setTimeout(() => {
      this.updateAgents();
    }, 100);
  },

  // Update active agents from registry
  async updateAgents() {
    try {
      console.log("[A2A Store] Updating agents from registry...");
      
      // Fetch registered agents from the backend (using match endpoint temporarily)
      const response = await API.callJsonApi("a2a_registry_match", {});
      
      if (response.status === "success" && response.matches) {
        console.log("[A2A Store] Received agents from registry:", response.matches.length);
        
        // Convert matches format to agents format
        this.agents = {};
        for (const match of response.matches) {
          const card = match.agent_card;
          if (card && card.agent_id) {
            this.agents[card.agent_id] = {
              card: card,
              lastSeen: new Date().toISOString(),
              score: {}
            };
          }
        }
      } else {
        console.error("[A2A Store] Failed to fetch agents:", response);
        // Fallback to local agent
        this.agents = {
          "agent-zero-local": {
            card: {
              agent_id: "agent-zero-local",
              role_description: "Agent Zero - AI Assistant",
              trust_level: "local",
              version: "1.0",
              tools: ["code_execution", "web_search", "file_management"]
            },
            lastSeen: new Date().toISOString(),
            score: {}
          }
        };
      }
      
      console.log("[A2A Store] Agents updated:", Object.keys(this.agents).length, "agents");
      
      // Also update tasks
      await this.updateTasks();
      this.loading = false;
    } catch (error) {
      console.error("[A2A Store] Failed to update agents:", error);
      // Still show local agent on error
      this.agents = {
        "agent-zero-local": {
          card: {
            agent_id: "agent-zero-local",
            role_description: "Agent Zero - AI Assistant",
            trust_level: "local",
            version: "1.0",
            tools: ["code_execution", "web_search", "file_management"]
          },
          lastSeen: new Date().toISOString(),
          score: {}
        }
      };
      this.loading = false;
    }
  },

  // Update active tasks (simplified for FastA2A)
  async updateTasks() {
    try {
      // FastA2A manages tasks internally, we just maintain our local state
      // Tasks are added via executeTask() and updated via polling if needed
      console.log(`Current tasks: ${Object.keys(this.tasks).length}`);
    } catch (error) {
      console.error("Failed to update tasks:", error);
    }
  },

  // Register a new task
  registerTask(task) {
    this.tasks[task.task_id] = task;
  },

  // Update task state
  updateTaskState(taskId, updates) {
    if (this.tasks[taskId]) {
      Object.assign(this.tasks[taskId], updates);
    }
  },

  // Generate UUID for tasks
  generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
      const r = Math.random() * 16 | 0;
      const v = c == 'x' ? r : (r & 0x3 | 0x8);
      return v.toString(16);
    });
  },

  // Match agents for a goal
  async matchAgents(goal) {
    try {
      const response = await API.callJsonApi("a2a_registry_match", { goal });
      if (response.status === "success") {
        return response.matches;
      }
      return [];
    } catch (error) {
      console.error("Failed to match agents:", error);
      return [];
    }
  },

  // Propose a task
  async proposeTask(envelope) {
    try {
      const response = await API.callJsonApi("a2a_task_propose", envelope);
      if (response.status === "proposed") {
        this.registerTask(response.task);
        return response.task;
      }
      return null;
    } catch (error) {
      console.error("Failed to propose task:", error);
      return null;
    }
  },

  // Update task
  async updateTask(taskId, updates) {
    try {
      const response = await API.callJsonApi("a2a_task_update", updates, {
        path_params: { task_id: taskId }
      });
      if (response.status === "updated") {
        this.updateTaskState(taskId, updates);
        return response.task;
      }
      return null;
    } catch (error) {
      console.error("Failed to update task:", error);
      return null;
    }
  },

  // Get provenance trace
  async getProvenance(taskId) {
    try {
      const response = await API.callJsonApi("a2a_task_provenance", {}, {
        path_params: { task_id: taskId }
      });
      if (response.status === "success") {
        return response.trace;
      }
      return "No provenance data available";
    } catch (error) {
      console.error("Failed to get provenance:", error);
      return "Error loading provenance";
    }
  },

  // Format timestamp for display
  formatTimestamp(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);

    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    
    return date.toLocaleDateString();
  },

  // Get task by ID
  getTask(taskId) {
    return this.tasks[taskId];
  },

  // Get agent by ID
  getAgent(agentId) {
    return this.agents[agentId];
  },

  // Execute a task through Agent Zero directly
  async executeTask(goal) {
    try {
      // Use the direct Agent Zero execution endpoint
      const result = await API.callJsonApi('a2a_task_execute', { 
        goal: goal
      });
      
      if (result && result.status === 'started' && result.task) {
        const task = result.task;
        this.registerTask(task);
        await this.updateAgents();
        
        // Start polling for task status
        this.pollTaskStatus(task.task_id);
        
        return task;
      } else {
        console.error('Failed to start task:', result);
        return null;
      }
    } catch (error) {
      console.error('Error executing task:', error);
      return null;
    }
  },
  
  // Poll for task status updates
  async pollTaskStatus(taskId) {
    const pollInterval = setInterval(async () => {
      try {
        const response = await API.callJsonApi('a2a_task_status', { task_id: taskId });
        if (response.status === 'success' && response.task) {
          console.log(`[A2A Store] Task ${taskId} status:`, response.task.state);
          this.updateTaskState(taskId, response.task);
          
          // Stop polling if task is completed or failed
          if (response.task.state === 'completed' || response.task.state === 'failed' || response.task.state === 'timeout') {
            console.log(`[A2A Store] Stopping poll for task ${taskId} - final state: ${response.task.state}`);
            clearInterval(pollInterval);
          }
        }
      } catch (error) {
        console.error('Error polling task status:', error);
        // Stop polling on repeated errors
        clearInterval(pollInterval);
      }
    }, 500); // Poll every 0.5 seconds for even faster updates
    
    // Stop polling after 45 seconds to match the reduced timeout
    setTimeout(() => {
      console.log(`[A2A Store] Timeout - stopping poll for task ${taskId}`);
      clearInterval(pollInterval);
    }, 45000);
  },

  // Clear all data
  clear() {
    this.agents = {};
    this.tasks = {};
    this.provenance = {};
    this.selectedTask = null;
    this.newGoal = "";
  },

  // Execute multiple tasks in parallel
  async executeBatchTasks(goals) {
    try {
      const result = await API.callJsonApi('a2a_task_execute_batch', { 
        goals: goals
      });
      
      if (result && result.status === 'started' && result.tasks) {
        // Register all tasks
        for (const task of result.tasks) {
          this.registerTask(task);
        }
        
        // Start polling for all task statuses
        for (const task_id of result.task_ids) {
          this.pollTaskStatus(task_id);
        }
        
        await this.updateAgents();
        return result.tasks;
      } else {
        console.error('Failed to start batch tasks:', result);
        return null;
      }
    } catch (error) {
      console.error('Error executing batch tasks:', error);
      return null;
    }
  },
  
  // Clear the registry
  async clearRegistry() {
    try {
      const result = await API.callJsonApi('a2a_registry_clear', {});
      if (result.status === 'success') {
        // Clear local data
        this.clear();
        // Refresh to get updated state
        await this.updateAgents();
        console.log('Registry cleared successfully');
      } else {
        console.error('Failed to clear registry:', result.error);
      }
    } catch (error) {
      console.error('Error clearing registry:', error);
    }
  }
};

// Create and export the store
const store = createStore("agentMeshStore", model);
export { store };