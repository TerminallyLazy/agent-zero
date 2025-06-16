# Agent Zero Secrets Management - User Guide

## 🔐 What is Secrets Management?

Agent Zero's new Secrets Management system is a security enhancement that protects your sensitive information (API keys, passwords, tokens) while allowing the AI agent to use them when needed. Instead of exposing real credentials in conversations, logs, or the interface, the system uses special placeholders that get replaced with actual values only at runtime.

### The Problem This Solves

**Before**: You had to either:
- Hardcode API keys in your prompts (security risk)
- Manually replace credentials every time (tedious)
- Risk having sensitive data appear in logs and chat history

**After**: You can:
- Use safe placeholders like `§§API_KEY_OPENAI§§` in all your interactions
- Have real credentials automatically substituted when tools run
- Keep sensitive data completely out of logs and chat history

## 🎯 Key Benefits

### 🛡️ Security
- **No credential exposure**: Real values never appear in prompts, logs, or UI
- **Secure storage**: Credentials stored in protected file with 600 permissions
- **Automatic sanitization**: Tool responses are cleaned of sensitive data

### 🚀 Convenience  
- **One-time setup**: Configure credentials once, use everywhere
- **Automatic substitution**: No manual replacement needed
- **Persistent storage**: Credentials survive restarts and updates

### 🔄 Flexibility
- **Multiple providers**: Support for OpenAI, Anthropic, Google, and custom APIs
- **Easy management**: Add, update, or remove credentials through UI or files
- **Environment separation**: Different credentials for different setups

## 🏗️ How It Works

### The Placeholder System

The system uses a special syntax: `§§SECRET_NAME§§`

```
Your prompt: "Use API key §§API_KEY_OPENAI§§ to query the model"
What the tool receives: "Use API key sk-actual-secret-key-here to query the model"  
What appears in logs: "Use API key §§API_KEY_OPENAI§§ to query the model"
```

### The Process Flow

1. **Storage**: You save credentials in `/tmp/secrets.env`
2. **Usage**: You use placeholders like `§§API_KEY_OPENAI§§` in your requests
3. **Substitution**: Agent Zero replaces placeholders with real values before tool execution
4. **Protection**: Responses are sanitized to replace real values back to placeholders
5. **Logging**: Only placeholders appear in logs and chat history

## 📋 Quick Start Guide

### Step 1: Set Up Your First Secret

#### Option A: Through the Web UI
1. Open Agent Zero web interface
2. Go to **Settings** → **Security** → **Secrets Management**
3. Click **Manage Secrets**
4. Add your first API key

#### Option B: Direct File Edit
1. Open `/tmp/secrets.env` in a text editor
2. Add your credentials:
```env
API_KEY_OPENAI=sk-your-actual-openai-key-here
API_KEY_ANTHROPIC=your-anthropic-key-here
```
3. Save and ensure file has 600 permissions: `chmod 600 /tmp/secrets.env`

### Step 2: Use Placeholders in Your Requests

Instead of typing your actual API key, use the placeholder syntax:

```
"Write a Python script that uses OpenAI API with key §§API_KEY_OPENAI§§"
```

### Step 3: Verify It's Working

When you make a request, you should see:
- Your prompt shows the placeholder: `§§API_KEY_OPENAI§§`
- The tool executes successfully (meaning it got the real key)
- Any responses show placeholders, not actual keys

## 💡 Common Use Cases

### API Integration

**OpenAI API calls:**
```python
import openai
client = openai.OpenAI(api_key="§§API_KEY_OPENAI§§")
response = client.chat.completions.create(...)
```

**Multiple API providers:**
```python
# OpenAI
openai_client = OpenAI(api_key="§§API_KEY_OPENAI§§")

# Anthropic  
anthropic_client = Anthropic(api_key="§§API_KEY_ANTHROPIC§§")

# Google
genai.configure(api_key="§§API_KEY_GOOGLE§§")
```

### Database Connections

```python
import psycopg2
conn = psycopg2.connect(
    host="localhost",
    database="myapp", 
    user="postgres",
    password="§§DATABASE_PASSWORD§§"
)
```

### Web Services and APIs

