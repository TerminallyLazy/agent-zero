"""
Advanced secrets handling for Agent Zero.
Implements placeholder substitution to keep real credentials out of prompts, logs, and front-end.
"""

import os
import re
import stat
from typing import Dict, List, Any, Union
from pathlib import Path
from python.helpers import files
from python.helpers.print_style import PrintStyle


class SecretsManager:
    """Centralized secrets management for Agent Zero"""
    
    SECRETS_FILE = "tmp/secrets.env"
    PLACEHOLDER_PATTERN = r"§§([A-Z_][A-Z0-9_]*)§§"
    _secrets_cache: Dict[str, str] = {}
    _cache_loaded = False
    
    @classmethod
    def load_secrets_dict(cls) -> Dict[str, str]:
        """Load secrets from the secrets.env file"""
        if cls._cache_loaded and cls._secrets_cache:
            return cls._secrets_cache.copy()
            
        secrets_path = files.get_abs_path(cls.SECRETS_FILE)
        
        if not os.path.exists(secrets_path):
            # Create the file if it doesn't exist
            os.makedirs(os.path.dirname(secrets_path), exist_ok=True)
            Path(secrets_path).touch(mode=0o600)
            cls._cache_loaded = True
            return {}
            
        # Verify file permissions
        file_stats = os.stat(secrets_path)
        if file_stats.st_mode & 0o077:  # Check if file is readable by group/others
            try:
                PrintStyle(background_color="red", font_color="white", padding=True).print(
                    f"WARNING: {secrets_path} has insecure permissions. Run: chmod 600 {secrets_path}"
                )
            except:
                # Fallback for testing environments
                print(f"WARNING: {secrets_path} has insecure permissions. Run: chmod 600 {secrets_path}")
        
        secrets = {}
        try:
            # Try UTF-8 first, fall back to Latin-1 if needed
            try:
                with open(secrets_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except UnicodeDecodeError:
                with open(secrets_path, 'r', encoding='latin-1') as f:
                    content = f.read()
            
            for line_num, line in enumerate(content.splitlines(), 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                    
                if '=' not in line:
                    continue
                    
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                
                # Remove surrounding quotes if present
                if (value.startswith('"') and value.endswith('"')) or \
                   (value.startswith("'") and value.endswith("'")):
                    value = value[1:-1]
                
                if key and value:
                    secrets[key] = value
                        
        except Exception as e:
            try:
                PrintStyle(background_color="red", font_color="white", padding=True).print(
                    f"Error loading secrets from {secrets_path}: {e}"
                )
            except:
                # Fallback for testing environments
                print(f"Error loading secrets from {secrets_path}: {e}")
            
        cls._secrets_cache = secrets
        cls._cache_loaded = True
        return secrets.copy()
    
    @classmethod
    def get_placeholder_keys(cls) -> List[str]:
        """Get list of available secret keys for use in prompts"""
        secrets = cls.load_secrets_dict()
        return list(secrets.keys())
    
    @classmethod
    def replace_placeholders_in_text(cls, text: str, warn_missing: bool = True, raise_on_missing: bool = False) -> str:
        """Replace §§SECRET_NAME§§ placeholders with actual values"""
        if not isinstance(text, str):
            return text
            
        secrets = cls.load_secrets_dict()
        
        def replace_placeholder(match):
            key = match.group(1)
            if key in secrets:
                secret_value = secrets[key]
                # Only return value if it's not empty
                if secret_value:
                    return secret_value
                else:
                    # Empty secret - return empty string (no warning needed)
                    return ""
            else:
                # Missing secret
                if raise_on_missing:
                    # Import here to avoid circular imports
                    from agent import RepairableException
                    raise RepairableException(f"Secret placeholder §§{key}§§ not found in secrets.env. Please add this secret to your secrets configuration.")
                elif warn_missing:
                    # Log warning for user-facing placeholders
                    try:
                        PrintStyle(background_color="yellow", font_color="black", padding=True).print(
                            f"Warning: Secret placeholder §§{key}§§ not found in secrets.env"
                        )
                    except:
                        # Fallback for testing environments
                        print(f"Warning: Secret placeholder §§{key}§§ not found in secrets.env")
                    return match.group(0)  # Return original placeholder
                else:
                    # Silent mode for optional config values
                    return ""
        
        return re.sub(cls.PLACEHOLDER_PATTERN, replace_placeholder, text)
    
    @classmethod
    def replace_placeholders_in_text_silent(cls, text: str) -> str:
        """Replace placeholders without warnings (for optional config values)"""
        return cls.replace_placeholders_in_text(text, warn_missing=False)
    
    @classmethod
    def replace_placeholders_in_text_strict(cls, text: str) -> str:
        """Replace placeholders with RepairableException for missing values (for tools)"""
        return cls.replace_placeholders_in_text(text, warn_missing=False, raise_on_missing=True)
    
    @classmethod
    def replace_placeholders_in_dict(cls, data: Dict[str, Any], strict: bool = True) -> Dict[str, Any]:
        """Recursively replace placeholders in dictionary values"""
        if not isinstance(data, dict):
            return data
            
        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                if strict:
                    result[key] = cls.replace_placeholders_in_text_strict(value)
                else:
                    result[key] = cls.replace_placeholders_in_text(value)
            elif isinstance(value, dict):
                result[key] = cls.replace_placeholders_in_dict(value, strict=strict)
            elif isinstance(value, list):
                result[key] = cls.replace_placeholders_in_list(value, strict=strict)
            else:
                result[key] = value
        return result
    
    @classmethod
    def replace_placeholders_in_list(cls, data: List[Any], strict: bool = True) -> List[Any]:
        """Recursively replace placeholders in list values"""
        if not isinstance(data, list):
            return data
            
        result = []
        for item in data:
            if isinstance(item, str):
                if strict:
                    result.append(cls.replace_placeholders_in_text_strict(item))
                else:
                    result.append(cls.replace_placeholders_in_text(item))
            elif isinstance(item, dict):
                result.append(cls.replace_placeholders_in_dict(item, strict=strict))
            elif isinstance(item, list):
                result.append(cls.replace_placeholders_in_list(item, strict=strict))
            else:
                result.append(item)
        return result
    
    @classmethod
    def replace_values_with_placeholders(cls, text: str) -> str:
        """Replace actual secret values with placeholders for logging/display"""
        if not isinstance(text, str):
            return text
            
        secrets = cls.load_secrets_dict()
        result = text
        
        # Sort by length (longest first) to avoid partial replacements
        for key, value in sorted(secrets.items(), key=lambda x: len(x[1]), reverse=True):
            if value and len(value) >= 8:  # Only replace reasonably long secrets
                placeholder = f"§§{key}§§"
                result = result.replace(value, placeholder)
                
        return result
    
    @classmethod
    def validate_secrets_file(cls) -> List[str]:
        """Validate secrets file and return list of issues"""
        issues = []
        secrets_path = files.get_abs_path(cls.SECRETS_FILE)
        
        if not os.path.exists(secrets_path):
            issues.append(f"Secrets file does not exist: {secrets_path}")
            return issues
            
        # Check file permissions
        file_stats = os.stat(secrets_path)
        if file_stats.st_mode & 0o077:
            issues.append(f"Insecure file permissions. Expected 600, got {oct(file_stats.st_mode)[-3:]}")
        
        # Check file content
        try:
            secrets = cls.load_secrets_dict()
            if not secrets:
                issues.append("No secrets found in secrets file")
            
            # Check for common issues
            for key, value in secrets.items():
                if not key.isupper():
                    issues.append(f"Secret key '{key}' should be uppercase")
                if not re.match(r'^[A-Z_][A-Z0-9_]*$', key):
                    issues.append(f"Secret key '{key}' contains invalid characters")
                if len(value) < 4:
                    issues.append(f"Secret '{key}' is suspiciously short")
                    
        except Exception as e:
            issues.append(f"Error reading secrets file: {e}")
            
        return issues
    
    @classmethod
    def get_masked_secrets_dict(cls) -> Dict[str, str]:
        """Get secrets dictionary with values masked for display"""
        secrets = cls.load_secrets_dict()
        return {key: "***" for key in secrets.keys()}
    
    @classmethod
    def save_secret(cls, key: str, value: str) -> bool:
        """Save a secret to the secrets file"""
        if not key or not value:
            return False
            
        key = key.upper().strip()
        if not re.match(r'^[A-Z_][A-Z0-9_]*$', key):
            try:
                PrintStyle(background_color="red", font_color="white", padding=True).print(
                    f"Invalid secret key '{key}'. Use uppercase letters, numbers, and underscores only."
                )
            except:
                # Fallback for testing environments
                print(f"Invalid secret key '{key}'. Use uppercase letters, numbers, and underscores only.")
            return False
        
        secrets_path = files.get_abs_path(cls.SECRETS_FILE)
        
        # Read existing secrets
        existing_secrets = cls.load_secrets_dict()
        existing_secrets[key] = value
        
        # Write back to file
        try:
            os.makedirs(os.path.dirname(secrets_path), exist_ok=True)
            
            with open(secrets_path, 'w', encoding='utf-8') as f:
                f.write("# Agent Zero Secrets Configuration\n")
                f.write("# This file contains sensitive credentials that should never appear in prompts, logs, or front-end\n")
                f.write("# Use placeholder syntax §§SECRET_NAME§§ in your configurations\n\n")
                
                for k, v in existing_secrets.items():
                    f.write(f"{k}={v}\n")
            
            # Ensure proper permissions
            os.chmod(secrets_path, 0o600)
            
            # Clear cache to force reload
            cls._cache_loaded = False
            cls._secrets_cache = {}
            
            return True
            
        except Exception as e:
            try:
                PrintStyle(background_color="red", font_color="white", padding=True).print(
                    f"Error saving secret to {secrets_path}: {e}"
                )
            except:
                # Fallback for testing environments
                print(f"Error saving secret to {secrets_path}: {e}")
            return False
    
    @classmethod
    def delete_secret(cls, key: str) -> bool:
        """Delete a secret from the secrets file"""
        key = key.upper().strip()
        secrets_path = files.get_abs_path(cls.SECRETS_FILE)
        
        # Read existing secrets
        existing_secrets = cls.load_secrets_dict()
        
        if key not in existing_secrets:
            return False
            
        del existing_secrets[key]
        
        # Write back to file
        try:
            with open(secrets_path, 'w', encoding='utf-8') as f:
                f.write("# Agent Zero Secrets Configuration\n")
                f.write("# This file contains sensitive credentials that should never appear in prompts, logs, or front-end\n")
                f.write("# Use placeholder syntax §§SECRET_NAME§§ in your configurations\n\n")
                
                for k, v in existing_secrets.items():
                    f.write(f"{k}={v}\n")
            
            # Clear cache to force reload
            cls._cache_loaded = False
            cls._secrets_cache = {}
            
            return True
            
        except Exception as e:
            try:
                PrintStyle(background_color="red", font_color="white", padding=True).print(
                    f"Error deleting secret from {secrets_path}: {e}"
                )
            except:
                # Fallback for testing environments
                print(f"Error deleting secret from {secrets_path}: {e}")
            return False
    
    @classmethod
    def clear_cache(cls):
        """Clear the secrets cache to force reload"""
        cls._cache_loaded = False
        cls._secrets_cache = {}


# Convenience functions for backward compatibility
def load_secrets_dict() -> Dict[str, str]:
    """Load secrets from the secrets.env file"""
    return SecretsManager.load_secrets_dict()

def get_placeholder_keys() -> List[str]:
    """Get list of available secret keys for use in prompts"""
    return SecretsManager.get_placeholder_keys()

def replace_placeholders_in_text(text: str) -> str:
    """Replace §§SECRET_NAME§§ placeholders with actual values"""
    return SecretsManager.replace_placeholders_in_text(text)

def replace_placeholders_in_text_silent(text: str) -> str:
    """Replace §§SECRET_NAME§§ placeholders with actual values (no warnings for missing)"""
    return SecretsManager.replace_placeholders_in_text_silent(text)

def replace_placeholders_in_text_strict(text: str) -> str:
    """Replace §§SECRET_NAME§§ placeholders with actual values (raises RepairableException for missing)"""
    return SecretsManager.replace_placeholders_in_text_strict(text)

def replace_placeholders_in_dict(data: Dict[str, Any], strict: bool = True) -> Dict[str, Any]:
    """Recursively replace placeholders in dictionary values"""
    return SecretsManager.replace_placeholders_in_dict(data, strict=strict)

def replace_values_with_placeholders(text: str) -> str:
    """Replace actual secret values with placeholders for logging/display"""
    return SecretsManager.replace_values_with_placeholders(text)