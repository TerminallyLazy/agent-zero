# Secrets Management

Agent Zero includes a comprehensive secrets management system that prevents sensitive information from appearing in prompts, logs, or the front-end interface while ensuring tools and LiteLLM providers receive the actual values at runtime.

## Overview

The secrets management system uses placeholder substitution with the syntax `§§SECRET_NAME§§`. Real credentials are stored securely in `/tmp/secrets.env` and are automatically substituted at runtime when tools are executed.

### Key Features

- **Secure Storage**: Secrets are stored in `/tmp/secrets.env` with 600 permissions
- **Automatic Substitution**: Placeholders are replaced with actual values before tool execution
- **Log Protection**: Actual values are replaced with placeholders in tool responses and logs
- **UI Integration**: Secrets management section in the settings interface
- **Browser Agent Support**: Secrets are automatically injected into browser-use agents

## Configuration

### Secrets File Location

Secrets are stored in `/tmp/secrets.env` with the following format:

```env
# Agent Zero Secrets Configuration
API_KEY_OPENAI=sk-your-actual-openai-key-here
API_KEY_ANTHROPIC=your-anthropic-key-here
DATABASE_PASSWORD=your-database-password
JWT_SECRET=your-jwt-secret-key
```

### File Permissions

The secrets file must have 600 permissions (readable/writable by owner only):

```bash
chmod 600 /tmp/secrets.env
```

### Naming Conventions

Secret keys must:
- Use uppercase letters, numbers, and underscores only
- Start with a letter or underscore
- Be descriptive and follow the pattern `[CATEGORY]_[PURPOSE]`

Examples:
- `API_KEY_OPENAI`
- `DATABASE_PASSWORD`
- `JWT_SECRET`
- `SMTP_PASSWORD`

## Usage

### Placeholder Syntax

Use the syntax `§§SECRET_NAME§§` anywhere you need to reference a secret:

```json
{
  "tool_name": "code_execution_tool",
  "tool_args": {
    "language": "python",
    "code": "import openai\nclient = openai.OpenAI(api_key='§§API_KEY_OPENAI§§')"
  }
}
```

### In Code Execution

```python
# Python code using secrets
import openai
import psycopg2

# OpenAI client
client = openai.OpenAI(api_key="§§API_KEY_OPENAI§§")

# Database connection
conn = psycopg2.connect(
    host="localhost",
    database="mydb",
    user="username",
    password="§§DATABASE_PASSWORD§§"
)
```

### In Shell Commands

```bash
# Environment variables
export API_KEY="§§API_KEY_OPENAI§§"

# Direct usage
curl -H "Authorization: Bearer §§API_KEY_OPENAI§§" https://api.openai.com/v1/models
```

### JSON Escaping

When using secrets in JSON strings, ensure proper escaping:

```json
{
  "config": {
    "apiKey": "§§API_KEY_OPENAI§§",
    "password": "§§DATABASE_PASSWORD§§"
  }
}
```

## Security Features

### Runtime Substitution

- Placeholders are replaced with actual values only when tools execute
- Original tool arguments remain unchanged in logs
- Agent prompts never contain actual secret values

### Response Protection

Tool responses automatically have sensitive values replaced with placeholders:

```
Input:  "Connect with key §§API_KEY_OPENAI§§"
Output: "Connected successfully with key §§API_KEY_OPENAI§§"
```

### Browser Agent Integration

The browser agent automatically receives secrets as `sensitive_data`:

```python
browser_agent = browser_use.Agent(
    task=task,
    sensitive_data={
        "API_KEY_OPENAI": "sk-actual-key",
        "DATABASE_PASSWORD": "actual-password"
    }
)
```

## Management

### Web UI

Access secrets management through the settings interface:

1. Navigate to Settings → Security → Secrets Management
2. View masked secret keys (actual values are hidden)
3. Use the "Manage Secrets" button for configuration

### Programmatic Management

```python
from python.helpers.secrets import SecretsManager

# Save a new secret
SecretsManager.save_secret("NEW_API_KEY", "secret-value")

# Load all secrets
secrets = SecretsManager.load_secrets_dict()

# Get available keys for prompts
keys = SecretsManager.get_placeholder_keys()

# Validate secrets file
issues = SecretsManager.validate_secrets_file()
```

### Command Line

You can directly edit the secrets file:

```bash
# Edit secrets file
nano /tmp/secrets.env

# Verify permissions
ls -la /tmp/secrets.env
# Should show: -rw------- 1 user user ... /tmp/secrets.env
```

## System Prompt Integration

The agent automatically receives information about available secrets:

```markdown
## Available Secret Placeholders

The following secret keys are available for use:
- `§§API_KEY_OPENAI§§`
- `§§DATABASE_PASSWORD§§`
- `§§JWT_SECRET§§`

## Usage Guidelines
Use the placeholder syntax §§SECRET_NAME§§ in tool arguments...
```

## Best Practices

### Security

1. **Never commit actual secrets**: Always use placeholders in code and configurations
2. **Rotate secrets regularly**: Update secrets in the secrets file and restart Agent Zero
3. **Monitor file permissions**: Ensure `/tmp/secrets.env` always has 600 permissions
4. **Use descriptive names**: Make secret keys self-documenting

### Development

