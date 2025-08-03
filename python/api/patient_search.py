from typing import Dict, Any
from flask import Request
from python.helpers.api import ApiHandler, Input, Output
from python.helpers.clinical_api import ClinicalInboxAPI
from initialize import initialize_agent


class PatientSearch(ApiHandler):
    
    @classmethod
    def requires_auth(cls) -> bool:
        return True
    
    async def process(self, input: Input, request: Request) -> Output:
        query = input.get('query', '')
        source = input.get('source', 'generic')
        
        if not query:
            return {"success": False, "message": "Search query is required", "patients": []}
        
        # Initialize Clinical API
        config = initialize_agent()
        clinical_api = ClinicalInboxAPI(config)
        
        # Perform patient search
        result = await clinical_api.search_patients(query, source)
        
        return result