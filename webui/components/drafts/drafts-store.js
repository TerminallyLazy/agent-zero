import { fetchApi, callJsonApi } from '/js/api.js';

export function createDraftsStore(){
  return {
    filter:'all',
    items:[],
    selected:null,
    draft:'',
    isLoading: false,
    error: null,

    get filtered(){ if(this.filter==='all') return this.items; return this.items.filter(i=>i.type===this.filter); },
    setFilter(f){ this.filter=f; },
    select(it){ this.selected=it; this.draft=it.draft||''; },
    close(){ this.selected=null; },

    async approveAndSend(){ 
      console.log('approveAndSend called', this.selected); // Debug
      if(!this.selected) {
        console.log('No selected item'); // Debug
        return; 
      }
      
      this.isLoading = true;
      this.error = null;
      
      try {
        console.log('Sending approve request...'); // Debug
        const response = await callJsonApi('/draft_approve_send', {
          draft_id: this.selected.id,
          patient_id: this.selected.patientId || this.selected.patient,
          content: this.draft,
          type: this.selected.type
        });
        
        console.log('Approve response:', response); // Debug
        
        if (response.success) {
          this.selected.status='sent';
          window.toast ? window.toast('Draft approved and sent', 'success', 3000) : alert('Approved & sent');
          this.removeSelected();
        } else {
          throw new Error(response.message || 'Failed to approve and send');
        }
      } catch (error) {
        console.error('Failed to approve and send:', error);
        this.error = error.message;
        window.toast ? window.toast('Failed to send draft', 'error', 3000) : alert('Failed to send');
      }
      
      this.isLoading = false;
    },
    
    async approveAndQueue(){ 
      if(!this.selected) return; 
      
      this.isLoading = true;
      this.error = null;
      
      try {
        const response = await callJsonApi('/draft_approve_queue', {
          draft_id: this.selected.id,
          patient_id: this.selected.patientId,
          content: this.draft,
          type: this.selected.type
        });
        
        if (response.success) {
          this.selected.status='queued';
          window.toast ? window.toast('Draft approved and queued', 'success', 3000) : alert('Approved & queued');
          this.removeSelected();
        } else {
          throw new Error(response.message || 'Failed to approve and queue');
        }
      } catch (error) {
        console.error('Failed to approve and queue:', error);
        this.error = error.message;
        window.toast ? window.toast('Failed to queue draft', 'error', 3000) : alert('Failed to queue');
      }
      
      this.isLoading = false;
    },
    
    async requestChanges(){ 
      if(!this.selected) return;
      
      this.isLoading = true;
      this.error = null;
      
      try {
        const response = await callJsonApi('/draft_request_changes', {
          draft_id: this.selected.id,
          feedback: prompt('What changes would you like to request?') || 'Please revise'
        });
        
        if (response.success) {
          this.selected.status = 'revision_requested';
          window.toast ? window.toast('Revision requested from agent', 'info', 3000) : alert('Requested changes from agent');
          this.close();
        } else {
          throw new Error(response.message || 'Failed to request changes');
        }
      } catch (error) {
        console.error('Failed to request changes:', error);
        this.error = error.message;
        window.toast ? window.toast('Failed to request changes', 'error', 3000) : alert('Failed to request changes');
      }
      
      this.isLoading = false;
    },
    
    removeSelected(){ 
      this.items = this.items.filter(i=>i!==this.selected); 
      this.selected=null; 
    },

    // Render Markdown to HTML (same as agent chat)
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

    async loadDrafts() {
      console.log('Loading drafts...'); // Debug
      this.isLoading = true;
      this.error = null;
      
      try {
        const response = await callJsonApi('/drafts_list', {});
        console.log('Drafts response:', response); // Debug
        
        if (response.success) {
          this.items = response.drafts || [];
          console.log('Loaded drafts:', this.items.length); // Debug
        } else {
          throw new Error(response.message || 'Failed to load drafts');
        }
      } catch (error) {
        console.error('Failed to load drafts:', error);
        this.error = error.message;
        // Fall back to some demo data so buttons can be tested
        this.items = [
          { 
            id:'d1', 
            type:'lab', 
            badge:'Lab', 
            badgeClass:'lab', 
            patient:'Mary Brown', 
            subject:'CMP Results', 
            agent:'Lab Notifier', 
            preview:'ALT mildly elevated...', 
            needsSignoff:true, 
            original:'CMP attachment shows ALT: 52 U/L (normal 7-40)', 
            summary:'Mild ALT elevation; likely benign but recommend follow-up', 
            draft:'Hi Mary, your CMP shows a mildly elevated ALT. Please schedule follow-up in 4-6 weeks to recheck.' 
          }
        ];
        console.log('Using demo data for testing'); // Debug
      }
      
      this.isLoading = false;
    },

    async init(){
      await this.loadDrafts();
    }
  }
}