```bash
# REST API calls
curl -H "Authorization: Bearer §§JWT_TOKEN§§" \
     https://api.example.com/data

# Environment setup
export API_SECRET="§§API_SECRET§§"
export DB_PASSWORD="§§DATABASE_PASSWORD§§"
```

### Docker and Configuration Files

```yaml
# docker-compose.yml
services:
  app:
    environment:
      - OPENAI_API_KEY=§§API_KEY_OPENAI§§
      - DATABASE_URL=postgres://user:§§DATABASE_PASSWORD§§@db:5432/app
```

## 🛠️ Management Guide

### Adding New Secrets

#### Method 1: Web Interface
1. Settings → Security → Secrets Management
2. Click "Manage Secrets"  
3. Enter key name (e.g., `API_KEY_CUSTOM`) and value
4. Save

#### Method 2: Direct File Edit
1. Edit `/tmp/secrets.env`
2. Add line: `NEW_SECRET_KEY=your-secret-value`
3. Save file

#### Method 3: Programmatic (Advanced)
```python
from python.helpers.secrets import SecretsManager
SecretsManager.save_secret("API_KEY_CUSTOM", "your-secret-value")
```

### Naming Conventions

**✅ Good Names:**
- `API_KEY_OPENAI`
- `DATABASE_PASSWORD`  
- `JWT_SECRET`
- `SMTP_PASSWORD`
- `WEBHOOK_SECRET`

