### healthcare_compliance

HIPAA compliance verification and healthcare data protection with comprehensive audit capabilities

**PHI Validation:**
- action: "validate_phi" - Scan data for Protected Health Information
- data: Healthcare data to validate for PHI compliance

**Audit Management:**
- action: "audit_log" - Create HIPAA-compliant audit log entry
- user_id: User performing the action
- patient_id: Patient whose data is accessed
- purpose: Purpose of access (treatment, payment, operations, etc.)
- data: Optional data access details

**Consent Verification:**
- action: "check_consent" - Verify patient consent for data use
- patient_id: Patient identifier
- purpose: Intended use of patient data

**Access Control:**
- action: "verify_access" - Verify user access permissions
- user_id: User requesting access
- patient_id: Target patient
- access_level: Required access level (read_only, limited_write, full_access, administrative)

**Compliance Reporting:**
- action: "generate_report" - Generate HIPAA compliance report
- start_date: Report start date (optional)
- end_date: Report end date (optional)

**Data Protection:**
- action: "mask_phi" - Mask PHI in data for safe display
- data: Data containing potential PHI to mask

**Risk Assessment:**
- action: "risk_assessment" - Conduct privacy risk assessment
- data: Data to assess for privacy risks

**Security Monitoring:**
- action: "breach_detection" - Detect potential HIPAA breach scenarios
- data: Access data to analyze
- user_id: User performing access

**Example usage**:
~~~json
{
    "thoughts": [
        "Validating patient data for PHI compliance",
        "Need to ensure all PHI is properly handled"
    ],
    "headline": "Validating PHI handling compliance",
    "tool_name": "healthcare_compliance",
    "tool_args": {
        "action": "validate_phi",
        "data": {
            "first_name": "John",
            "last_name": "Doe",
            "date_of_birth": "1990-01-15",
            "ssn": "123-45-6789"
        }
    }
}
~~~

**Audit logging example**:
~~~json
{
    "thoughts": [
        "Creating audit trail for patient data access",
        "Required for HIPAA compliance"
    ],
    "headline": "Logging patient data access for audit",
    "tool_name": "healthcare_compliance",
    "tool_args": {
        "action": "audit_log",
        "user_id": "doctor_smith",
        "patient_id": "12345",
        "purpose": "treatment"
    }
}
~~~

**Access verification example**:
~~~json
{
    "thoughts": [
        "Verifying user has permission to access patient data",
        "Following minimum necessary principle"
    ],
    "headline": "Verifying user access permissions",
    "tool_name": "healthcare_compliance",
    "tool_args": {
        "action": "verify_access",
        "user_id": "nurse_jones",
        "patient_id": "12345",
        "access_level": "read_only"
    }
}
~~~

Always implement proper access controls and maintain detailed audit trails for all PHI access.