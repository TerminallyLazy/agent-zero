from typing import Dict, Any
from flask import Request
from python.helpers.api import ApiHandler, Input, Output
from python.helpers.clinical_api import ClinicalInboxAPI
from initialize import initialize_agent


class InboxGenerateDraft(ApiHandler):
    
    @classmethod
    def requires_auth(cls) -> bool:
        return True
    
    async def process(self, input: Input, request: Request) -> Output:
        item_id = input.get('item_id', '')
        agent_id = input.get('agent_id', 'inbox-drafter')
        item_type = input.get('item_type', 'patient')
        patient = input.get('patient', '')
        content = input.get('content', '')
        context = input.get('context', {})
        
        if not all([item_id, patient, content]):
            return {
                "success": False, 
                "message": "Missing required fields: item_id, patient, content"
            }
        
        # Initialize Clinical API
        config = initialize_agent()
        clinical_api = ClinicalInboxAPI(config)
        
        # Generate draft
        result = await clinical_api.generate_draft(
            item_id, agent_id, item_type, patient, content, context
        )
        
        return result