**❌ Avoid:**
- `api_key` (not uppercase)
- `MY-SECRET` (hyphens not allowed)
- `123_KEY` (can't start with number)

### Updating Secrets

To change a secret value:
1. Edit `/tmp/secrets.env`
2. Update the value: `API_KEY_OPENAI=new-key-value`
3. Save file (Agent Zero will detect the change)

### Removing Secrets

#### Method 1: File Edit
1. Edit `/tmp/secrets.env`
2. Delete or comment out the line
3. Save file

#### Method 2: Programmatic
```python
from python.helpers.secrets import SecretsManager
SecretsManager.delete_secret("OLD_API_KEY")
```

## 🔍 Troubleshooting

### Common Issues

#### "Secret placeholder not found" Warning

**Problem**: You see `Warning: Secret placeholder §§MY_KEY§§ not found in secrets.env`

**Solutions**:
1. Check spelling: `§§MY_KEY§§` vs `§§MY_KEY§§` 
2. Verify the secret exists in `/tmp/secrets.env`
3. Ensure the key name is exactly uppercase: `MY_KEY` not `my_key`
4. Restart Agent Zero to reload secrets

#### Placeholder Not Being Replaced

**Problem**: You see `§§API_KEY§§` in tool execution instead of the actual key

**Solutions**:
1. Verify secret exists: `cat /tmp/secrets.env | grep API_KEY`
2. Check file permissions: `ls -la /tmp/secrets.env` (should be `-rw-------`)
3. Verify placeholder syntax: `§§SECRET_NAME§§` (note the special § characters)
4. Clear cache: restart Agent Zero

#### Permission Denied Errors

**Problem**: Can't read or write secrets file

**Solutions**:
1. Fix permissions: `chmod 600 /tmp/secrets.env`
2. Check ownership: `chown $USER /tmp/secrets.env`
3. Verify directory exists: `mkdir -p /tmp && chmod 755 /tmp`

#### Secrets Appearing in Logs

**Problem**: You see actual secret values in chat logs

**Solutions**:
1. Verify you're using latest Agent Zero version
2. Check that tools inherit from base Tool class properly
3. Report as a security issue if confirmed

### Validation and Health Checks

#### Check Secret Status
```python
from python.helpers.secrets import SecretsManager

# List available secrets
secrets = SecretsManager.get_placeholder_keys()
print(f"Available secrets: {secrets}")

# Validate configuration
issues = SecretsManager.validate_secrets_file()
if issues:
    print("Issues found:")
    for issue in issues:
        print(f"  - {issue}")
else:
    print("✅ All secrets configured correctly")
```

#### Test Placeholder Replacement
```python
# Test a placeholder
test_text = "API key: §§API_KEY_OPENAI§§"
result = SecretsManager.replace_placeholders_in_text(test_text)
print(f"Original: {test_text}")
print(f"Replaced: {result}")
```

## 🔐 Security Best Practices

### File Security

1. **Always use 600 permissions:**
   ```bash
   chmod 600 /tmp/secrets.env
   ```

2. **Verify ownership:**
   ```bash
   ls -la /tmp/secrets.env
   # Should show: -rw------- 1 yourusername yourusername
   ```

3. **Never commit the secrets file:**
   ```bash
   echo "/tmp/secrets.env" >> .gitignore
   ```

### Secret Management

1. **Use strong, unique secrets:**
   - Generate long, random API keys
   - Don't reuse passwords across services
   - Rotate secrets regularly

2. **Minimize secret scope:**
   - Use read-only API keys when possible
   - Limit API key permissions to needed functions
   - Create separate keys for different environments

3. **Monitor usage:**
   - Watch for "secret not found" warnings
   - Review API usage in provider dashboards
   - Set up alerts for unusual activity

### Environment Separation

**Development:**
```env
API_KEY_OPENAI=sk-dev-key-here
DATABASE_PASSWORD=dev_password
```

**Production:**
```env
API_KEY_OPENAI=sk-prod-key-here  
DATABASE_PASSWORD=strong_prod_password
```

## 📖 Reference Guide

### Placeholder Syntax

| Element | Description | Example |
|---------|-------------|---------|
| `§§` | Opening delimiter | `§§API_KEY§§` |
| `SECRET_NAME` | Your secret identifier | `API_KEY_OPENAI` |
| `§§` | Closing delimiter | `§§API_KEY§§` |

### Supported Secret Types

| Type | Example Name | Example Value |
|------|--------------|---------------|
| API Keys | `API_KEY_OPENAI` | `sk-proj-abc123...` |
| Passwords | `DATABASE_PASSWORD` | `mySecurePassword123` |
| Tokens | `JWT_SECRET` | `your-jwt-secret-here` |
| URLs | `DATABASE_URL` | `postgresql://user:pass@host:5432/db` |
| Custom | `WEBHOOK_SECRET` | `whsec_abc123...` |

### File Format

The `/tmp/secrets.env` file uses standard environment file format:

```env
# Comments start with #
# Format: KEY=value

# API Keys
API_KEY_OPENAI=sk-your-key-here
API_KEY_ANTHROPIC=your-anthropic-key

# Database credentials  
DATABASE_PASSWORD=your-db-password
DATABASE_URL=postgresql://user:password@localhost:5432/db

# Custom secrets
JWT_SECRET=your-jwt-secret
WEBHOOK_SECRET=whsec_your-webhook-secret

# Quoted values (for spaces or special characters)
COMPLEX_SECRET="value with spaces"
SINGLE_QUOTED='another value'
```

### Agent Integration Points

The secrets system integrates with Agent Zero at multiple levels:

1. **Tool Execution**: All tools automatically substitute placeholders
2. **Browser Agent**: Secrets injected as `sensitive_data` parameter  
3. **Code Execution**: Works in Python, Node.js, shell scripts
4. **System Prompts**: Agent knows about available secrets
5. **Settings UI**: Secrets management interface
6. **Memory System**: Only placeholders stored in conversation history

## 🎓 Advanced Usage

### Conditional Secrets

You can use different secrets based on context:

```python
# Development vs Production
api_key = "§§API_KEY_OPENAI_DEV§§" if env == "dev" else "§§API_KEY_OPENAI_PROD§§"

# Different models
anthropic_key = "§§API_KEY_ANTHROPIC§§"  
openai_key = "§§API_KEY_OPENAI§§"
```

### Complex Configurations

For complex setups, you can build configuration objects:

```python
config = {
    "openai": {
        "api_key": "§§API_KEY_OPENAI§§",
        "organization": "§§OPENAI_ORG_ID§§"
    },
    "database": {
        "url": "postgresql://user:§§DATABASE_PASSWORD§§@localhost:5432/app",
        "pool_size": 10
    },
    "redis": {
        "url": "redis://:§§REDIS_PASSWORD§§@localhost:6379/0"
    }
}
```

### Backup and Migration

**Backup your secrets:**
```bash
# Create encrypted backup
gpg --symmetric --cipher-algo AES256 /tmp/secrets.env
mv secrets.env.gpg ~/backups/
```

**Migrate between environments:**
```bash
# Export from old system
cp /old/path/secrets.env /tmp/secrets.env.backup

# Import to new system  
cp /tmp/secrets.env.backup /tmp/secrets.env
chmod 600 /tmp/secrets.env
```

### Integration with External Secret Managers

For enterprise use, you can integrate with external secret managers:

```python
# Example: AWS Secrets Manager integration
import boto3

def load_aws_secrets():
    client = boto3.client('secretsmanager')
    secret = client.get_secret_value(SecretId='agent-zero-secrets')
    return json.loads(secret['SecretString'])

# Update secrets file from external source
aws_secrets = load_aws_secrets()
for key, value in aws_secrets.items():
    SecretsManager.save_secret(key, value)
```

## ❓ FAQ

### General Questions

**Q: Are my secrets sent to external services?**
A: No. Secrets are only used locally within Agent Zero. They're substituted into tool arguments but never transmitted in API calls to Agent Zero's servers.

**Q: Can I see my actual secret values in the UI?**
A: No. The UI only shows masked values (`***`) for security. You can only see actual values by directly viewing the `/tmp/secrets.env` file.

**Q: What happens if I delete the secrets file?**
A: Agent Zero will create a new empty file automatically. You'll need to re-add your secrets.

### Technical Questions

**Q: How does this affect performance?**
A: Minimal impact. Secrets are cached in memory after first load, and placeholder replacement is very fast.

**Q: Can I use environment variables instead?**
A: You can, but the secrets system provides better security by keeping credentials out of process environments and system logs.

**Q: Is this compatible with Docker?**
A: Yes. Mount the `/tmp` directory to persist secrets across container restarts, or set them up in your container initialization.

### Security Questions

**Q: How secure is this system?**
A: Very secure when used properly:
- File permissions prevent other users from reading secrets
- Secrets never appear in logs or chat history  
- Memory usage is minimized and cached data is cleared on restart
- Placeholder syntax prevents accidental exposure

**Q: Can other applications access my secrets?**
A: Only if they run as the same user and you haven't properly set file permissions. Always use `chmod 600` on the secrets file.

**Q: What if someone gains access to my secrets file?**
A: They would have access to your credentials. This is why proper file permissions and system security are critical. Consider additional measures like disk encryption for highly sensitive environments.

## 🚀 Getting Started Checklist

### Initial Setup
- [ ] Verify Agent Zero is updated to v0.8.6+
- [ ] Create `/tmp/secrets.env` file
- [ ] Set proper permissions: `chmod 600 /tmp/secrets.env`
- [ ] Add your first API key
- [ ] Test with a simple placeholder replacement

### First Use
- [ ] Try a basic request with `§§API_KEY_OPENAI§§`
- [ ] Verify the tool executes successfully
- [ ] Check that logs show placeholders, not actual keys
- [ ] Add additional secrets as needed

### Ongoing Usage
- [ ] Regularly review and rotate secrets
- [ ] Monitor for "secret not found" warnings
- [ ] Keep backups of your secrets file (encrypted)
- [ ] Update documentation when adding new secrets

## 📞 Support and Resources

### Documentation
- **Technical Reference**: `/docs/secrets.md`
- **API Documentation**: See `SecretsManager` class in source code
- **Integration Examples**: Check `/tests/test_secrets_integration.py`

### Getting Help
- **GitHub Issues**: Report bugs or request features
- **Discord Community**: Get help from other users
- **Documentation**: Check the technical docs for advanced usage

### Contributing
The secrets management system is open source. Contributions are welcome for:
- Additional security features
- UI improvements
- Integration with external secret managers
- Documentation improvements

---

**🎉 Congratulations!** You now have a comprehensive understanding of Agent Zero's secrets management system. Start with basic API key management and gradually explore more advanced features as your needs grow.

Remember: Security is a shared responsibility. Follow best practices, keep your system updated, and never hesitate to ask for help if you're unsure about security implications.