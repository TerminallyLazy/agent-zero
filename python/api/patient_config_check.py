from typing import Dict, Any
from flask import Request
from python.helpers.api import ApiHandler, Input, Output
from python.helpers.clinical_api import ClinicalInboxAPI
from initialize import initialize_agent


class PatientConfigCheck(ApiHandler):
    
    @classmethod
    def requires_auth(cls) -> bool:
        return True
    
    async def process(self, input: Input, request: Request) -> Output:
        # Initialize Clinical API
        config = initialize_agent()
        clinical_api = ClinicalInboxAPI(config)
        
        return {
            "success": True,
            "configured": bool(clinical_api.drchrono_config),
            "source": "drchrono" if clinical_api.drchrono_config else "none"
        }