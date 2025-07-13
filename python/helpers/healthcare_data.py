"""
Healthcare Data Helper Module

Provides healthcare-specific data processing utilities including:
- FHIR resource validation and transformation
- Clinical code validation (ICD-10, CPT, SNOMED)
- Patient demographics handling
- PHI de-identification utilities
- Medical terminology processing
"""

import re
import json
import hashlib
from typing import Dict, Any, Optional, List, Set, Tuple
from datetime import datetime, date
from dataclasses import dataclass
import unicodedata


@dataclass
class ValidationResult:
    """Result of data validation"""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    suggestions: List[str]


@dataclass
class PatientDemographics:
    """Standardized patient demographics"""
    first_name: str
    last_name: str
    date_of_birth: date
    gender: str
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[Dict[str, str]] = None
    emergency_contact: Optional[Dict[str, str]] = None
    insurance: Optional[Dict[str, str]] = None


class FHIRValidator:
    """FHIR (Fast Healthcare Interoperability Resources) validator"""
    
    # FHIR resource types
    RESOURCE_TYPES = {
        'Patient', 'Practitioner', 'Organization', 'Location',
        'Encounter', 'Observation', 'Condition', 'Procedure',
        'MedicationRequest', 'DiagnosticReport', 'AllergyIntolerance',
        'Immunization', 'CarePlan', 'Goal', 'Appointment'
    }
    
    # Required fields for common FHIR resources
    REQUIRED_FIELDS = {
        'Patient': ['resourceType', 'identifier', 'name', 'gender'],
        'Practitioner': ['resourceType', 'identifier', 'name'],
        'Encounter': ['resourceType', 'status', 'class', 'subject'],
        'Observation': ['resourceType', 'status', 'code', 'subject'],
        'Condition': ['resourceType', 'code', 'subject'],
        'Procedure': ['resourceType', 'status', 'code', 'subject'],
        'MedicationRequest': ['resourceType', 'status', 'intent', 'medicationCodeableConcept', 'subject']
    }
    
    def validate_resource(self, resource: Dict[str, Any]) -> ValidationResult:
        """Validate FHIR resource structure"""
        errors = []
        warnings = []
        suggestions = []
        
        # Check resource type
        resource_type = resource.get('resourceType')
        if not resource_type:
            errors.append("Missing required field: resourceType")
        elif resource_type not in self.RESOURCE_TYPES:
            errors.append(f"Unknown resource type: {resource_type}")
        
        # Check required fields
        if resource_type in self.REQUIRED_FIELDS:
            required_fields = self.REQUIRED_FIELDS[resource_type]
            for field in required_fields:
                if field not in resource:
                    errors.append(f"Missing required field for {resource_type}: {field}")
        
        # Validate identifiers
        if 'identifier' in resource:
            identifier_errors = self._validate_identifiers(resource['identifier'])
            errors.extend(identifier_errors)
        
        # Validate dates
        date_errors, date_warnings = self._validate_dates(resource)
        errors.extend(date_errors)
        warnings.extend(date_warnings)
        
        # Validate coding systems
        coding_errors, coding_suggestions = self._validate_coding(resource)
        errors.extend(coding_errors)
        suggestions.extend(coding_suggestions)
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            suggestions=suggestions
        )
    
    def _validate_identifiers(self, identifiers: List[Dict]) -> List[str]:
        """Validate FHIR identifiers"""
        errors = []
        
        if not isinstance(identifiers, list):
            errors.append("Identifiers must be an array")
            return errors
        
        for i, identifier in enumerate(identifiers):
            if not isinstance(identifier, dict):
                errors.append(f"Identifier {i} must be an object")
                continue
            
            if 'value' not in identifier:
                errors.append(f"Identifier {i} missing required 'value' field")
            
            if 'system' not in identifier:
                errors.append(f"Identifier {i} missing recommended 'system' field")
        
        return errors
    
    def _validate_dates(self, resource: Dict) -> Tuple[List[str], List[str]]:
        """Validate date fields in FHIR resource"""
        errors = []
        warnings = []
        
        date_fields = ['birthDate', 'deceasedDateTime', 'effectiveDateTime', 'onsetDateTime']
        
        for field in date_fields:
            if field in resource:
                date_value = resource[field]
                if not self._is_valid_fhir_date(date_value):
                    errors.append(f"Invalid date format for {field}: {date_value}")
        
        return errors, warnings
    
    def _is_valid_fhir_date(self, date_str: str) -> bool:
        """Check if date string is valid FHIR date format"""
        # FHIR date format: YYYY, YYYY-MM, or YYYY-MM-DD
        date_patterns = [
            r'^\d{4}$',  # YYYY
            r'^\d{4}-\d{2}$',  # YYYY-MM
            r'^\d{4}-\d{2}-\d{2}$',  # YYYY-MM-DD
            r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$'  # DateTime
        ]
        
        return any(re.match(pattern, date_str) for pattern in date_patterns)
    
    def _validate_coding(self, resource: Dict) -> Tuple[List[str], List[str]]:
        """Validate coding systems and codes"""
        errors = []
        suggestions = []
        
        def check_coding_recursive(obj, path=""):
            if isinstance(obj, dict):
                if 'coding' in obj:
                    coding_list = obj['coding']
                    if isinstance(coding_list, list):
                        for i, coding in enumerate(coding_list):
                            if 'system' not in coding:
                                errors.append(f"Missing 'system' in coding at {path}.coding[{i}]")
                            if 'code' not in coding:
                                errors.append(f"Missing 'code' in coding at {path}.coding[{i}]")
                            
                            # Suggest standard coding systems
                            system = coding.get('system', '')
                            if system and not any(std in system for std in ['snomed', 'icd', 'loinc', 'cpt']):
                                suggestions.append(f"Consider using standard coding system at {path}.coding[{i}]")
                
                for key, value in obj.items():
                    check_coding_recursive(value, f"{path}.{key}" if path else key)
            
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    check_coding_recursive(item, f"{path}[{i}]")
        
        check_coding_recursive(resource)
        return errors, suggestions


