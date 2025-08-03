from typing import Dict, Any
from flask import Request
from python.helpers.api import ApiHandler, Input, Output
from python.helpers.clinical_api import ClinicalInboxAPI
from initialize import initialize_agent


class PatientDetails(ApiHandler):
    
    @classmethod
    def requires_auth(cls) -> bool:
        return True
    
    async def process(self, input: Input, request: Request) -> Output:
        patient_id = input.get('patient_id', '')
        
        if not patient_id:
            return {"success": False, "message": "Patient ID is required"}
        
        # Initialize Clinical API
        config = initialize_agent()
        clinical_api = ClinicalInboxAPI(config)
        
        # Get patient details
        result = await clinical_api.get_patient_details(patient_id)
        
        return result