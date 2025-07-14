import json
import os
import uuid
import shutil
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypedDict
from dataclasses import asdict
import zipfile
import tempfile

from python.helpers import files, settings
from python.helpers.print_style import PrintStyle
from agent import AgentConfig


class ProfileConfig(TypedDict, total=False):
    id: str
    name: str
    description: str
    avatar: str
    created_at: str
    updated_at: str
    
    # Agent configuration overrides
    prompts_subdir: str
    memory_subdir: str
    knowledge_subdirs: List[str]
    
    # Model configurations (optional overrides)
    chat_model_overrides: Dict[str, Any]
    utility_model_overrides: Dict[str, Any]
    embedding_model_overrides: Dict[str, Any]
    browser_model_overrides: Dict[str, Any]
    
    # Custom components and file paths
    custom_tools: List[str]           # List of custom tool names/paths
    custom_extensions: List[str]      # List of extension names/paths
    custom_helpers: List[str]         # List of helper function names/paths
    
    # Profile file structure
    tools_dir: str                    # Custom tools directory path
    helpers_dir: str                  # Custom helpers directory path  
    extensions_dir: str               # Custom extensions directory path
    assets_dir: str                   # Profile assets directory path
    config_files: List[str]           # Configuration files for this profile
    
    # Advanced configuration
    environment_vars: Dict[str, str]  # Profile-specific environment variables
    dependencies: List[str]           # Required Python packages for this profile
    version: str                      # Profile version for compatibility
    author: str                       # Profile author/creator
    
    # Template source (for templates)
    is_template: bool
    template_source: str