class ClinicalCodeValidator:
    """Validator for clinical coding systems"""
    
    # ICD-10 code pattern (simplified)
    ICD10_PATTERN = re.compile(r'^[A-Z]\d{2}(\.[A-Z0-9]{1,4})?$')
    
    # CPT code pattern
    CPT_PATTERN = re.compile(r'^\d{5}$')
    
    # HCPCS code pattern
    HCPCS_PATTERN = re.compile(r'^[A-Z]\d{4}$')
    
    # SNOMED CT code pattern (simplified)
    SNOMED_PATTERN = re.compile(r'^\d{6,18}$')
    
    def validate_icd10_code(self, code: str) -> ValidationResult:
        """Validate ICD-10 diagnosis code"""
        errors = []
        warnings = []
        suggestions = []
        
        if not code:
            errors.append("ICD-10 code cannot be empty")
            return ValidationResult(False, errors, warnings, suggestions)
        
        code = code.upper().strip()
        
        if not self.ICD10_PATTERN.match(code):
            errors.append(f"Invalid ICD-10 code format: {code}")
            suggestions.append("ICD-10 codes should be in format: A00 or A00.0")
        
        # Check for common issues
        if len(code) < 3:
            errors.append("ICD-10 code too short")
        
        if '.' in code and len(code.split('.')[1]) > 4:
            warnings.append("ICD-10 subcategory code unusually long")
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            suggestions=suggestions
        )
    
    def validate_cpt_code(self, code: str) -> ValidationResult:
        """Validate CPT procedure code"""
        errors = []
        warnings = []
        suggestions = []
        
        if not code:
            errors.append("CPT code cannot be empty")
            return ValidationResult(False, errors, warnings, suggestions)
        
        code = code.strip()
        
        if not self.CPT_PATTERN.match(code):
            errors.append(f"Invalid CPT code format: {code}")
            suggestions.append("CPT codes should be 5 digits (e.g., 99213)")
        
        # Check ranges for validity
        code_num = int(code) if code.isdigit() else 0
        
        if code_num < 10000 or code_num > 99999:
            errors.append("CPT code out of valid range")
        
        # Check for common evaluation & management codes
        if 99200 <= code_num <= 99499:
            suggestions.append("E&M code - ensure proper documentation level")
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            suggestions=suggestions
        )
    
    def validate_snomed_code(self, code: str) -> ValidationResult:
        """Validate SNOMED CT code"""
        errors = []
        warnings = []
        suggestions = []
        
        if not code:
            errors.append("SNOMED code cannot be empty")
            return ValidationResult(False, errors, warnings, suggestions)
        
        code = code.strip()
        
        if not self.SNOMED_PATTERN.match(code):
            errors.append(f"Invalid SNOMED code format: {code}")
            suggestions.append("SNOMED codes should be 6-18 digits")
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            suggestions=suggestions
        )


