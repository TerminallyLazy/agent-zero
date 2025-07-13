"""
Enhanced DrChrono OAuth2 Client with Dynamic Scope Management

Features:
- Web UI for scope selection and management
- Dynamic scope configuration
- Enhanced token management
- Integration with Agent Zero DrChrono tools
- Secure credential storage
"""

import requests
import json
import os
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode
from flask import Flask, redirect, url_for, request, jsonify, render_template_string, session
from typing import Dict, List, Optional, Any

# DrChrono OAuth2 Configuration
CLIENT_ID = os.environ.get('DRCHRONO_CLIENT_ID', '')
CLIENT_SECRET = os.environ.get('DRCHRONO_CLIENT_SECRET', '')
REDIRECT_URI = os.environ.get('DRCHRONO_REDIRECT_URI', 'http://localhost:8080/callback')
BASE_URL = 'https://drchrono.com'
TOKENS_FILE = 'drchrono_tokens.json'

# Available DrChrono API Scopes
AVAILABLE_SCOPES = {
    'user': {
        'user:read': 'Read user account information',
        'user:write': 'Modify user account information'
    },
    'calendar': {
        'calendar:read': 'Read appointment scheduling data',
        'calendar:write': 'Create and modify appointments'
    },
    'patients': {
        'patients:read': 'Read patient demographic and medical data',
        'patients:write': 'Create and modify patient records',
        'patients:summary:read': 'Read patient summary information'
    },
    'billing': {
        'billing:read': 'Read billing and payment information',
        'billing:write': 'Create and modify billing records'
    },
    'clinical': {
        'clinical:read': 'Read clinical notes and documentation',
        'clinical:write': 'Create and modify clinical documentation'
    },
    'labs': {
        'labs:read': 'Read laboratory results and orders',
        'labs:write': 'Create and modify lab orders'
    }
}

# Flask app setup
app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# Global variables
current_tokens = {}
selected_scopes = []

def load_tokens() -> Dict[str, Any]:
    """Load tokens from file"""
    try:
        with open(TOKENS_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_tokens(tokens: Dict[str, Any]) -> None:
    """Save tokens to file"""
    with open(TOKENS_FILE, 'w') as f:
        json.dump(tokens, f, indent=2, default=str)

def get_authorization_url(scopes: List[str]) -> str:
    """Generate DrChrono authorization URL"""
    params = {
        'client_id': CLIENT_ID,
        'response_type': 'code',
        'redirect_uri': REDIRECT_URI,
        'scope': ' '.join(scopes),
        'state': secrets.token_urlsafe(32)  # CSRF protection
    }
    session['oauth_state'] = params['state']
    return f"{BASE_URL}/o/authorize/?{urlencode(params)}"

def exchange_code_for_tokens(auth_code: str) -> Dict[str, Any]:
    """Exchange authorization code for access tokens"""
    data = {
        'code': auth_code,
        'grant_type': 'authorization_code',
        'redirect_uri': REDIRECT_URI,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET
    }
    
    response = requests.post(f'{BASE_URL}/o/token/', data=data)
    response.raise_for_status()
    
    token_data = response.json()
    
    # Add expiration timestamp
    expires_at = datetime.now() + timedelta(seconds=token_data['expires_in'])
    token_data['expires_at'] = expires_at.isoformat()
    
    return token_data

def refresh_access_token(refresh_token: str) -> Dict[str, Any]:
    """Refresh access token using refresh token"""
    data = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET
    }
    
    response = requests.post(f'{BASE_URL}/o/token/', data=data)
    response.raise_for_status()
    
    token_data = response.json()
    expires_at = datetime.now() + timedelta(seconds=token_data['expires_in'])
    token_data['expires_at'] = expires_at.isoformat()
    
    return token_data

def test_api_connection(access_token: str) -> Dict[str, Any]:
    """Test API connection with current token"""
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Accept': 'application/json'
    }
    
    response = requests.get(f'{BASE_URL}/api/users', headers=headers)
    
    return {
        'status_code': response.status_code,
        'success': response.status_code == 200,
        'data': response.json() if response.status_code == 200 else None,
        'error': response.text if response.status_code != 200 else None
    }