1. **Use placeholders consistently**: Don't mix actual values and placeholders
2. **Test with dummy values**: Use fake secrets during development and testing
3. **Document secret requirements**: List required secrets in project documentation
4. **Validate on startup**: Check that all required secrets are available

### Deployment

1. **Secure the secrets file**: Ensure proper file permissions in production
2. **Backup secrets safely**: Use encrypted backups for the secrets file
3. **Monitor secret usage**: Watch logs for missing secret warnings
4. **Environment separation**: Use different secrets for development/staging/production

## Validation

The system includes comprehensive validation:

### File Validation

```python
issues = SecretsManager.validate_secrets_file()
for issue in issues:
    print(f"Issue: {issue}")
```

Common validation issues:
- Insecure file permissions (not 600)
- Secret keys not in uppercase
- Invalid characters in key names
- Suspiciously short secret values
- Malformed key=value pairs

### Runtime Validation

- Missing secrets log warnings but don't cause failures
- Invalid key names are rejected when saving
- Empty or None values are filtered out

## API Reference

### SecretsManager Class

#### Core Methods

```python
# Load secrets from file
secrets = SecretsManager.load_secrets_dict()

# Get list of available secret keys
keys = SecretsManager.get_placeholder_keys()

# Replace placeholders with actual values
text = SecretsManager.replace_placeholders_in_text("Key: §§API_KEY§§")
data = SecretsManager.replace_placeholders_in_dict({"key": "§§API_KEY§§"})

# Replace actual values with placeholders (for logging)
safe_text = SecretsManager.replace_values_with_placeholders("Key: sk-actual")
```

#### Management Methods

```python
# Save a secret
success = SecretsManager.save_secret("NEW_KEY", "value")

# Delete a secret
success = SecretsManager.delete_secret("OLD_KEY")

# Get masked secrets for display
masked = SecretsManager.get_masked_secrets_dict()

# Validate secrets file
issues = SecretsManager.validate_secrets_file()

# Clear cache (force reload)
SecretsManager.clear_cache()
```

### Tool Integration

All tools automatically support secrets through the base Tool class:

```python
class MyTool(Tool):
    async def _execute_impl(self, **kwargs):
        # kwargs already have placeholders replaced with actual values
        api_key = kwargs.get("api_key")  # This is the actual secret value
        
        # Tool response messages are automatically scrubbed
        return Response(
            message=f"Used API key: {api_key}",  # Will be sanitized in logs
            break_loop=False
        )
```

## Troubleshooting

### Common Issues

**Placeholder not replaced**
- Check that the secret exists in `/tmp/secrets.env`
- Verify the key name matches exactly (case-sensitive)
- Ensure proper placeholder syntax: `§§KEY_NAME§§`

**Permission denied errors**
- Check file permissions: `chmod 600 /tmp/secrets.env`
- Ensure the file is owned by the correct user

**Secrets appearing in logs**
- Verify tool inheritance from base Tool class
- Check that `_execute_impl` is used instead of `execute`
- Ensure response message sanitization is working

**Missing secrets warnings**
- Add missing secrets to `/tmp/secrets.env`
- Clear cache: `SecretsManager.clear_cache()`
- Restart Agent Zero if necessary

### Debug Commands

```python
# Check if secrets are loaded
from python.helpers.secrets import SecretsManager
print(SecretsManager.load_secrets_dict().keys())

# Test placeholder replacement
text = "Test: §§API_KEY_OPENAI§§"
result = SecretsManager.replace_placeholders_in_text(text)
print(f"Original: {text}")
print(f"Replaced: {result}")

# Validate configuration
issues = SecretsManager.validate_secrets_file()
if issues:
    print("Issues found:")
    for issue in issues:
        print(f"  - {issue}")
else:
    print("No issues found")
```

## Migration Guide

### From Environment Variables

If you're currently using environment variables for secrets:

1. **Identify secrets**: List all sensitive environment variables
2. **Create secrets file**: Add them to `/tmp/secrets.env`
3. **Update configurations**: Replace environment variable references with placeholders
4. **Test substitution**: Verify placeholders are replaced correctly
5. **Remove env vars**: Clean up old environment variables

Example migration:

```bash
# Old approach
export OPENAI_API_KEY="sk-actual-key"

# New approach in /tmp/secrets.env
API_KEY_OPENAI=sk-actual-key

# Update code from:
os.getenv("OPENAI_API_KEY")

# To use placeholder in tool args:
"api_key": "§§API_KEY_OPENAI§§"
```

### From Hardcoded Values

1. **Identify hardcoded secrets**: Search for API keys, passwords, tokens
2. **Extract to secrets file**: Move values to `/tmp/secrets.env`
3. **Replace with placeholders**: Use `§§SECRET_NAME§§` syntax
4. **Test functionality**: Ensure tools still work correctly
5. **Remove hardcoded values**: Clean up old references

## Changelog

### v0.8.6 - Secrets Management
- Added comprehensive secrets management system
- Implemented placeholder substitution with `§§SECRET_NAME§§` syntax
- Added secure storage in `/tmp/secrets.env` with 600 permissions
- Integrated with tool execution pipeline for automatic substitution
- Added response sanitization to prevent secrets from appearing in logs
- Created settings UI for secrets management
- Added browser agent integration with `sensitive_data` parameter
- Included system prompt extension for secrets information
- Added comprehensive unit and integration tests
- Created detailed documentation and migration guide