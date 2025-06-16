"""
Migration and synchronization utilities for Agent Zero secrets management.
Handles the transition from direct .env credentials to placeholder-based system.
"""

import os
import re
from typing import Dict, List, Tuple, Set
from pathlib import Path
from python.helpers import files, dotenv
from python.helpers.secrets import SecretsManager
from python.helpers.print_style import PrintStyle


class SecretsMigration:
    """Handles migration from .env to secrets.env system"""
    
    # Common secret key patterns
    SECRET_PATTERNS = [
        r'^API_KEY_\w+$',
        r'^.*_API_KEY$',
        r'^.*_TOKEN$',
        r'^.*_SECRET$',
        r'^.*_PASSWORD$',
        r'^ROOT_PASSWORD$',
        r'^AUTH_LOGIN$',
        r'^AUTH_PASSWORD$',
        r'^RFC_PASSWORD$',
        r'^HF_TOKEN$',
    ]
    
    # Non-secret configuration patterns  
    NON_SECRET_PATTERNS = [
        r'^DEFAULT_USER_TIMEZONE$',
        r'^USE_CLOUDFLARE$',
        r'^WEB_UI_PORT$',
        r'^.*_BASE_URL$',
        r'^.*_ENDPOINT$',
        r'^.*_API_VERSION$',
        r'^TOKENIZERS_PARALLELISM$',
        r'^PYDEVD_.*$',
        r'^ANONYMIZED_TELEMETRY$',
        r'^OLLAMA_.*$',
        r'^LM_STUDIO_.*$',
    ]
    
    @classmethod
    def is_secret_key(cls, key: str) -> bool:
        """Determine if a key should be treated as a secret"""
        key = key.upper().strip()
        
        # Check non-secret patterns first
        for pattern in cls.NON_SECRET_PATTERNS:
            if re.match(pattern, key):
                return False
                
        # Check secret patterns
        for pattern in cls.SECRET_PATTERNS:
            if re.match(pattern, key):
                return True
                
        # If key contains common secret indicators
        secret_indicators = ['key', 'token', 'secret', 'password', 'auth', 'credential']
        key_lower = key.lower()
        for indicator in secret_indicators:
            if indicator in key_lower:
                return True
                
        return False
    
    @classmethod
    def extract_secrets_from_env(cls) -> Tuple[Dict[str, str], Dict[str, str]]:
        """Extract secrets and non-secrets from .env file"""
        env_path = files.get_abs_path(".env")
        secrets = {}
        non_secrets = {}
        
        if not os.path.exists(env_path):
            return secrets, non_secrets
        
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(env_path, 'r', encoding='latin-1') as f:
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
            
            # Remove quotes
            if (value.startswith('"') and value.endswith('"')) or \
               (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
            
            # Skip if it's already a placeholder
            if value.startswith('§§') and value.endswith('§§'):
                non_secrets[key] = value
                continue
                
            # Categorize as secret or non-secret
            if cls.is_secret_key(key) and value:  # Only secrets with actual values
                secrets[key] = value
            else:
                non_secrets[key] = value
                
        return secrets, non_secrets
    
    @classmethod
    def migrate_to_placeholder_system(cls, force: bool = False) -> Tuple[int, int]:
        """
        Migrate from direct .env credentials to placeholder system
        Returns: (secrets_migrated, placeholders_created)
        """
        if not force:
            # Check if migration is needed
            current_secrets = SecretsManager.load_secrets_dict()
            secrets_from_env, _ = cls.extract_secrets_from_env()
            
            # If we already have secrets and no raw secrets in .env, no migration needed
            if current_secrets and not any(
                not (v.startswith('§§') and v.endswith('§§')) 
                for v in secrets_from_env.values() if v
            ):
                return 0, 0
        
        PrintStyle(background_color="blue", font_color="white", padding=True).print(
            "🔄 Migrating to placeholder-based secrets system..."
        )
        
        # Extract secrets and non-secrets from .env
        secrets_from_env, non_secrets_from_env = cls.extract_secrets_from_env()
        
        # Load existing secrets
        existing_secrets = SecretsManager.load_secrets_dict()
        
        # Merge secrets (existing takes precedence)
        all_secrets = {**secrets_from_env, **existing_secrets}
        
        # Remove empty values
        all_secrets = {k: v for k, v in all_secrets.items() if v}
        
        secrets_migrated = 0
        if all_secrets:
            # Save merged secrets
            cls._save_secrets_file(all_secrets)
            secrets_migrated = len([k for k in secrets_from_env.keys() if k in all_secrets])
        
        # Update .env file with placeholders
        placeholders_created = cls._update_env_with_placeholders(all_secrets, non_secrets_from_env)
        
        PrintStyle(background_color="green", font_color="white", padding=True).print(
            f"✅ Migration complete: {secrets_migrated} secrets migrated, {placeholders_created} placeholders created"
        )
        
        return secrets_migrated, placeholders_created
    
    @classmethod
    def _save_secrets_file(cls, secrets: Dict[str, str]):
        """Save secrets to the secrets.env file"""
        secrets_path = files.get_abs_path(SecretsManager.SECRETS_FILE)
        
        # Create directory if needed
        os.makedirs(os.path.dirname(secrets_path), exist_ok=True)
        
        with open(secrets_path, 'w', encoding='utf-8') as f:
            f.write("# Agent Zero Secrets Configuration\n")
            f.write("# This file contains sensitive credentials that should never appear in prompts, logs, or front-end\n")
            f.write("# Use placeholder syntax §§SECRET_NAME§§ in your configurations\n\n")
            
            for key in sorted(secrets.keys()):
                value = secrets[key]
                f.write(f"{key}={value}\n")
        
        # Set secure permissions
        os.chmod(secrets_path, 0o600)
        
        # Clear cache
        SecretsManager.clear_cache()
    
    @classmethod
    def _update_env_with_placeholders(cls, secrets: Dict[str, str], non_secrets: Dict[str, str]) -> int:
        """Update .env file to use placeholders for secrets"""
        env_path = files.get_abs_path(".env")
        
        # Build new .env content
        lines = []
        lines.append("# Agent Zero Environment Configuration")
        lines.append("# Sensitive credentials now use placeholder substitution for security")
        lines.append("# Real values are stored in /tmp/secrets.env with secure permissions")
        lines.append("")
        
        placeholders_created = 0
        
        # Add secrets as placeholders
        secret_keys = sorted(secrets.keys())
        if secret_keys:
            lines.append("# API Keys and Sensitive Credentials (using placeholders)")
            for key in secret_keys:
                lines.append(f"{key}=§§{key}§§")
                placeholders_created += 1
            lines.append("")
        
        # Add non-secret configurations
        non_secret_keys = sorted(non_secrets.keys())
        if non_secret_keys:
            lines.append("# Configuration Settings")
            for key in non_secret_keys:
                value = non_secrets[key]
                # Handle multi-line values and special characters
                if "\n" in value:
                    value = f"'{value}'"
                elif " " in value or value == "" or any(c in value for c in "\"'"):
                    value = f'"{value}"'
                lines.append(f"{key}={value}")
        
        # Write the new .env file
        with open(env_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))
            f.write("\n")
        
        return placeholders_created
    
    @classmethod
    def sync_env_and_secrets(cls) -> Dict[str, str]:
        """
        Synchronize .env and secrets.env files
        Returns status report
        """
        report = {
            "secrets_found": 0,
            "placeholders_created": 0,
            "conflicts_resolved": 0,
            "status": "success"
        }
        
        try:
            # Get current state
            secrets_from_env, non_secrets_from_env = cls.extract_secrets_from_env()
            existing_secrets = SecretsManager.load_secrets_dict()
            
            # Find secrets that need to be moved from .env to secrets.env
            new_secrets = {}
            conflicts = 0
            
            for key, value in secrets_from_env.items():
                if not (value.startswith('§§') and value.endswith('§§')):
                    # This is a raw secret in .env
                    if key in existing_secrets and existing_secrets[key] != value:
                        # Conflict: different values
                        conflicts += 1
                        PrintStyle(background_color="yellow", font_color="black", padding=True).print(
                            f"⚠️ Conflict for {key}: keeping secrets.env value"
                        )
                    else:
                        new_secrets[key] = value
            
            if new_secrets:
                # Merge with existing secrets
                all_secrets = {**new_secrets, **existing_secrets}
                cls._save_secrets_file(all_secrets)
                
                # Update .env with placeholders
                placeholders_created = cls._update_env_with_placeholders(all_secrets, non_secrets_from_env)
                
                report.update({
                    "secrets_found": len(new_secrets),
                    "placeholders_created": placeholders_created,
                    "conflicts_resolved": conflicts
                })
                
                PrintStyle(background_color="green", font_color="white", padding=True).print(
                    f"🔄 Sync complete: {len(new_secrets)} secrets moved, {placeholders_created} placeholders updated"
                )
            
        except Exception as e:
            report.update({
                "status": "error",
                "error": str(e)
            })
            PrintStyle(background_color="red", font_color="white", padding=True).print(
                f"❌ Sync error: {e}"
            )
        
        return report
    
    @classmethod
    def validate_configuration(cls) -> Dict[str, any]:
        """Validate the current secrets configuration"""
        validation = {
            "env_file_exists": False,
            "secrets_file_exists": False,
            "secrets_file_permissions": None,
            "raw_secrets_in_env": [],
            "missing_placeholders": [],
            "orphaned_secrets": [],
            "status": "unknown"
        }
        
        try:
            env_path = files.get_abs_path(".env")
            secrets_path = files.get_abs_path(SecretsManager.SECRETS_FILE)
            
            validation["env_file_exists"] = os.path.exists(env_path)
            validation["secrets_file_exists"] = os.path.exists(secrets_path)
            
            if validation["secrets_file_exists"]:
                stat = os.stat(secrets_path)
                validation["secrets_file_permissions"] = oct(stat.st_mode)[-3:]
            
            # Check for raw secrets in .env
            if validation["env_file_exists"]:
                secrets_from_env, _ = cls.extract_secrets_from_env()
                for key, value in secrets_from_env.items():
                    if value and not (value.startswith('§§') and value.endswith('§§')):
                        validation["raw_secrets_in_env"].append(key)
            
            # Check for missing placeholders
            if validation["secrets_file_exists"]:
                existing_secrets = SecretsManager.load_secrets_dict()
                secrets_from_env, _ = cls.extract_secrets_from_env()
                
                for key in existing_secrets.keys():
                    if key not in secrets_from_env or secrets_from_env[key] != f"§§{key}§§":
                        validation["missing_placeholders"].append(key)
                
                for key in secrets_from_env.keys():
                    if (secrets_from_env[key].startswith('§§') and 
                        secrets_from_env[key].endswith('§§') and 
                        key not in existing_secrets):
                        validation["orphaned_secrets"].append(key)
            
            # Determine overall status
            if validation["raw_secrets_in_env"]:
                validation["status"] = "migration_needed"
            elif validation["missing_placeholders"] or validation["orphaned_secrets"]:
                validation["status"] = "sync_needed"  
            elif not validation["secrets_file_exists"]:
                validation["status"] = "setup_needed"
            else:
                validation["status"] = "healthy"
                
        except Exception as e:
            validation["status"] = "error"
            validation["error"] = str(e)
        
        return validation


def auto_migrate_if_needed():
    """Automatically migrate if raw secrets are detected in .env"""
    validation = SecretsMigration.validate_configuration()
    
    if validation["status"] == "migration_needed":
        PrintStyle(background_color="yellow", font_color="black", padding=True).print(
            "🔄 Raw secrets detected in .env file. Starting automatic migration..."
        )
        SecretsMigration.migrate_to_placeholder_system()
    elif validation["status"] == "sync_needed":
        PrintStyle(background_color="blue", font_color="white", padding=True).print(
            "🔄 Synchronizing .env and secrets.env files..."
        )
        SecretsMigration.sync_env_and_secrets()


if __name__ == "__main__":
    auto_migrate_if_needed()