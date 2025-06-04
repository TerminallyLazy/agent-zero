#!/usr/bin/env python3
"""
Script to properly format and fix the MCP server configuration
"""

import json
from pathlib import Path
import os

def fix_mcp_config():
    """Fix and properly format the MCP server configuration"""
    
    # Define the MCP servers configuration as a proper Python data structure
    mcp_servers = [
        {
            "name": "filesystem",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/lazy/Downloads/", "/home/lazy/Projects/"],
            "disabled": False
        },
        {
            "name": "supabase", 
            "command": "npx",
            "args": ["-y", "@supabase/mcp-server-supabase@latest", "--access-token", ""],
            "disabled": False
        },
        {
            "name": "github",
            "command": "npx", 
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "env": {
                "GITHUB_PERSONAL_ACCESS_TOKEN": os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
            },
            "disabled": False
        },
        {
            "name": "21st_dev_magic",
            "command": "npx",
            "args": ["-y", "@21st-dev/magic@latest", "API_KEY="],
            "disabled": False
        },
        {
            "name": "desktop_commander", 
            "command": "npx",
            "args": ["@wonderwhy-er/desktop-commander@latest"],
            "disabled": False
        },
        {
            "name": "context7",
            "command": "npx",
            "args": ["-y", "@upstash/context7-mcp@latest"], 
            "disabled": False
        },
        {
            "name": "shadcn",
            "command": "npx",
            "args": ["-y", "shadcn@canary", "registry:mcp"],
            "env": {
                "REGISTRY_URL": "https://alpine-registry.vercel.app//r/registry.json"
            },
            "disabled": False
        },
        {
            "name": "local_mcp_server",
            "description": "Local MCP Server via SSE",
            "url": "http://localhost:5000/mcp/sse",
            "timeout": 5.0,
            "sse_read_timeout": 300.0,
            "disabled": False
        }
    ]
    
    # Convert to JSON string (this will be stored as the value)
    mcp_servers_json = json.dumps(mcp_servers)
    
    print("🔧 Generated MCP servers JSON:")
    print(mcp_servers_json)
    print(f"\n📏 Length: {len(mcp_servers_json)} characters")
    
    # Read current settings
    settings_path = Path("tmp/settings.json")
    with open(settings_path, 'r') as f:
        settings = json.load(f)
    
    # Update the mcp_servers field
    settings["mcp_servers"] = mcp_servers_json
    
    # Write back to file
    with open(settings_path, 'w') as f:
        json.dump(settings, f, indent=4)
    
    print(f"✅ Updated {settings_path}")
    
    # Validate the result
    print("\n🔍 Validating the updated configuration...")
    test_parse = json.loads(settings["mcp_servers"])
    print(f"✅ Successfully parsed {len(test_parse)} server configurations")
    
    # Show the new server specifically
    for server in test_parse:
        if server.get("name") == "local_mcp_server":
            print(f"\n🎯 Found the requested MCP server:")
            print(f"   Name: {server['name']}")
            print(f"   URL: {server['url']}")
            print(f"   Description: {server.get('description', 'N/A')}")
            print(f"   Enabled: {not server.get('disabled', False)}")
            break

if __name__ == "__main__":
    print("🔧 Fixing MCP Server Configuration...")
    print("=" * 50)
    fix_mcp_config()
    print("=" * 50)
    print("✅ MCP configuration fix completed!") 