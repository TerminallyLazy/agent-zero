export function createAgentsStore() {
  return {
    agents: [],
    tasks: [],
    selectedTask: null,
    logs: [],
    isLoading: false,
    showAddAgent: false,
    newAgent: {
      name: '',
      specialization: '',
      systemPrompt: ''
    },

    startAgent(id){ const a=this.agents.find(x=>x.id===id); if(a){ a.status='running'; a.lastRun=new Date().toISOString(); }},
    stopAgent(id){ const a=this.agents.find(x=>x.id===id); if(a){ a.status='idle'; }},

    createAgent() {
      console.log('createAgent() called!'); // Debug
      console.log('newAgent data:', this.newAgent); // Debug
      
      if (!this.newAgent.name || !this.newAgent.specialization || !this.newAgent.systemPrompt) {
        console.log('Validation failed - missing fields'); // Debug
        alert('Please fill in all fields');
        return;
      }

      const agent = {
        id: 'agent-' + Date.now(),
        name: this.newAgent.name,
        status: 'idle',
        assigned: [this.newAgent.specialization],
        specialization: this.newAgent.specialization,
        systemPrompt: this.newAgent.systemPrompt,
        lastRun: null,
        created: new Date().toISOString()
      };

      this.agents.push(agent);
      this.showAddAgent = false;
      this.resetNewAgent();
      
      // Show success message
      if (window.toast) {
        window.toast(`Agent "${agent.name}" created successfully!`, 'success', 3000);
      } else {
        alert(`Agent "${agent.name}" created successfully!`);
      }
    },

    resetNewAgent() {
      this.newAgent = {
        name: '',
        specialization: '',
        systemPrompt: ''
      };
    },

    deleteAgent(id) {
      if (confirm('Are you sure you want to delete this agent?')) {
        this.agents = this.agents.filter(a => a.id !== id);
      }
    },

    runTask(id){ const t=this.tasks.find(x=>x.id===id); if(!t) return; t.state='running'; setTimeout(()=>{ t.state='idle'; t.lastRun=new Date().toISOString(); this.logs.unshift(`[${new Date().toLocaleTimeString()}] Task ${t.name} completed`); }, 800); },
    openTask(id){ this.selectedTask = this.tasks.find(x=>x.id===id)||null; this.fetchLogs(); },
    closeTask(){ this.selectedTask=null; },

    fetchLogs(){ this.logs = [
      `[${new Date().toLocaleTimeString()}] Agent orchestrator booted`,
      `[${new Date().toLocaleTimeString()}] Scheduler tick`,
    ]; },

    get scheduled(){ return this.tasks.filter(t=>t.type==='scheduled'); },
    get adhoc(){ return this.tasks.filter(t=>t.type==='adhoc'); },
    get planned(){ return this.tasks.filter(t=>t.type==='planned'); },

    init(){
      console.log('Agents store init() called'); // Debug
      this.agents = [
        { id:'agent-lab', name:'Lab Notifier', status:'idle', assigned:['labs'], lastRun:null },
        { id:'agent-refill', name:'Refill Processor', status:'running', assigned:['refills'], lastRun:new Date().toISOString() },
        { id:'agent-appt', name:'Appointment Monitor', status:'idle', assigned:['appointments'], lastRun:null },
        { id:'agent-drafter', name:'Inbox Drafter', status:'idle', assigned:['patients','colleagues'], lastRun:null },
      ];
      console.log('Agents initialized:', this.agents.length); // Debug
      this.tasks = [
        { id:'t1', name:'Daily Lab Roundup', type:'scheduled', cron:'0 17 * * 1-5', state:'idle', lastRun:null },
        { id:'t2', name:'Appointment Sweep', type:'scheduled', cron:'*/15 * * * *', state:'running', lastRun:new Date().toISOString() },
        { id:'t3', name:'Summarize Conversation', type:'adhoc', state:'idle', lastRun:null },
        { id:'t4', name:'Batch Lab Callbacks', type:'planned', plan:['2025-08-03T18:00:00Z','2025-08-04T18:00:00Z'], state:'idle', lastRun:null },
      ];
    }
  }
}
