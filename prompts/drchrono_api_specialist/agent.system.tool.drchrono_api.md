### drchrono_api

DrChrono API operations for complete EHR integration with HIPAA compliance

**Direct Endpoint Access:**
- endpoint: API endpoint path (e.g., "/api/patients", "/api/appointments")
- method: HTTP method (GET, POST, PUT, PATCH, DELETE)
- data: Request payload for POST/PUT/PATCH operations
- params: Query parameters for filtering/pagination

**High-Level Operations:**
- operation: Predefined operation name for common tasks
- patient_id: Patient identifier for patient-specific operations
- appointment_id: Appointment identifier 
- doctor_id: Provider identifier

**Available Operations:**
- list_patients: Get patient list with optional filtering
- get_patient: Retrieve specific patient by ID
- create_patient: Create new patient record
- update_patient: Update existing patient information
- search_patients: Search patients by name/phone/email
- get_patient_summary: Get patient summary data
- list_appointments: Get appointment list
- get_appointment: Retrieve specific appointment
- create_appointment: Schedule new appointment
- update_appointment: Modify existing appointment
- list_clinical_notes: Get clinical notes
- get_clinical_note: Retrieve specific note
- list_doctors: Get provider list
- get_doctor: Retrieve specific provider

**Example usage**:
~~~json
{
    "thoughts": [
        "Need to retrieve patient information for review",
        "Using get_patient operation with patient ID"
    ],
    "headline": "Retrieving patient data from DrChrono",
    "tool_name": "drchrono_api",
    "tool_args": {
        "operation": "get_patient",
        "patient_id": "12345"
    }
}
~~~

**Direct endpoint example**:
~~~json
{
    "thoughts": [
        "Creating custom API call to specific endpoint",
        "Using POST method with patient data"
    ],
    "headline": "Creating new patient via DrChrono API",
    "tool_name": "drchrono_api",
    "tool_args": {
        "endpoint": "/api/patients",
        "method": "POST",
        "data": {
            "first_name": "John",
            "last_name": "Doe",
            "date_of_birth": "1990-01-15",
            "gender": "male"
        }
    }
}
~~~

Always ensure HIPAA compliance and proper authentication before accessing patient data.