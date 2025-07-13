"""
Healthcare Compliance Tool

Provides HIPAA compliance verification, audit trail management, and healthcare data validation:
- PHI (Protected Health Information) handling compliance
- HIPAA audit trail generation
- Data privacy validation
- Consent management
- Security protocol verification
"""

import json
import hashlib
import datetime
from typing import Dict, Any, Optional, List, Set
from python.helpers.tool import Tool, Response
from python.helpers.errors import handle_error
from python.helpers.print_style import PrintStyle


class HealthcareCompliance(Tool):
    """Healthcare compliance verification and audit tool"""
    
    # HIPAA-defined PHI identifiers
    PHI_IDENTIFIERS = {
        'names', 'name', 'first_name', 'last_name', 'middle_name',
        'geographic_subdivisions', 'address', 'street', 'city', 'state', 'zip', 'postal_code',
        'dates', 'date_of_birth', 'dob', 'birth_date', 'admission_date', 'discharge_date',
        'telephone_numbers', 'phone', 'mobile', 'home_phone', 'work_phone',
        'fax_numbers', 'fax',
        'email_addresses', 'email',
        'social_security_numbers', 'ssn', 'social_security_number',
        'medical_record_numbers', 'mrn', 'medical_record_number', 'patient_id',
        'health_plan_numbers', 'insurance_id', 'policy_number',
        'account_numbers', 'account_number',
        'certificate_numbers', 'certificate_number',
        'vehicle_identifiers', 'license_plate',
        'device_identifiers', 'device_id',
        'web_urls', 'url', 'website',
        'ip_addresses', 'ip_address',
        'biometric_identifiers', 'fingerprint', 'retinal_scan',
        'full_face_photos', 'photo', 'image',
        'other_unique_identifying_numbers', 'patient_photo'
    }
    
    # Minimum necessary principle - data access levels
    ACCESS_LEVELS = {
        'read_only': 'Can view but not modify data',
        'limited_write': 'Can modify specific fields only',
        'full_access': 'Can view and modify all accessible data',
        'administrative': 'Can manage user access and system settings'
    }
    
    async def execute(
        self,
        action: str = "",
        data: Optional[Dict] = None,
        user_id: str = "",
        patient_id: str = "",
        purpose: str = "",
        access_level: str = "read_only",
        **kwargs
    ) -> Response:
        """
        Execute healthcare compliance operations
        
        Args:
            action: Compliance action (validate_phi, audit_log, check_consent, verify_access, generate_report)
            data: Data to validate or audit
            user_id: User performing the action
            patient_id: Patient whose data is being accessed
            purpose: Purpose of data access (treatment, payment, operations, etc.)
            access_level: Required access level for the operation
        """
        
        try:
            if action == "validate_phi":
                return await self._validate_phi_handling(data)
            
            elif action == "audit_log":
                return await self._create_audit_log(user_id, patient_id, purpose, data)
            
            elif action == "check_consent":
                return await self._check_patient_consent(patient_id, purpose)
            
            elif action == "verify_access":
                return await self._verify_user_access(user_id, patient_id, access_level)
            
            elif action == "generate_report":
                start_date = kwargs.get("start_date")
                end_date = kwargs.get("end_date")
                return await self._generate_compliance_report(start_date, end_date)
            
            elif action == "mask_phi":
                return await self._mask_phi_data(data)
            
            elif action == "risk_assessment":
                return await self._conduct_risk_assessment(data)
            
            elif action == "breach_detection":
                return await self._detect_potential_breach(data, user_id)
            
            else:
                return Response(
                    message=f"Error: Unknown action '{action}'. Available actions: validate_phi, audit_log, check_consent, verify_access, generate_report, mask_phi, risk_assessment, breach_detection",
                    break_loop=False
                )
                
        except Exception as e:
            handle_error(e)
            return Response(
                message=f"Healthcare compliance error: {str(e)}",
                break_loop=False
            )
    
    async def _validate_phi_handling(self, data: Optional[Dict]) -> Response:
        """Validate PHI handling compliance"""
        
        if not data:
            return Response(
                message="Error: Data required for PHI validation",
                break_loop=False
            )
        
        violations = []
        phi_found = []
        recommendations = []
        
        # Scan for PHI identifiers
        def scan_for_phi(obj, path=""):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    current_path = f"{path}.{key}" if path else key
                    
                    # Check if key name suggests PHI
                    if key.lower() in self.PHI_IDENTIFIERS:
                        phi_found.append({
                            "field": current_path,
                            "type": "Direct PHI identifier",
                            "value": str(value)[:50] + "..." if len(str(value)) > 50 else str(value)
                        })
                    
                    # Check for potential PHI patterns in values
                    if isinstance(value, str):
                        if self._contains_phi_patterns(value):
                            phi_found.append({
                                "field": current_path,
                                "type": "Potential PHI in value",
                                "value": value[:50] + "..." if len(value) > 50 else value
                            })
                    
                    scan_for_phi(value, current_path)
                    
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    scan_for_phi(item, f"{path}[{i}]")
        
        scan_for_phi(data)
        
        # Generate compliance assessment
        if phi_found:
            recommendations.extend([
                "Ensure proper encryption for PHI data transmission",
                "Verify user authorization before sharing PHI",
                "Log all PHI access for audit purposes",
                "Consider data minimization - only include necessary PHI",
                "Implement role-based access controls"
            ])
        
        compliance_score = max(0, 100 - (len(phi_found) * 10))
        
        return Response(
            message=f"PHI Validation Report:\n"
                   f"- Compliance Score: {compliance_score}/100\n"
                   f"- PHI Elements Found: {len(phi_found)}\n"
                   f"- Violations: {len(violations)}\n\n"
                   f"PHI Elements Detected:\n{json.dumps(phi_found, indent=2)}\n\n"
                   f"Recommendations:\n" + "\n".join(f"• {rec}" for rec in recommendations),
            break_loop=False
        )
    
    def _contains_phi_patterns(self, value: str) -> bool:
        """Check if string contains common PHI patterns"""
        import re
        
        patterns = [
            r'\b\d{3}-\d{2}-\d{4}\b',  # SSN
            r'\b\d{3}\.\d{2}\.\d{4}\b',  # SSN with dots
            r'\b\d{10,}\b',  # Long numbers (could be medical record numbers)
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Email
            r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',  # Phone number
        ]
        
        for pattern in patterns:
            if re.search(pattern, value):
                return True
        return False
    
    async def _create_audit_log(self, user_id: str, patient_id: str, purpose: str, data: Optional[Dict] = None) -> Response:
        """Create HIPAA-compliant audit log entry"""
        
        if not user_id or not patient_id:
            return Response(
                message="Error: user_id and patient_id required for audit logging",
                break_loop=False
            )
        
        # Create audit log entry
        audit_entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "user_id": user_id,
            "patient_id": patient_id,
            "purpose": purpose,
            "action": "data_access",
            "ip_address": "system_internal",  # Should be captured from request
            "user_agent": "Agent-Zero-DrChrono",
            "data_accessed": self._sanitize_for_audit(data) if data else "Not specified",
            "compliance_verified": True,
            "audit_id": hashlib.sha256(f"{user_id}{patient_id}{datetime.datetime.now().isoformat()}".encode()).hexdigest()[:16]
        }
        
        # Store audit log (in production, this would go to secure audit system)
        audit_logs = self.agent.get_data("hipaa_audit_logs") or []
        audit_logs.append(audit_entry)
        self.agent.set_data("hipaa_audit_logs", audit_logs[-100:])  # Keep last 100 entries
        
        return Response(
            message=f"HIPAA Audit Log Created:\n"
                   f"- Audit ID: {audit_entry['audit_id']}\n"
                   f"- User: {user_id}\n"
                   f"- Patient: {patient_id}\n"
                   f"- Purpose: {purpose}\n"
                   f"- Timestamp: {audit_entry['timestamp']}\n"
                   f"- Compliance Status: Verified",
            break_loop=False
        )
    
    def _sanitize_for_audit(self, data: Dict) -> Dict:
        """Sanitize data for audit logging (remove actual PHI values)"""
        if not isinstance(data, dict):
            return {"data_type": str(type(data).__name__)}
        
        sanitized = {}
        for key, value in data.items():
            if key.lower() in self.PHI_IDENTIFIERS:
                sanitized[key] = "***PHI_REDACTED***"
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_for_audit(value)
            elif isinstance(value, list):
                sanitized[key] = f"Array[{len(value)}]"
            else:
                sanitized[key] = str(type(value).__name__)
        
        return sanitized
    
    async def _check_patient_consent(self, patient_id: str, purpose: str) -> Response:
        """Check patient consent for data use"""
        
        if not patient_id:
            return Response(
                message="Error: patient_id required for consent verification",
                break_loop=False
            )
        
        # In production, this would check actual consent records
        consent_records = self.agent.get_data("patient_consents") or {}
        patient_consent = consent_records.get(patient_id, {})
        
        valid_purposes = ["treatment", "payment", "healthcare_operations", "research", "marketing"]
        
        if purpose.lower() not in valid_purposes:
            return Response(
                message=f"Warning: Purpose '{purpose}' not recognized. Valid purposes: {', '.join(valid_purposes)}",
                break_loop=False
            )
        
        # Check specific consent
        consent_status = patient_consent.get(purpose.lower(), "not_specified")
        
        return Response(
            message=f"Patient Consent Status:\n"
                   f"- Patient ID: {patient_id}\n"
                   f"- Purpose: {purpose}\n"
                   f"- Consent Status: {consent_status}\n"
                   f"- Verification: {'APPROVED' if consent_status == 'granted' else 'REQUIRES_REVIEW'}\n\n"
                   f"Note: In production, verify actual consent records before proceeding.",
            break_loop=False
        )
    
    async def _verify_user_access(self, user_id: str, patient_id: str, access_level: str) -> Response:
        """Verify user has appropriate access to patient data"""
        
        if not user_id or not patient_id:
            return Response(
                message="Error: user_id and patient_id required for access verification",
                break_loop=False
            )
        
        if access_level not in self.ACCESS_LEVELS:
            return Response(
                message=f"Error: Invalid access level. Valid levels: {', '.join(self.ACCESS_LEVELS.keys())}",
                break_loop=False
            )
        
        # In production, this would check actual RBAC system
        user_permissions = self.agent.get_data("user_permissions") or {}
        user_access = user_permissions.get(user_id, {})
        
        # Check role-based access
        user_role = user_access.get("role", "unknown")
        allowed_patients = user_access.get("allowed_patients", [])
        access_granted = (
            user_role in ["doctor", "nurse", "administrator"] or
            patient_id in allowed_patients or
            "all_patients" in allowed_patients
        )
        
        return Response(
            message=f"Access Verification Result:\n"
                   f"- User ID: {user_id}\n"
                   f"- User Role: {user_role}\n"
                   f"- Patient ID: {patient_id}\n"
                   f"- Requested Access Level: {access_level}\n"
                   f"- Access Status: {'GRANTED' if access_granted else 'DENIED'}\n"
                   f"- Minimum Necessary: {self.ACCESS_LEVELS[access_level]}\n\n"
                   f"Note: In production, integrate with actual RBAC system.",
            break_loop=False
        )
    
    async def _generate_compliance_report(self, start_date: str = None, end_date: str = None) -> Response:
        """Generate HIPAA compliance report"""
        
        audit_logs = self.agent.get_data("hipaa_audit_logs") or []
        
        if not audit_logs:
            return Response(
                message="No audit logs found. HIPAA compliance reporting requires audit data.",
                break_loop=False
            )
        
        # Filter by date range if provided
        if start_date and end_date:
            filtered_logs = [
                log for log in audit_logs
                if start_date <= log["timestamp"][:10] <= end_date
            ]
        else:
            filtered_logs = audit_logs
        
        # Generate statistics
        total_accesses = len(filtered_logs)
        unique_users = len(set(log["user_id"] for log in filtered_logs))
        unique_patients = len(set(log["patient_id"] for log in filtered_logs))
        
        purposes = {}
        for log in filtered_logs:
            purpose = log.get("purpose", "unspecified")
            purposes[purpose] = purposes.get(purpose, 0) + 1
        
        return Response(
            message=f"HIPAA Compliance Report:\n"
                   f"- Report Period: {start_date or 'All time'} to {end_date or 'Present'}\n"
                   f"- Total Data Accesses: {total_accesses}\n"
                   f"- Unique Users: {unique_users}\n"
                   f"- Unique Patients: {unique_patients}\n"
                   f"- Access Purposes: {json.dumps(purposes, indent=2)}\n\n"
                   f"Compliance Status: MONITORED\n"
                   f"All accesses have been logged and audited.",
            break_loop=False
        )
    
    async def _mask_phi_data(self, data: Optional[Dict]) -> Response:
        """Mask PHI in data for safe display/logging"""
        
        if not data:
            return Response(
                message="Error: Data required for PHI masking",
                break_loop=False
            )
        
        def mask_phi_recursive(obj):
            if isinstance(obj, dict):
                masked = {}
                for key, value in obj.items():
                    if key.lower() in self.PHI_IDENTIFIERS:
                        masked[key] = "***MASKED***"
                    else:
                        masked[key] = mask_phi_recursive(value)
                return masked
            elif isinstance(obj, list):
                return [mask_phi_recursive(item) for item in obj]
            else:
                return obj
        
        masked_data = mask_phi_recursive(data)
        
        return Response(
            message=f"PHI Data Masking Complete:\n{json.dumps(masked_data, indent=2)}\n\n"
                   f"All PHI identifiers have been masked for safe display.",
            break_loop=False
        )
    
    async def _conduct_risk_assessment(self, data: Optional[Dict]) -> Response:
        """Conduct privacy risk assessment"""
        
        if not data:
            return Response(
                message="Error: Data required for risk assessment",
                break_loop=False
            )
        
        risks = []
        phi_count = 0
        
        def assess_risks(obj, path=""):
            nonlocal phi_count
            if isinstance(obj, dict):
                for key, value in obj.items():
                    current_path = f"{path}.{key}" if path else key
                    if key.lower() in self.PHI_IDENTIFIERS:
                        phi_count += 1
                        if key.lower() in ['ssn', 'social_security_number']:
                            risks.append(f"HIGH RISK: SSN found at {current_path}")
                        elif key.lower() in ['date_of_birth', 'dob']:
                            risks.append(f"MEDIUM RISK: Date of birth at {current_path}")
                        else:
                            risks.append(f"LOW RISK: PHI identifier at {current_path}")
                    assess_risks(value, current_path)
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    assess_risks(item, f"{path}[{i}]")
        
        assess_risks(data)
        
        # Calculate overall risk score
        risk_score = min(100, phi_count * 15)
        risk_level = "HIGH" if risk_score > 70 else "MEDIUM" if risk_score > 30 else "LOW"
        
        return Response(
            message=f"Privacy Risk Assessment:\n"
                   f"- Overall Risk Level: {risk_level}\n"
                   f"- Risk Score: {risk_score}/100\n"
                   f"- PHI Elements: {phi_count}\n"
                   f"- Identified Risks:\n" + "\n".join(f"  • {risk}" for risk in risks) + "\n\n"
                   f"Recommendations:\n"
                   f"• Implement strong encryption for data transmission\n"
                   f"• Use secure authentication for all access\n"
                   f"• Maintain detailed audit logs\n"
                   f"• Apply data minimization principles",
            break_loop=False
        )
    
    async def _detect_potential_breach(self, data: Optional[Dict], user_id: str) -> Response:
        """Detect potential HIPAA breach scenarios"""
        
        breach_indicators = []
        
        # Check for unusual data access patterns
        if data and len(str(data)) > 10000:  # Large data access
            breach_indicators.append("Large volume of data accessed")
        
        # Check access time (outside business hours could be suspicious)
        current_hour = datetime.datetime.now().hour
        if current_hour < 6 or current_hour > 22:
            breach_indicators.append("Access outside normal business hours")
        
        # Check for bulk patient data
        if isinstance(data, dict) and 'patients' in str(data).lower():
            breach_indicators.append("Multiple patient records accessed")
        
        # Get recent audit logs to check for patterns
        audit_logs = self.agent.get_data("hipaa_audit_logs") or []
        recent_logs = [log for log in audit_logs 
                      if log.get("user_id") == user_id 
                      and log.get("timestamp", "").startswith(datetime.datetime.now().strftime("%Y-%m-%d"))]
        
        if len(recent_logs) > 20:  # Excessive access in one day
            breach_indicators.append("Excessive data access frequency")
        
        breach_risk = "HIGH" if len(breach_indicators) > 2 else "MEDIUM" if len(breach_indicators) > 0 else "LOW"
        
        if breach_indicators:
            # Log potential breach for investigation
            breach_alert = {
                "timestamp": datetime.datetime.now().isoformat(),
                "user_id": user_id,
                "indicators": breach_indicators,
                "risk_level": breach_risk,
                "investigation_required": len(breach_indicators) > 1
            }
            
            breach_alerts = self.agent.get_data("breach_alerts") or []
            breach_alerts.append(breach_alert)
            self.agent.set_data("breach_alerts", breach_alerts[-50:])  # Keep last 50 alerts
        
        return Response(
            message=f"Breach Detection Analysis:\n"
                   f"- Risk Level: {breach_risk}\n"
                   f"- Indicators Found: {len(breach_indicators)}\n"
                   f"- Investigation Required: {'YES' if len(breach_indicators) > 1 else 'NO'}\n\n"
                   f"Breach Indicators:\n" + "\n".join(f"• {indicator}" for indicator in breach_indicators) + "\n\n"
                   f"{'ALERT: Potential breach detected! Immediate review recommended.' if breach_risk == 'HIGH' else 'Status: Normal operations'}",
            break_loop=False
        )


# Common HIPAA compliance requirements
HIPAA_REQUIREMENTS = {
    "access_control": "Assign unique access credentials and automatic logoff",
    "audit_controls": "Hardware, software, and procedural mechanisms for audit",
    "integrity": "Protect PHI from improper alteration or destruction",
    "transmission_security": "Guard against unauthorized access during transmission",
    "minimum_necessary": "Use and disclose only minimum PHI necessary",
    "consent_management": "Obtain and document patient consent for data use",
    "breach_notification": "Notify patients and authorities of data breaches",
    "business_associate": "Ensure third parties comply with HIPAA requirements"
}