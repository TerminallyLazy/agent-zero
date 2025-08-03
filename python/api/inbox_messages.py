from typing import Dict, Any
from flask import Request
from python.helpers.api import ApiHandler, Input, Output
from python.helpers.clinical_api import ClinicalInboxAPI
from initialize import initialize_agent


class InboxMessages(ApiHandler):
    
    @classmethod
    def requires_auth(cls) -> bool:
        return True
    
    async def process(self, input: Input, request: Request) -> Output:
        filter_type = input.get('filter')
        limit = input.get('limit', 50)
        
        # Initialize Clinical API
        config = initialize_agent()
        clinical_api = ClinicalInboxAPI(config)
        
        # Get inbox messages
        result = await clinical_api.get_inbox_messages(filter_type, limit)
        
        return result