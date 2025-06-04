#!/usr/bin/env python3
"""
Validation script for MCP server configuration
Tests that the configuration in tmp/settings.json is properly formatted
"""

import json
import sys
from pathlib import Path

def validate_mcp_config():
    """Validate the MCP server configuration"""
    
    try:
        # Load settings
        settings_path = Path("tmp/settings.json")
        if not settings_path.exists():
            print("❌ Error: tmp/settings.json not found")
            return False
            
        with open(settings_path, 'r') as f:
            settings = json.load(f)
        
        # Check if mcp_servers key exists
        if "mcp_servers" not in settings:
            print("❌ Error: 'mcp_servers' key not found in settings")
            return False
            
        mcp_servers_str = settings["mcp_servers"]
        print(f"📄 Raw mcp_servers string length: {len(mcp_servers_str)} characters")
        
        # Parse the MCP servers JSON string
        try:
            mcp_servers = json.loads(mcp_servers_str)
        except json.JSONDecodeError as e:
            print(f"❌ Error: Failed to parse mcp_servers JSON: {e}")
            return False
            
        # Check if it's a list
        if not isinstance(mcp_servers, list):
            print(f"❌ Error: mcp_servers should be a list, got {type(mcp_servers)}")
            return False
            
        print(f"✅ Successfully parsed {len(mcp_servers)} MCP server configurations")
        
        # Validate each server config
        for i, server in enumerate(mcp_servers):
            print(f"\n🔍 Server {i+1}:")
            
            if not isinstance(server, dict):
                print(f"  ❌ Error: Server config should be a dict, got {type(server)}")
                continue
                
            # Check required fields
            name = server.get("name", "Unknown")
            print(f"  📛 Name: {name}")
            
            if "url" in server:
                # Remote SSE server
                url = server.get("url")
                print(f"  🌐 Type: Remote SSE Server")
                print(f"  🔗 URL: {url}")
                
                if url == "http://localhost:5000/mcp/sse":
                    print(f"  ✅ Found the requested MCP server!")
                    
            elif "command" in server:
                # Local stdio server
                command = server.get("command")
                args = server.get("args", [])
                print(f"  💻 Type: Local Stdio Server")
                print(f"  ⚡ Command: {command}")
                print(f"  📋 Args: {args}")
            else:
                print(f"  ❌ Error: Server missing both 'url' and 'command' fields")
                continue
                
            disabled = server.get("disabled", False)
            print(f"  🔄 Enabled: {not disabled}")
            
        return True
        
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    print("🔍 Validating MCP Server Configuration...")
    print("=" * 50)
    
    success = validate_mcp_config()
    
    print("\n" + "=" * 50)
    if success:
        print("✅ MCP configuration validation PASSED!")
        print("🚀 Ready to restart agent-zero to load the new configuration")
    else:
        print("❌ MCP configuration validation FAILED!")
        sys.exit(1) 