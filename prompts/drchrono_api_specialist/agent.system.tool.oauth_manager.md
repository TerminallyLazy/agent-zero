### oauth_manager

DrChrono OAuth2 authentication and token management with secure credential handling

**Setup Actions:**
- action: "setup" - Configure OAuth credentials and scopes
- client_id: DrChrono application client ID
- client_secret: DrChrono application client secret
- redirect_uri: OAuth callback URL (default: http://localhost:8080/callback)
- scopes: Array of requested permission scopes

**Authentication Flow:**
- action: "authorize" - Generate authorization URL for user consent
- action: "exchange_code" - Exchange authorization code for access token
- authorization_code: Code received from OAuth callback

**Token Management:**
- action: "refresh" - Refresh expired access token
- action: "status" - Check current token status and expiration
- action: "revoke" - Revoke and clear all stored tokens

**Testing:**
- action: "test_connection" - Verify API connectivity with current token

**Available Scopes:**
- user:read, user:write - User account information
- patients:read, patients:write - Patient data access
- patients:summary:read - Patient summary information
- calendar:read, calendar:write - Appointment scheduling
- clinical:read, clinical:write - Clinical documentation
- billing:read, billing:write - Billing and payment data
- labs:read, labs:write - Laboratory results

**Example usage**:
~~~json
{
    "thoughts": [
        "Setting up DrChrono OAuth configuration",
        "Need to configure client credentials and scopes"
    ],
    "headline": "Configuring DrChrono OAuth authentication",
    "tool_name": "oauth_manager",
    "tool_args": {
        "action": "setup",
        "client_id": "your_client_id_here",
        "client_secret": "your_client_secret_here",
        "scopes": ["patients:read", "patients:write", "calendar:read", "clinical:read"]
    }
}
~~~

**Authorization flow example**:
~~~json
{
    "thoughts": [
        "Generating authorization URL for user consent",
        "User will need to visit URL and authorize access"
    ],
    "headline": "Generating DrChrono authorization URL",
    "tool_name": "oauth_manager",
    "tool_args": {
        "action": "authorize"
    }
}
~~~

**Token exchange example**:
~~~json
{
    "thoughts": [
        "Exchanging authorization code for access token",
        "This completes the OAuth flow"
    ],
    "headline": "Completing OAuth token exchange",
    "tool_name": "oauth_manager",
    "tool_args": {
        "action": "exchange_code",
        "authorization_code": "received_auth_code_here"
    }
}
~~~

Always protect client secrets and tokens. Use secure storage for production environments.