# Web UI Templates
HOME_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>DrChrono OAuth2 Manager</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .container { max-width: 800px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .header { text-align: center; color: #2c3e50; margin-bottom: 30px; }
        .scope-category { margin: 15px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }
        .scope-category h3 { margin-top: 0; color: #34495e; }
        .scope-item { margin: 8px 0; padding: 8px; background: #f8f9fa; border-radius: 3px; }
        .scope-item label { display: flex; align-items: center; cursor: pointer; }
        .scope-item input { margin-right: 10px; }
        .scope-description { font-size: 0.9em; color: #666; margin-left: 25px; }
        .button { background: #3498db; color: white; padding: 12px 24px; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; margin: 10px 5px; }
        .button:hover { background: #2980b9; }
        .button.success { background: #27ae60; }
        .button.danger { background: #e74c3c; }
        .status { padding: 15px; margin: 15px 0; border-radius: 5px; }
        .status.success { background: #d4edda; border: 1px solid #c3e6cb; color: #155724; }
        .status.error { background: #f8d7da; border: 1px solid #f5c6cb; color: #721c24; }
        .status.warning { background: #fff3cd; border: 1px solid #ffeaa7; color: #856404; }
        .token-info { background: #e9ecef; padding: 15px; border-radius: 5px; margin: 15px 0; }
        .config-section { margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }
        .form-group { margin: 10px 0; }
        .form-group label { display: block; margin-bottom: 5px; font-weight: bold; }
        .form-group input { width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 3px; }
        .hidden { display: none; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏥 DrChrono OAuth2 Manager</h1>
            <p>Enhanced OAuth2 client with dynamic scope management for Agent Zero integration</p>
        </div>

        <!-- Configuration Status -->
        <div class="config-section">
            <h3>Configuration Status</h3>
            {% if client_id and client_secret %}
            <div class="status success">
                ✅ OAuth credentials configured
            </div>
            {% else %}
            <div class="status error">
                ❌ OAuth credentials not configured. Set DRCHRONO_CLIENT_ID and DRCHRONO_CLIENT_SECRET environment variables.
            </div>
            {% endif %}
            
            <div class="form-group">
                <label>Client ID:</label>
                <input type="text" value="{{ client_id[:8] + '...' if client_id else 'Not configured' }}" readonly>
            </div>
            <div class="form-group">
                <label>Redirect URI:</label>
                <input type="text" value="{{ redirect_uri }}" readonly>
            </div>
        </div>

        <!-- Token Status -->
        {% if tokens %}
        <div class="token-info">
            <h3>Current Token Status</h3>
            <p><strong>Status:</strong> 
                {% if token_expired %}
                <span style="color: #e74c3c;">⚠️ Expired</span>
                {% else %}
                <span style="color: #27ae60;">✅ Valid</span>
                {% endif %}
            </p>
            <p><strong>Expires:</strong> {{ tokens.expires_at }}</p>
            <p><strong>Scopes:</strong> {{ tokens.scope }}</p>
            
            <button class="button" onclick="testConnection()">Test API Connection</button>
            <button class="button" onclick="refreshToken()">Refresh Token</button>
            <button class="button danger" onclick="revokeToken()">Revoke Token</button>
        </div>
        {% else %}
        <div class="status warning">
            No active tokens. Please authenticate with DrChrono.
        </div>
        {% endif %}

        <!-- Scope Selection -->
        <div class="config-section">
            <h3>Select API Scopes</h3>
            <p>Choose the permissions your application needs:</p>
            
            <form id="scopeForm">
                {% for category, scopes in available_scopes.items() %}
                <div class="scope-category">
                    <h3>{{ category.title() }} Permissions</h3>
                    {% for scope, description in scopes.items() %}
                    <div class="scope-item">
                        <label>
                            <input type="checkbox" name="scopes" value="{{ scope }}" 
                                   {% if scope in current_scopes %}checked{% endif %}>
                            <strong>{{ scope }}</strong>
                        </label>
                        <div class="scope-description">{{ description }}</div>
                    </div>
                    {% endfor %}
                </div>
                {% endfor %}
                
                <button type="button" class="button" onclick="selectAllScopes()">Select All</button>
                <button type="button" class="button" onclick="clearAllScopes()">Clear All</button>
                <button type="button" class="button success" onclick="authorize()">Authorize with Selected Scopes</button>
            </form>
        </div>

        <!-- API Testing -->
        <div class="config-section">
            <h3>API Testing</h3>
            <button class="button" onclick="testEndpoint('/api/users')">Test Users Endpoint</button>
            <button class="button" onclick="testEndpoint('/api/patients')">Test Patients Endpoint</button>
            <button class="button" onclick="testEndpoint('/api/appointments')">Test Appointments Endpoint</button>
            
            <div id="testResults" class="hidden">
                <h4>Test Results:</h4>
                <pre id="testOutput"></pre>
            </div>
        </div>

        <!-- Agent Zero Integration -->
        <div class="config-section">
            <h3>Agent Zero Integration</h3>
            <p>Copy the configuration below to integrate with Agent Zero DrChrono tools:</p>
            <button class="button" onclick="generateAgentConfig()">Generate Agent Zero Config</button>
            
            <div id="agentConfig" class="hidden">
                <h4>Agent Zero Configuration:</h4>
                <pre id="configOutput"></pre>
                <button class="button" onclick="copyConfig()">Copy to Clipboard</button>
            </div>
        </div>
    </div>

    <script>
        function selectAllScopes() {
            document.querySelectorAll('input[name="scopes"]').forEach(cb => cb.checked = true);
        }

        function clearAllScopes() {
            document.querySelectorAll('input[name="scopes"]').forEach(cb => cb.checked = false);
        }

        function authorize() {
            const selectedScopes = Array.from(document.querySelectorAll('input[name="scopes"]:checked'))
                .map(cb => cb.value);
            
            if (selectedScopes.length === 0) {
                alert('Please select at least one scope');
                return;
            }

            const params = new URLSearchParams();
            selectedScopes.forEach(scope => params.append('scopes', scope));
            
            window.location.href = '/authorize?' + params.toString();
        }

        function testConnection() {
            fetch('/test_connection')
                .then(response => response.json())
                .then(data => {
                    const status = data.success ? 'success' : 'error';
                    showMessage(`API Test ${data.success ? 'Successful' : 'Failed'}: ${JSON.stringify(data, null, 2)}`, status);
                })
                .catch(error => showMessage('Error testing connection: ' + error, 'error'));
        }

        function refreshToken() {
            fetch('/refresh_token', {method: 'POST'})
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        showMessage('Token refreshed successfully', 'success');
                        setTimeout(() => location.reload(), 1000);
                    } else {
                        showMessage('Failed to refresh token: ' + data.error, 'error');
                    }
                })
                .catch(error => showMessage('Error refreshing token: ' + error, 'error'));
        }

        function revokeToken() {
            if (confirm('Are you sure you want to revoke the current token?')) {
                fetch('/revoke_token', {method: 'POST'})
                    .then(response => response.json())
                    .then(data => {
                        showMessage('Token revoked successfully', 'success');
                        setTimeout(() => location.reload(), 1000);
                    })
                    .catch(error => showMessage('Error revoking token: ' + error, 'error'));
            }
        }

        function testEndpoint(endpoint) {
            fetch('/test_endpoint?endpoint=' + encodeURIComponent(endpoint))
                .then(response => response.json())
                .then(data => {
                    document.getElementById('testResults').classList.remove('hidden');
                    document.getElementById('testOutput').textContent = JSON.stringify(data, null, 2);
                })
                .catch(error => showMessage('Error testing endpoint: ' + error, 'error'));
        }

        function generateAgentConfig() {
            fetch('/agent_config')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('agentConfig').classList.remove('hidden');
                    document.getElementById('configOutput').textContent = JSON.stringify(data, null, 2);
                })
                .catch(error => showMessage('Error generating config: ' + error, 'error'));
        }

        function copyConfig() {
            const configText = document.getElementById('configOutput').textContent;
            navigator.clipboard.writeText(configText).then(() => {
                showMessage('Configuration copied to clipboard', 'success');
            });
        }

        function showMessage(message, type) {
            const messageDiv = document.createElement('div');
            messageDiv.className = `status ${type}`;
            messageDiv.textContent = message;
            document.querySelector('.container').insertBefore(messageDiv, document.querySelector('.container').firstChild);
            setTimeout(() => messageDiv.remove(), 5000);
        }
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    """Main dashboard"""
    global current_tokens
    current_tokens = load_tokens()
    
    # Check token expiration
    token_expired = False
    if current_tokens and 'expires_at' in current_tokens:
        try:
            expires_at = datetime.fromisoformat(current_tokens['expires_at'])
            token_expired = datetime.now() >= expires_at
        except:
            token_expired = True
    
    # Get current scopes
    current_scopes = []
    if current_tokens and 'scope' in current_tokens:
        current_scopes = current_tokens['scope'].split()
    
    return render_template_string(HOME_TEMPLATE,
                                client_id=CLIENT_ID,
                                client_secret=CLIENT_SECRET,
                                redirect_uri=REDIRECT_URI,
                                tokens=current_tokens,
                                token_expired=token_expired,
                                available_scopes=AVAILABLE_SCOPES,
                                current_scopes=current_scopes)

@app.route('/authorize')
def authorize():
    """Start OAuth authorization flow"""
    scopes = request.args.getlist('scopes')
    
    if not scopes:
        return jsonify({'error': 'No scopes selected'}), 400
    
    if not CLIENT_ID or not CLIENT_SECRET:
        return jsonify({'error': 'OAuth credentials not configured'}), 400
    
    auth_url = get_authorization_url(scopes)
    return redirect(auth_url)

@app.route('/callback')
def callback():
    """OAuth callback handler"""
    if 'error' in request.args:
        error_msg = request.args.get('error')
        return f'<h1>Authorization Failed</h1><p>{error_msg}</p><a href="/">Back to Home</a>'
    
    # Verify state parameter for CSRF protection
    state = request.args.get('state')
    if state != session.get('oauth_state'):
        return '<h1>Security Error</h1><p>Invalid state parameter</p><a href="/">Back to Home</a>'
    
    code = request.args.get('code')
    if not code:
        return '<h1>Error</h1><p>No authorization code received</p><a href="/">Back to Home</a>'
    
    try:
        tokens = exchange_code_for_tokens(code)
        save_tokens(tokens)
        
        return f'''
        <h1>✅ Authorization Successful!</h1>
        <p>Access token obtained and saved.</p>
        <p>Expires: {tokens.get('expires_at', 'Unknown')}</p>
        <p>Scopes: {tokens.get('scope', 'Unknown')}</p>
        <a href="/">Return to Dashboard</a>
        '''
    except Exception as e:
        return f'<h1>❌ Token Exchange Failed</h1><p>{str(e)}</p><a href="/">Back to Home</a>'

@app.route('/test_connection')
def test_connection_endpoint():
    """Test API connection"""
    tokens = load_tokens()
    
    if not tokens or 'access_token' not in tokens:
        return jsonify({'success': False, 'error': 'No access token available'})
    
    try:
        result = test_api_connection(tokens['access_token'])
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/refresh_token', methods=['POST'])
def refresh_token_endpoint():
    """Refresh access token"""
    tokens = load_tokens()
    
    if not tokens or 'refresh_token' not in tokens:
        return jsonify({'success': False, 'error': 'No refresh token available'})
    
    try:
        new_tokens = refresh_access_token(tokens['refresh_token'])
        # Preserve refresh token if not provided in response
        if 'refresh_token' not in new_tokens:
            new_tokens['refresh_token'] = tokens['refresh_token']
        
        save_tokens(new_tokens)
        return jsonify({'success': True, 'message': 'Token refreshed successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/revoke_token', methods=['POST'])
def revoke_token_endpoint():
    """Revoke access token"""
    try:
        # Clear local tokens
        if os.path.exists(TOKENS_FILE):
            os.remove(TOKENS_FILE)
        
        return jsonify({'success': True, 'message': 'Token revoked successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/test_endpoint')
def test_endpoint_route():
    """Test specific API endpoint"""
    endpoint = request.args.get('endpoint', '/api/users')
    tokens = load_tokens()
    
    if not tokens or 'access_token' not in tokens:
        return jsonify({'error': 'No access token available'})
    
    try:
        headers = {
            'Authorization': f"Bearer {tokens['access_token']}",
            'Accept': 'application/json'
        }
        
        response = requests.get(f"{BASE_URL}{endpoint}", headers=headers)
        
        return jsonify({
            'endpoint': endpoint,
            'status_code': response.status_code,
            'success': response.status_code == 200,
            'data': response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text,
            'headers': dict(response.headers)
        })
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/agent_config')
def agent_config():
    """Generate Agent Zero configuration"""
    tokens = load_tokens()
    
    config = {
        'drchrono_config': {
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'redirect_uri': REDIRECT_URI,
            'base_url': BASE_URL
        }
    }
    
    if tokens:
        config['drchrono_tokens'] = {
            'access_token': tokens.get('access_token'),
            'refresh_token': tokens.get('refresh_token'),
            'expires_at': tokens.get('expires_at'),
            'token_type': tokens.get('token_type', 'Bearer'),
            'scope': tokens.get('scope', '')
        }
    
    return jsonify(config)

def main():
    """Run the OAuth client"""
    print("🏥 DrChrono Enhanced OAuth2 Client")
    print("=" * 40)
    print(f"Client ID: {CLIENT_ID[:8] + '...' if CLIENT_ID else 'Not configured'}")
    print(f"Redirect URI: {REDIRECT_URI}")
    print(f"Available Scopes: {sum(len(scopes) for scopes in AVAILABLE_SCOPES.values())}")
    print()
    print("Starting web server on http://localhost:8080")
    print("Open your browser to begin OAuth configuration")
    print()
    
    app.run(host='0.0.0.0', port=8080, debug=True)

if __name__ == '__main__':
    main()