"""
Clinical Inbox API Integration
Handles integration between Agent Zero, DrChrono EMR, and Clinical Inbox UI
"""

import json
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import requests
from python.helpers.log import Log
from python.helpers.print_style import PrintStyle
from agent import Agent, AgentContext, UserMessage, AgentConfig

class ClinicalInboxAPI:
    """Handles Clinical Inbox API operations"""
    
    def __init__(self, config: AgentConfig):
        self.config = config
        self.drchrono_config = None
        self.session = requests.Session()
        
    def set_drchrono_config(self, config: Dict[str, Any]):
        """Configure DrChrono API settings"""
        self.drchrono_config = {
            'base_url': config.get('base_url', 'https://app.drchrono.com/api'),
            'access_token': config.get('access_token'),
            'refresh_token': config.get('refresh_token'),
            'client_id': config.get('client_id'),
            'client_secret': config.get('client_secret')
        }
        
        if self.drchrono_config.get('access_token'):
            self.session.headers.update({
                'Authorization': f"Bearer {self.drchrono_config['access_token']}",
                'Content-Type': 'application/json'
            })
            PrintStyle(font_color="green").print("DrChrono API configured successfully")
    
    # Patient Management
    async def search_patients(self, query: str, source: str = 'generic') -> Dict[str, Any]:
        """Search for patients across configured systems"""
        try:
            if source == 'drchrono' and self.drchrono_config:
                return await self._search_drchrono_patients(query)
            else:
                # Generic/mock patient search
                return {
                    'success': False,
                    'message': 'Patient database not configured. Please set up DrChrono integration.',
                    'patients': []
                }
        except Exception as e:
            PrintStyle(font_color="red").print(f"Patient search failed: {e}")
            return {'success': False, 'message': str(e), 'patients': []}
    
    async def _search_drchrono_patients(self, query: str) -> Dict[str, Any]:
        """Search DrChrono patients using proper API parameters"""
        try:
            url = f"{self.drchrono_config['base_url']}/patients"
            
            # Parse query to determine search type
            params = {'page_size': 20}
            
            # Try to parse the query for specific search types
            query = query.strip()
            if '@' in query:
                # Email search
                params['email'] = query
            elif query.replace('-', '').replace(' ', '').isdigit():
                # Could be chart_id or phone - try chart_id first
                params['chart_id'] = query
            elif len(query.split()) == 2:
                # Two words - likely first and last name
                parts = query.split()
                params['first_name'] = parts[0]
                params['last_name'] = parts[1]
            elif len(query.split()) == 1:
                # Single word - try as first name first, then last name
                params['first_name'] = query
            else:
                # Complex query - try as first name
                params['first_name'] = query
            
            response = self.session.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            patients = data.get('data', [])
            
            # If no results with first name, try as last name
            if not patients and 'first_name' in params and 'last_name' not in params:
                params = {'page_size': 20, 'last_name': query}
                response = self.session.get(url, params=params)
                if response.ok:
                    data = response.json()
                    patients = data.get('data', [])
            
            return {
                'success': True,
                'patients': patients,
                'total': len(patients)
            }
        except Exception as e:
            return {'success': False, 'message': f"DrChrono search failed: {e}", 'patients': []}
    
    async def get_patient_details(self, patient_id: str) -> Dict[str, Any]:
        """Get detailed patient information"""
        try:
            if self.drchrono_config:
                return await self._get_drchrono_patient_details(patient_id)
            else:
                return {'success': False, 'message': 'EMR not configured'}
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    async def _get_drchrono_patient_details(self, patient_id: str) -> Dict[str, Any]:
        """Get DrChrono patient details"""
        try:
            # Get patient basic info
            url = f"{self.drchrono_config['base_url']}/patients/{patient_id}"
            response = self.session.get(url)
            response.raise_for_status()
            patient = response.json()
            
            # Get additional data
            allergies = await self._get_patient_allergies(patient_id)
            medications = await self._get_patient_medications(patient_id)
            lab_results = await self._get_patient_lab_results(patient_id)
            
            patient.update({
                'allergies': allergies,
                'current_medications': medications,
                'lab_results': lab_results
            })
            
            return {'success': True, 'patient': patient}
        except Exception as e:
            return {'success': False, 'message': f"Failed to get patient details: {e}"}
    
    async def _get_patient_allergies(self, patient_id: str) -> List[str]:
        """Get patient allergies from DrChrono"""
        try:
            url = f"{self.drchrono_config['base_url']}/allergies"
            params = {'patient': patient_id}
            response = self.session.get(url, params=params)
            if response.ok:
                data = response.json()
                return [allergy.get('description', '') for allergy in data.get('data', [])]
        except:
            pass
        return []
    
    async def _get_patient_medications(self, patient_id: str) -> List[str]:
        """Get patient medications from DrChrono"""
        try:
            url = f"{self.drchrono_config['base_url']}/medications"
            params = {'patient': patient_id}
            response = self.session.get(url, params=params)
            if response.ok:
                data = response.json()
                return [med.get('name', '') for med in data.get('data', [])]
        except:
            pass
        return []
    
    async def _get_patient_lab_results(self, patient_id: str) -> List[Dict]:
        """Get patient lab results from DrChrono"""
        try:
            url = f"{self.drchrono_config['base_url']}/lab_results"
            params = {'patient': patient_id, 'page_size': 10}
            response = self.session.get(url, params=params)
            if response.ok:
                data = response.json()
                return data.get('data', [])
        except:
            pass
        return []
    
    # Inbox Management
    async def get_inbox_messages(self, filter_type: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
        """Get inbox messages from various sources"""
        try:
            messages = []
            
            # Get DrChrono messages if configured
            if self.drchrono_config:
                drchrono_messages = await self._get_drchrono_messages(filter_type, limit)
                messages.extend(drchrono_messages)
            
            # Get patient portal messages
            portal_messages = await self._get_portal_messages(filter_type, limit)
            messages.extend(portal_messages)
            
            # Sort by timestamp
            messages.sort(key=lambda x: x.get('created_at', ''), reverse=True)
            
            return {'success': True, 'messages': messages[:limit]}
        except Exception as e:
            return {'success': False, 'message': str(e), 'messages': []}
    
    async def _get_drchrono_messages(self, filter_type: Optional[str], limit: int) -> List[Dict]:
        """Get messages from DrChrono"""
        try:
            # Get patient messages
            url = f"{self.drchrono_config['base_url']}/patient_messages"
            params = {'page_size': limit}
            response = self.session.get(url, params=params)
            
            if response.ok:
                data = response.json()
                messages = []
                
                for msg in data.get('data', []):
                    messages.append({
                        'id': f"drchrono_{msg.get('id')}",
                        'subject': msg.get('subject', 'No subject'),
                        'content': msg.get('body', ''),
                        'patient': msg.get('patient_name', ''),
                        'patient_id': msg.get('patient'),
                        'type': 'patient',
                        'status': 'new',
                        'created_at': msg.get('created_at'),
                        'source': 'drchrono'
                    })
                
                return messages
        except Exception as e:
            PrintStyle(font_color="red").print(f"DrChrono messages failed: {e}")
        
        return []
    
    async def _get_portal_messages(self, filter_type: Optional[str], limit: int) -> List[Dict]:
        """Get messages from patient portal or other sources"""
        # Placeholder for additional message sources
        return []
    
    # Agent Integration
    async def create_specialized_context(self, agent_name: str, system_prompt: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """Create a new Agent Zero context for specialized clinical agent"""
        try:
            # Create new context with specialized prompt
            agent_context = AgentContext(
                config=self.config,
                name=f"{agent_name} - Clinical Inbox"
            )
            
            # Add system message with specialized prompt
            system_message = system_prompt
            if context and context.get('patient'):
                system_message += f"\\n\\nCurrent patient context: {context['patient']}"
            
            # Initialize with system message
            user_msg = UserMessage(message="", system_message=[system_message])
            agent_context.agent0.hist_add_user_message(user_msg)
            
            return {
                'success': True,
                'id': agent_context.id,
                'name': agent_context.name
            }
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    async def send_message_to_context(self, context_id: str, message: str, attachments: List[str] = None) -> Dict[str, Any]:
        """Send message to Agent Zero context"""
        try:
            context = AgentContext.get(context_id)
            if not context:
                return {'success': False, 'message': 'Context not found'}
            
            # Create user message
            user_msg = UserMessage(
                message=message,
                attachments=attachments or []
            )
            
            # Send to context
            task = context.communicate(user_msg)
            
            return {'success': True, 'task_id': context.id if task else None}
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    async def get_context_logs(self, context_id: str, after_log_index: int = 0, limit: int = 50) -> Dict[str, Any]:
        """Get logs from Agent Zero context"""
        try:
            context = AgentContext.get(context_id)
            if not context:
                return {'success': False, 'message': 'Context not found', 'logs': []}
            
            # Get logs after specified index
            all_logs = context.log.logs
            new_logs = [log for log in all_logs if (log.id or 0) > after_log_index]
            
            # Limit results
            limited_logs = new_logs[:limit]
            
            # Convert to serializable format
            serialized_logs = []
            for log_item in limited_logs:
                serialized_logs.append({
                    'id': log_item.id,
                    'type': log_item.type.value if hasattr(log_item.type, 'value') else str(log_item.type),
                    'heading': log_item.heading,
                    'content': log_item.content,
                    'timestamp': log_item.timestamp.isoformat() if log_item.timestamp else None,
                    'kvps': log_item.kvps
                })
            
            return {
                'success': True,
                'logs': serialized_logs,
                'is_running': context.task and context.task.is_alive() if context.task else False
            }
        except Exception as e:
            return {'success': False, 'message': str(e), 'logs': []}
    
    # Draft Generation
    async def generate_draft(self, item_id: str, agent_id: str, item_type: str, patient: str, content: str, context: Dict) -> Dict[str, Any]:
        """Generate draft response using specialized agent"""
        try:
            # Map agent ID to system prompt
            agent_prompts = {
                'lab-notifier': 'You are a specialized Lab Notifier agent. Analyze lab results and create patient-friendly explanations with clinical context.',
                'refill-processor': 'You are a Refill Processor agent. Handle medication refill requests with safety checks and clear instructions.',
                'appointment-monitor': 'You are an Appointment Monitor agent. Manage scheduling requests with efficiency and patient convenience in mind.',
                'inbox-drafter': 'You are an Inbox Drafter agent. Create empathetic, clear, and medically accurate patient communications.'
            }
            
            system_prompt = agent_prompts.get(agent_id, agent_prompts['inbox-drafter'])
            
            # Create context for this agent
            context_result = await self.create_specialized_context(agent_id, system_prompt, context)
            if not context_result['success']:
                return context_result
            
            # Prepare message for agent
            agent_message = f"""
Please help draft a response for this {item_type} message:

Patient: {patient}
Content: {content}

Additional Context:
- Medications: {context.get('medications', 'None listed')}
- Allergies: {context.get('allergies', 'None listed')}
- Next Appointment: {context.get('nextAppointment', 'None scheduled')}

Please create a professional, empathetic response that addresses the patient's needs while maintaining appropriate medical tone.
"""
            
            # Send message to agent
            send_result = await self.send_message_to_context(context_result['id'], agent_message)
            if not send_result['success']:
                return send_result
            
            # Wait for response (with timeout)
            max_wait = 30  # 30 seconds
            wait_time = 0
            
            while wait_time < max_wait:
                await asyncio.sleep(1)
                wait_time += 1
                
                logs_result = await self.get_context_logs(context_result['id'])
                if logs_result['success']:
                    # Look for agent response
                    for log in logs_result['logs']:
                        if log['type'] == 'response' and log['content']:
                            return {
                                'success': True,
                                'draft': log['content'],
                                'context_id': context_result['id']
                            }
                    
                    # Check if agent stopped running
                    if not logs_result.get('is_running', False):
                        break
            
            return {'success': False, 'message': 'Agent did not respond within timeout period'}
            
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    # Audit Logging
    async def log_audit_event(self, event_type: str, category: str, action: str, description: str, details: Dict = None) -> Dict[str, Any]:
        """Log audit event"""
        try:
            # Create audit log entry
            log_entry = {
                'id': f"audit_{int(datetime.now().timestamp() * 1000)}",
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'type': event_type,
                'category': category,
                'action': action,
                'description': description,
                'details': details or {},
                'user': 'Clinical User'  # TODO: Get from session
            }
            
            # Store in context logs for audit trail
            AgentContext.log_to_all(
                type=Log.Type.INFO,
                heading=f"Audit: {action}",
                content=description,
                kvps=details
            )
            
            return {'success': True, 'event_id': log_entry['id']}
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    # Health Check
    async def health_check(self) -> Dict[str, Any]:
        """Check system health"""
        return {
            'success': True,
            'status': 'healthy',
            'drchrono_configured': bool(self.drchrono_config),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }


# Global instance for API handlers
_clinical_api_instance = None

def get_clinical_api() -> ClinicalInboxAPI:
    """Get or create the global Clinical API instance"""
    global _clinical_api_instance
    if _clinical_api_instance is None:
        from initialize import initialize_agent
        config = initialize_agent()
        _clinical_api_instance = ClinicalInboxAPI(config)
    return _clinical_api_instance