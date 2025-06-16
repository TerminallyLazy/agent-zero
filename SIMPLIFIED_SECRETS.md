# 🔐 Agent Zero Simplified Secrets Management

## What This Actually Does (Simplified)

The implementation provides a **simple placeholder substitution system** that:

1. **✅ Keeps .env file untouched** - no modifications to existing environment files
2. **✅ Uses /tmp/secrets.env** - separate file for actual secret values 
3. **✅ Includes placeholders in system prompt** - agent knows available secrets
4. **✅ Converts placeholders when tools run** - real values only during execution
5. **✅ Sanitizes logs automatically** - secret values replaced with placeholders

## Core Implementation

### 📁 **File Structure (Simple)**
```
.env                    # Your existing file - NEVER TOUCHED
tmp/secrets.env         # Real secrets stored here (600 permissions)
```

### 🔧 **Settings UI Integration**
- **Textarea field** for editing secrets in .env format
- **Values masked** with *** (never shows real values)
- **Saves to** `/tmp/secrets.env` automatically

### 🤖 **System Prompt Integration**
- **Auto-detects** available secrets from `/tmp/secrets.env`
- **Injects placeholders** into system prompt: `§§API_KEY_OPENAI§§`, `§§RFC_PASSWORD§§`
- **Provides instructions** for safe usage and special character handling

### 🛠️ **Tool Processing**
```python
# Tool receives placeholder
def some_tool(api_key="§§API_KEY_OPENAI§§"):
    # System automatically replaces with real value before execution
    client = SomeAPI(api_key=api_key)  # Gets actual key
    return "Connected successfully"
    # Response automatically sanitized for logging
```

### 📋 **Log Sanitization**
```python
# Log class automatically sanitizes all content
log.log(type="info", content="Using key: sk-proj-abc123...")
# Stored as: "Using key: §§API_KEY_OPENAI§§..."
```

## Key Classes

### **SecretsManager** (`python/helpers/secrets.py`)
```python
# Load secrets from /tmp/secrets.env
secrets = SecretsManager.load_secrets_dict()

# Get available keys for system prompt
keys = SecretsManager.get_placeholder_keys()

# Replace placeholders in tool arguments (strict mode)
processed = SecretsManager.replace_placeholders_in_dict(kwargs, strict=True)

# Sanitize output for logging
clean_text = SecretsManager.replace_values_with_placeholders(response)
```

### **Tool Base Class** (`python/helpers/tool.py`)
```python
class Tool:
    async def execute(self, **kwargs):
        # 1. Replace placeholders with real values
        processed_kwargs = SecretsManager.replace_placeholders_in_dict(kwargs)
        
        # 2. Execute tool implementation  
        response = await self._execute_impl(**processed_kwargs)
        
        # 3. Sanitize response for logging
        response.message = SecretsManager.replace_values_with_placeholders(response.message)
        
        return response
```

### **Log Class** (`python/helpers/log.py`)
```python
class Log:
    def _sanitize_content(self, content):
        # Automatically replace secret values with placeholders
        return SecretsManager.replace_values_with_placeholders(content)
    
    def log(self, type, content, **kwargs):
        # All log content automatically sanitized
        sanitized_content = self._sanitize_content(content)
        # ... create log item with sanitized content
```

## Usage Examples

### 🖥️ **Settings UI**
1. Go to Settings → Security → Secrets Management
2. Edit in textarea:
   ```
   API_KEY_OPENAI=***              # Keep existing
   API_KEY_ANTHROPIC=new-key       # Add/update
   RFC_PASSWORD=                   # Remove (empty)
   ```
3. Save → automatically updates `/tmp/secrets.env`

### 💬 **Agent Conversations**
```
User: "Use API key §§API_KEY_OPENAI§§ to generate an image"
Agent: [Receives placeholder in system prompt, uses real value in tools, logs show placeholder]
```

### 📊 **What Happens Behind the Scenes**
1. **System Prompt**: Lists available placeholders like `§§API_KEY_OPENAI§§`
2. **Tool Execution**: `§§API_KEY_OPENAI§§` → `sk-proj-real-key-here`
3. **Response Logging**: `sk-proj-real-key-here` → `§§API_KEY_OPENAI§§`

## Security Features

### 🛡️ **Complete Value Isolation**
- **Logs**: Only show placeholders, never real values
- **Frontend**: Settings show *** for all values  
- **System Prompts**: Agent only sees placeholder syntax
- **Tool Execution**: Real values only during execution moment
- **File Permissions**: `/tmp/secrets.env` has 600 permissions

### 🔐 **Error Handling**
- **Missing Secrets**: RepairableException with clear message
- **Invalid Placeholders**: Safe fallback behavior
- **File Permissions**: Automatic 600 permission setting

## CLI Management (Optional)

```bash
# List secrets (values masked)
python manage_secrets.py list

# Add new secret
python manage_secrets.py add NEW_SECRET "secret-value"

# Validate configuration
python manage_secrets.py validate
```

## The Bottom Line

This is a **minimal, focused implementation** that:

- ✅ **Never touches .env** - your existing file stays exactly as-is
- ✅ **Simple /tmp/secrets.env** - just key=value pairs with secure permissions
- ✅ **Automatic placeholder injection** - system prompt gets available secrets
- ✅ **Runtime substitution only** - real values only when tools execute
- ✅ **Complete log sanitization** - secret values never appear in logs

**No complex migration, no file watching, no .env manipulation** - just simple, secure placeholder substitution! 🎯