class PatientDataProcessor:
    """Patient data processing and validation"""
    
    # Valid gender values (FHIR)
    VALID_GENDERS = {'male', 'female', 'other', 'unknown'}
    
    # Phone number pattern
    PHONE_PATTERN = re.compile(r'^\+?1?[-.\s]?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})$')
    
    # Email pattern
    EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    
    def validate_patient_demographics(self, patient_data: Dict[str, Any]) -> ValidationResult:
        """Validate patient demographic data"""
        errors = []
        warnings = []
        suggestions = []
        
        # Required fields check
        required_fields = ['first_name', 'last_name', 'date_of_birth', 'gender']
        for field in required_fields:
            if field not in patient_data or not patient_data[field]:
                errors.append(f"Missing required field: {field}")
        
        # Name validation
        if 'first_name' in patient_data:
            name_errors = self._validate_name(patient_data['first_name'], 'first_name')
            errors.extend(name_errors)
        
        if 'last_name' in patient_data:
            name_errors = self._validate_name(patient_data['last_name'], 'last_name')
            errors.extend(name_errors)
        
        # Date of birth validation
        if 'date_of_birth' in patient_data:
            dob_errors, dob_warnings = self._validate_date_of_birth(patient_data['date_of_birth'])
            errors.extend(dob_errors)
            warnings.extend(dob_warnings)
        
        # Gender validation
        if 'gender' in patient_data:
            gender = patient_data['gender'].lower().strip()
            if gender not in self.VALID_GENDERS:
                errors.append(f"Invalid gender value: {gender}. Valid values: {', '.join(self.VALID_GENDERS)}")
        
        # Phone validation
        if 'phone' in patient_data and patient_data['phone']:
            if not self.PHONE_PATTERN.match(patient_data['phone']):
                errors.append("Invalid phone number format")
                suggestions.append("Use format: (555) 123-4567 or 555-123-4567")
        
        # Email validation
        if 'email' in patient_data and patient_data['email']:
            if not self.EMAIL_PATTERN.match(patient_data['email']):
                errors.append("Invalid email address format")
        
        # SSN validation (if present)
        if 'ssn' in patient_data and patient_data['ssn']:
            ssn_errors = self._validate_ssn(patient_data['ssn'])
            errors.extend(ssn_errors)
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            suggestions=suggestions
        )
    
    def _validate_name(self, name: str, field_name: str) -> List[str]:
        """Validate name fields"""
        errors = []
        
        if not isinstance(name, str):
            errors.append(f"{field_name} must be a string")
            return errors
        
        name = name.strip()
        
        if len(name) < 1:
            errors.append(f"{field_name} cannot be empty")
        
        if len(name) > 50:
            errors.append(f"{field_name} too long (max 50 characters)")
        
        # Check for invalid characters
        if re.search(r'[0-9]', name):
            errors.append(f"{field_name} should not contain numbers")
        
        if re.search(r'[^a-zA-Z\s\'-]', name):
            errors.append(f"{field_name} contains invalid characters")
        
        return errors
    
    def _validate_date_of_birth(self, dob: str) -> Tuple[List[str], List[str]]:
        """Validate date of birth"""
        errors = []
        warnings = []
        
        try:
            if isinstance(dob, str):
                # Try different date formats
                for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y']:
                    try:
                        birth_date = datetime.strptime(dob, fmt).date()
                        break
                    except ValueError:
                        continue
                else:
                    errors.append("Invalid date format. Use YYYY-MM-DD")
                    return errors, warnings
            elif isinstance(dob, date):
                birth_date = dob
            else:
                errors.append("Date of birth must be a string or date object")
                return errors, warnings
            
            # Check if date is reasonable
            today = date.today()
            age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
            
            if birth_date > today:
                errors.append("Date of birth cannot be in the future")
            
            if age > 150:
                warnings.append("Patient age over 150 years - please verify")
            
            if age < 0:
                errors.append("Invalid date of birth")
            
        except Exception as e:
            errors.append(f"Error validating date of birth: {str(e)}")
        
        return errors, warnings
    
    def _validate_ssn(self, ssn: str) -> List[str]:
        """Validate Social Security Number"""
        errors = []
        
        # Remove formatting
        ssn_digits = re.sub(r'[^0-9]', '', ssn)
        
        if len(ssn_digits) != 9:
            errors.append("SSN must be 9 digits")
            return errors
        
        # Check for invalid patterns
        if ssn_digits == '000000000':
            errors.append("Invalid SSN: all zeros")
        
        if ssn_digits[:3] == '666':
            errors.append("Invalid SSN: cannot start with 666")
        
        if ssn_digits[:3] == '900':
            errors.append("Invalid SSN: cannot start with 900")
        
        return errors
    
    def normalize_patient_data(self, patient_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize patient data to standard format"""
        normalized = {}
        
        # Normalize names
        if 'first_name' in patient_data:
            normalized['first_name'] = self._normalize_name(patient_data['first_name'])
        
        if 'last_name' in patient_data:
            normalized['last_name'] = self._normalize_name(patient_data['last_name'])
        
        if 'middle_name' in patient_data:
            normalized['middle_name'] = self._normalize_name(patient_data['middle_name'])
        
        # Normalize phone
        if 'phone' in patient_data and patient_data['phone']:
            normalized['phone'] = self._normalize_phone(patient_data['phone'])
        
        # Normalize email
        if 'email' in patient_data and patient_data['email']:
            normalized['email'] = patient_data['email'].lower().strip()
        
        # Normalize gender
        if 'gender' in patient_data:
            normalized['gender'] = patient_data['gender'].lower().strip()
        
        # Copy other fields as-is
        for key, value in patient_data.items():
            if key not in normalized:
                normalized[key] = value
        
        return normalized
    
    def _normalize_name(self, name: str) -> str:
        """Normalize name to standard format"""
        if not isinstance(name, str):
            return name
        
        # Remove extra whitespace and normalize
        name = ' '.join(name.strip().split())
        
        # Capitalize properly
        name = name.title()
        
        # Handle special cases
        name = re.sub(r'\bMc([a-z])', r'Mc\1'.upper(), name)
        name = re.sub(r'\bO\'([a-z])', r"O'\1".upper(), name)
        
        return name
    
    def _normalize_phone(self, phone: str) -> str:
        """Normalize phone number to standard format"""
        # Extract digits only
        digits = re.sub(r'[^0-9]', '', phone)
        
        # Remove leading 1 if present
        if len(digits) == 11 and digits[0] == '1':
            digits = digits[1:]
        
        # Format as (XXX) XXX-XXXX
        if len(digits) == 10:
            return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
        
        return phone  # Return original if can't normalize


class PHIDeidentifier:
    """De-identification utility for Protected Health Information"""
    
    def __init__(self):
        self.salt = "agent_zero_deidentification_salt"
    
    def deidentify_patient_data(self, patient_data: Dict[str, Any]) -> Dict[str, Any]:
        """De-identify patient data for research/analytics"""
        deidentified = {}
        
        # Replace direct identifiers with hashed versions
        direct_identifiers = {
            'first_name', 'last_name', 'middle_name', 'name',
            'ssn', 'social_security_number', 'mrn', 'medical_record_number',
            'phone', 'email', 'address', 'patient_id'
        }
        
        for key, value in patient_data.items():
            if key.lower() in direct_identifiers:
                if value:
                    deidentified[f"{key}_hash"] = self._hash_identifier(str(value))
            elif key.lower() == 'date_of_birth':
                # Generalize birth date to birth year only
                if value:
                    try:
                        if isinstance(value, str):
                            birth_year = datetime.strptime(value, '%Y-%m-%d').year
                        else:
                            birth_year = value.year
                        deidentified['birth_year'] = birth_year
                    except:
                        deidentified['birth_year'] = None
            elif key.lower() in ['zip', 'postal_code', 'zipcode']:
                # Generalize ZIP code to first 3 digits
                if value and len(str(value)) >= 5:
                    deidentified[f"{key}_3digit"] = str(value)[:3] + "XX"
            else:
                # Keep non-identifying fields
                deidentified[key] = value
        
        return deidentified
    
    def _hash_identifier(self, identifier: str) -> str:
        """Create consistent hash of identifier"""
        combined = f"{identifier}{self.salt}"
        return hashlib.sha256(combined.encode()).hexdigest()[:16]
    
    def create_synthetic_patient(self, template: Dict[str, Any]) -> Dict[str, Any]:
        """Create synthetic patient data for testing"""
        import random
        
        synthetic = template.copy()
        
        # Replace with synthetic values
        synthetic.update({
            'first_name': random.choice(['John', 'Jane', 'Michael', 'Sarah', 'David', 'Emily']),
            'last_name': random.choice(['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia']),
            'phone': f"({random.randint(200, 999)}) {random.randint(200, 999)}-{random.randint(1000, 9999)}",
            'email': f"patient{random.randint(1000, 9999)}@example.com",
            'ssn': f"{random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(1000, 9999)}",
            'medical_record_number': f"MRN{random.randint(100000, 999999)}"
        })
        
        return synthetic


# Medical terminology mappings
MEDICAL_TERMINOLOGIES = {
    'gender_codes': {
        'M': 'male',
        'F': 'female',
        'U': 'unknown',
        'O': 'other'
    },
    
    'common_icd10_codes': {
        'Z00.00': 'Encounter for general adult medical examination without abnormal findings',
        'Z12.31': 'Encounter for screening mammogram for malignant neoplasm of breast',
        'I10': 'Essential hypertension',
        'E11.9': 'Type 2 diabetes mellitus without complications',
        'M79.3': 'Panniculitis, unspecified'
    },
    
    'common_cpt_codes': {
        '99213': 'Office or other outpatient visit for evaluation and management',
        '99214': 'Office or other outpatient visit for evaluation and management',
        '99215': 'Office or other outpatient visit for evaluation and management',
        '90791': 'Psychiatric diagnostic evaluation',
        '36415': 'Collection of venous blood by venipuncture'
    }
}


def validate_healthcare_data(data: Dict[str, Any], data_type: str = "patient") -> ValidationResult:
    """Main validation function for healthcare data"""
    
    if data_type == "patient":
        processor = PatientDataProcessor()
        return processor.validate_patient_demographics(data)
    
    elif data_type == "fhir":
        validator = FHIRValidator()
        return validator.validate_resource(data)
    
    else:
        return ValidationResult(
            is_valid=False,
            errors=[f"Unknown data type: {data_type}"],
            warnings=[],
            suggestions=["Use 'patient' or 'fhir' as data_type"]
        )