class ProfileManager:
    """Manages agent profiles including creation, deletion, import/export"""
    
    def __init__(self):
        self.profiles_dir = files.get_abs_path("profiles")
        self.templates_dir = files.get_abs_path("profiles", "templates")
        self.active_profile_file = files.get_abs_path("tmp", "active_profile.json")
        self._ensure_directories()
        self._create_default_profile()
    
    def _ensure_directories(self):
        """Ensure profile directories exist"""
        os.makedirs(self.profiles_dir, exist_ok=True)
        os.makedirs(self.templates_dir, exist_ok=True)
        os.makedirs(files.get_abs_path("tmp"), exist_ok=True)
    
    def _create_default_profile(self):
        """Create default profile if it doesn't exist"""
        default_id = "default"
        if not self.profile_exists(default_id):
            current_settings = settings.get_settings()
            
            default_profile: ProfileConfig = {
                "id": default_id,
                "name": "Default",
                "description": "Default Agent Zero profile",
                "avatar": "🤖",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "prompts_subdir": current_settings.get("agent_prompts_subdir", ""),
                "memory_subdir": current_settings.get("agent_memory_subdir", ""),
                "knowledge_subdirs": ["default"],
                "chat_model_overrides": {},
                "utility_model_overrides": {},
                "embedding_model_overrides": {},
                "browser_model_overrides": {},
                "custom_tools": [],
                "custom_extensions": [],
                "custom_helpers": [],
                "tools_dir": "tools",
                "helpers_dir": "helpers", 
                "extensions_dir": "extensions",
                "assets_dir": "assets",
                "config_files": [],
                "environment_vars": {},
                "dependencies": [],
                "version": "1.0.0",
                "author": "Agent Zero",
                "is_template": False,
                "template_source": ""
            }
            
            self.create_profile(default_profile)
            self.set_active_profile(default_id)
    
    def profile_exists(self, profile_id: str) -> bool:
        """Check if a profile exists"""
        profile_path = files.get_abs_path(self.profiles_dir, profile_id)
        return os.path.exists(profile_path) and os.path.isdir(profile_path)
    
    def get_profile_path(self, profile_id: str) -> str:
        """Get the full path to a profile directory"""
        return files.get_abs_path(self.profiles_dir, profile_id)
    
    def get_profile_config_path(self, profile_id: str) -> str:
        """Get the path to a profile's config file"""
        return files.get_abs_path(self.get_profile_path(profile_id), "profile.json")
    
    def list_profiles(self) -> List[ProfileConfig]:
        """List all available profiles"""
        profiles = []
        
        if not os.path.exists(self.profiles_dir):
            return profiles
        
        for item in os.listdir(self.profiles_dir):
            # Skip templates directory - templates are loaded separately
            if item == "templates":
                continue
                
            profile_path = files.get_abs_path(self.profiles_dir, item)
            if os.path.isdir(profile_path):
                try:
                    profile = self.get_profile(item)
                    if profile:
                        profiles.append(profile)
                except Exception as e:
                    PrintStyle(font_color="orange", padding=True).print(
                        f"Warning: Could not load profile '{item}': {e}"
                    )
        
        # Sort by name
        profiles.sort(key=lambda p: p.get("name", ""))
        return profiles
    
    def get_profile(self, profile_id: str) -> Optional[ProfileConfig]:
        """Get a specific profile by ID"""
        if not self.profile_exists(profile_id):
            return None
        
        config_path = self.get_profile_config_path(profile_id)
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                profile_data = json.load(f)
            
            # Ensure all required fields are present
            profile: ProfileConfig = {
                "id": profile_data.get("id", profile_id),
                "name": profile_data.get("name", profile_id.title()),
                "description": profile_data.get("description", ""),
                "avatar": profile_data.get("avatar", "🤖"),
                "created_at": profile_data.get("created_at", datetime.now(timezone.utc).isoformat()),
                "updated_at": profile_data.get("updated_at", datetime.now(timezone.utc).isoformat()),
                "prompts_subdir": profile_data.get("prompts_subdir", ""),
                "memory_subdir": profile_data.get("memory_subdir", profile_id),
                "knowledge_subdirs": profile_data.get("knowledge_subdirs", ["default"]),
                "chat_model_overrides": profile_data.get("chat_model_overrides", {}),
                "utility_model_overrides": profile_data.get("utility_model_overrides", {}),
                "embedding_model_overrides": profile_data.get("embedding_model_overrides", {}),
                "browser_model_overrides": profile_data.get("browser_model_overrides", {}),
                "custom_tools": profile_data.get("custom_tools", []),
                "custom_extensions": profile_data.get("custom_extensions", []),
                "custom_helpers": profile_data.get("custom_helpers", []),
                "tools_dir": profile_data.get("tools_dir", "tools"),
                "helpers_dir": profile_data.get("helpers_dir", "helpers"),
                "extensions_dir": profile_data.get("extensions_dir", "extensions"),
                "assets_dir": profile_data.get("assets_dir", "assets"),
                "config_files": profile_data.get("config_files", []),
                "environment_vars": profile_data.get("environment_vars", {}),
                "dependencies": profile_data.get("dependencies", []),
                "version": profile_data.get("version", "1.0.0"),
                "author": profile_data.get("author", "Unknown"),
                "is_template": profile_data.get("is_template", False),
                "template_source": profile_data.get("template_source", "")
            }
            
            return profile
            
        except Exception as e:
            PrintStyle(font_color="red", padding=True).print(
                f"Error loading profile '{profile_id}': {e}"
            )
            return None
    
    def create_profile(self, profile_data: ProfileConfig) -> bool:
        """Create a new profile"""
        try:
            # Generate ID if not provided
            if not profile_data.get("id"):
                profile_data["id"] = str(uuid.uuid4())
            
            profile_id = profile_data["id"]
            
            # Check if profile already exists
            if self.profile_exists(profile_id):
                return False
            
            # Create profile directory
            profile_path = self.get_profile_path(profile_id)
            os.makedirs(profile_path, exist_ok=True)
            
            # Create comprehensive profile subdirectories
            subdirs = [
                "prompts",     # Custom prompts directory
                "knowledge",   # Knowledge base files
                "tools",       # Custom tools directory
                "helpers",     # Helper functions directory
                "extensions",  # Extensions directory
                "memory",      # Profile-specific memory
                "config",      # Configuration files
                "assets"       # Profile assets (images, etc.)
            ]
            
            for subdir in subdirs:
                os.makedirs(files.get_abs_path(profile_path, subdir), exist_ok=True)
            
            # Set timestamps
            now = datetime.now(timezone.utc).isoformat()
            profile_data["created_at"] = now
            profile_data["updated_at"] = now
            
            # Save profile config
            config_path = self.get_profile_config_path(profile_id)
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(profile_data, f, indent=2, ensure_ascii=False)
            
            PrintStyle(font_color="green", padding=True).print(
                f"Created profile '{profile_data.get('name', profile_id)}'"
            )
            return True
            
        except Exception as e:
            PrintStyle(font_color="red", padding=True).print(
                f"Error creating profile: {e}"
            )
            return False
    
    def update_profile(self, profile_id: str, profile_data: ProfileConfig) -> bool:
        """Update an existing profile"""
        try:
            if not self.profile_exists(profile_id):
                return False
            
            # Preserve ID and creation time
            existing_profile = self.get_profile(profile_id)
            if existing_profile:
                profile_data["id"] = profile_id
                profile_data["created_at"] = existing_profile.get("created_at", 
                                                                datetime.now(timezone.utc).isoformat())
            
            # Update timestamp
            profile_data["updated_at"] = datetime.now(timezone.utc).isoformat()
            
            # Save updated profile
            config_path = self.get_profile_config_path(profile_id)
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(profile_data, f, indent=2, ensure_ascii=False)
            
            return True
            
        except Exception as e:
            PrintStyle(font_color="red", padding=True).print(
                f"Error updating profile '{profile_id}': {e}"
            )
            return False
    
    def delete_profile(self, profile_id: str) -> bool:
        """Delete a profile"""
        try:
            # Don't allow deleting the default profile
            if profile_id == "default":
                return False
            
            if not self.profile_exists(profile_id):
                return False
            
            # If this is the active profile, switch to default
            if self.get_active_profile_id() == profile_id:
                self.set_active_profile("default")
            
            # Remove profile directory
            profile_path = self.get_profile_path(profile_id)
            shutil.rmtree(profile_path)
            
            PrintStyle(font_color="green", padding=True).print(
                f"Deleted profile '{profile_id}'"
            )
            return True
            
        except Exception as e:
            PrintStyle(font_color="red", padding=True).print(
                f"Error deleting profile '{profile_id}': {e}"
            )
            return False
    
    def get_active_profile_id(self) -> str:
        """Get the ID of the currently active profile"""
        try:
            if os.path.exists(self.active_profile_file):
                with open(self.active_profile_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get("active_profile", "default")
        except:
            pass
        return "default"
    
    def get_active_profile(self) -> Optional[ProfileConfig]:
        """Get the currently active profile"""
        active_id = self.get_active_profile_id()
        return self.get_profile(active_id)
    
    def set_active_profile(self, profile_id: str) -> bool:
        """Set the active profile"""
        try:
            if not self.profile_exists(profile_id):
                return False
            
            # Save active profile
            with open(self.active_profile_file, 'w', encoding='utf-8') as f:
                json.dump({"active_profile": profile_id}, f)
            
            return True
            
        except Exception as e:
            PrintStyle(font_color="red", padding=True).print(
                f"Error setting active profile '{profile_id}': {e}"
            )
            return False
    
    def export_profile(self, profile_id: str, export_path: str) -> bool:
        """Export a profile to a ZIP file"""
        try:
            if not self.profile_exists(profile_id):
                return False
            
            profile_path = self.get_profile_path(profile_id)
            
            with zipfile.ZipFile(export_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files_list in os.walk(profile_path):
                    for file in files_list:
                        file_path = os.path.join(root, file)
                        arc_path = os.path.relpath(file_path, profile_path)
                        zipf.write(file_path, arc_path)
            
            return True
            
        except Exception as e:
            PrintStyle(font_color="red", padding=True).print(
                f"Error exporting profile '{profile_id}': {e}"
            )
            return False
    
    def import_profile(self, zip_path: str, profile_id: Optional[str] = None) -> Optional[str]:
        """Import a profile from a ZIP file"""
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                # Extract ZIP to temporary directory
                with zipfile.ZipFile(zip_path, 'r') as zipf:
                    zipf.extractall(temp_dir)
                
                # Read profile config
                config_path = os.path.join(temp_dir, "profile.json")
                if not os.path.exists(config_path):
                    return None
                
                with open(config_path, 'r', encoding='utf-8') as f:
                    profile_data = json.load(f)
                
                # Generate new ID if needed or requested
                if profile_id:
                    profile_data["id"] = profile_id
                elif self.profile_exists(profile_data.get("id", "")):
                    profile_data["id"] = str(uuid.uuid4())
                
                imported_id = profile_data["id"]
                
                # Create profile directory
                profile_path = self.get_profile_path(imported_id)
                if os.path.exists(profile_path):
                    shutil.rmtree(profile_path)
                
                # Copy extracted files to profile directory
                shutil.copytree(temp_dir, profile_path)
                
                # Update timestamps
                profile_data["updated_at"] = datetime.now(timezone.utc).isoformat()
                
                # Save updated config
                with open(self.get_profile_config_path(imported_id), 'w', encoding='utf-8') as f:
                    json.dump(profile_data, f, indent=2, ensure_ascii=False)
                
                return imported_id
                
        except Exception as e:
            PrintStyle(font_color="red", padding=True).print(
                f"Error importing profile: {e}"
            )
            return None
    
    def validate_profile(self, profile_data: Dict[str, Any]) -> List[str]:
        """Validate profile data and return list of errors"""
        errors = []
        
        # Required fields
        if not profile_data.get("name"):
            errors.append("Profile name is required")
        
        if not profile_data.get("id"):
            errors.append("Profile ID is required")
        
        # Validate ID format
        profile_id = profile_data.get("id", "")
        if not re.match(r'^[a-zA-Z0-9_-]+$', profile_id):
            errors.append("Profile ID must contain only letters, numbers, underscores, and hyphens")
        
        return errors


# Global instance
_profile_manager = None

def get_profile_manager() -> ProfileManager:
    """Get the global profile manager instance"""
    global _profile_manager
    if _profile_manager is None:
        _profile_manager = ProfileManager()
    return _profile_manager