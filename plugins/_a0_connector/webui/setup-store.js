import { createStore } from '/js/AlpineStore.js';
import { getCsrfToken } from '/js/api.js';
import { openModal } from '/js/modals.js';
import { store as pluginSettings } from '/components/plugins/plugin-settings-store.js';

const endpoint = '/api/plugins/_a0_connector/v1/host_setup';
const receiptKey = 'a0.computer-setup.request.v1';

export async function setupRequest(action, payload = {}) {
  const controller = new AbortController();
  const timer = setTimeout(()=>controller.abort(),12000);
  try {
    // Use the shared CSRF source but never fetchApi's automatic 403 replay.
    const token = await getCsrfToken();
    const response = await fetch(endpoint,{method:'POST',redirect:'manual',credentials:'same-origin',
      headers:{'Content-Type':'application/json','X-CSRF-Token':token},
      body:JSON.stringify({...payload,action}),signal:controller.signal});
    if (!response.ok) throw new Error(response.status === 404
      ? 'Update Agent Zero for guided setup. You can still use Host access in Launcher.'
      : 'Setup could not be checked. Confirm that you are signed in and try Check again.');
    const reader = response.body.getReader();let size=0;const parts=[];
    try {
      for (;;) { const {done,value}=await reader.read();if(done)break;size+=value.byteLength;if(size>65536)throw new Error('Invalid setup response.');parts.push(value); }
    } finally { await reader.cancel().catch(()=>{}); }
    const bytes=new Uint8Array(size);let offset=0;for(const part of parts){bytes.set(part,offset);offset+=part.length;}
    const result=JSON.parse(new TextDecoder().decode(bytes));
    if(result.version!==1 || !/^[a-f0-9]{32}$/.test(result.server_id))throw new Error('Incompatible setup response.');
    return result;
  } finally { clearTimeout(timer); }
}

export const store = createStore('computerSetup', {
  snapshot:null, continuation:null, busy:false, stale:false, notice:'', browser:true, computer:false,
  active:false, generation:0, timer:null, pending:null, launcherTimer:null,
  async open() { await openModal('/plugins/_a0_connector/webui/setup.html'); },
  async start() {
    clearInterval(this.timer);this.busy=false;this.stale=false;
    this.active=true;this.generation++;this.snapshot=null;this.continuation=null;this.notice='';
    try { this.pending=JSON.parse(sessionStorage.getItem(receiptKey)||'null'); } catch { this.pending=null; }
    await this.refresh();
    if(this.active)this.timer=setInterval(()=>{if(!document.hidden)this.refresh();},5000);
  },
  stop() { this.active=false;this.generation++;clearInterval(this.timer);clearTimeout(this.launcherTimer);this.timer=null;this.snapshot=null;this.continuation=null; },
  openLauncher() {
    clearTimeout(this.launcherTimer);
    this.launcherTimer=setTimeout(()=> {
      if(this.active)this.notice='If Launcher did not open, install or update it, then open the same server and enter your setup code. You can always continue manually; opening the app grants no access.';
    },1800);
  },
  async refresh() {
    if(!this.active || this.busy || document.hidden)return;
    const generation=this.generation;this.busy=true;
    try {
      const result=await setupRequest('status');
      if(!this.active || generation!==this.generation)return;
      this.snapshot=result;this.stale=false;this.notice='';
      if(this.pending?.request_id && (!this.pending.server_id || this.pending.server_id===result.server_id)) {
        const continuation=await setupRequest('read',{request_id:this.pending.request_id});
        if(!this.active || generation!==this.generation)return;
        this.continuation=continuation;
        if(this.pending.action==='create' || (this.pending.action==='confirm' && continuation.state==='confirmed') || (this.pending.action==='cancel' && continuation.state==='cancelled')) {
          this.pending={request_id:continuation.request_id,server_id:continuation.server_id,action:'read'};
          sessionStorage.setItem(receiptKey,JSON.stringify(this.pending));
        }
      }
    } catch(error) { if(this.active && generation===this.generation){this.stale=true;this.notice=error.message;} }
    finally { if(generation===this.generation)this.busy=false; }
  },
  async change(action) {
    if(this.busy || this.stale || !this.snapshot)return;
    const generation=this.generation;
    const request_id=action==='create' ? crypto.randomUUID():this.continuation?.request_id;
    if(!request_id)return;
    this.busy=true;
    try {
      this.pending={request_id,server_id:this.snapshot.server_id,action};
      sessionStorage.setItem(receiptKey,JSON.stringify(this.pending));
      const payload={request_id};
      if(action==='create')payload.capabilities=[...(this.browser?['browser']:[]),...(this.computer?['computer_use']:[])];
      const result=await setupRequest(action,payload);
      if(!this.active || generation!==this.generation)return;
      this.continuation=result;this.pending.action='read';
      sessionStorage.setItem(receiptKey,JSON.stringify(this.pending));this.notice='';
    } catch(error) { if(generation===this.generation)this.notice='The setup request may have completed. Check again to read its status; it will not be sent again automatically.'; }
    finally { if(generation===this.generation)this.busy=false; }
  },
  async browserSettings() { await pluginSettings.openConfig('_browser'); },
  forget() { sessionStorage.removeItem(receiptKey);this.pending=null;this.continuation=null;this.stale=false;this.notice=''; },
  stateLabel(step) { return ({ready:'Prepared',checking:'Checking',action_here:'On this device',action_on_computer:'On your computer',unavailable:'Not available'})[step.state]||'Check again'; }
});
