"""
OAuth Manager Tool

Handles DrChrono OAuth2 authentication flow including:
- Authorization URL generation
- Token exchange and refresh
- Scope management
- Secure credential storage
"""

import json
import asyncio
import webbrowser
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from python.helpers.tool import Tool, Response
from python.helpers.drchrono_api import DrChronoConfig, TokenInfo
from python.helpers.errors import handle_error
from python.helpers.print_style import PrintStyle
import requests
from urllib.parse import urlencode


class OAuthManager(Tool):
    """OAuth2 authentication manager for DrChrono API"""
    
    async def execute(
        self,
        action: str = "",
        client_id: str = "",
        client_secret: str = "",
        redirect_uri: str = "http://localhost:8080/callback",
        scopes: Optional[List[str]] = None,
        authorization_code: str = "",
        **kwargs
    ) -> Response:
        """
        Manage DrChrono OAuth2 authentication
        
        Args:
            action: Action to perform (setup, authorize, exchange_code, refresh, status, revoke)
            client_id: DrChrono application client ID
            client_secret: DrChrono application client secret
            redirect_uri: OAuth redirect URI
            scopes: List of requested scopes
            authorization_code: Authorization code from OAuth callback
        """
        
        try:
            if action == "setup":
                return await self._setup_oauth_config(client_id, client_secret, redirect_uri, scopes)
            
            elif action == "authorize":
                return await self._generate_authorization_url()
            
            elif action == "exchange_code":
                if not authorization_code:
                    return Response(
                        message="Error: authorization_code required for exchange_code action",
                        break_loop=False
                    )
                return await self._exchange_authorization_code(authorization_code)
            
            elif action == "refresh":
                return await self._refresh_token()
            
            elif action == "status":
                return await self._get_token_status()
            
            elif action == "revoke":
                return await self._revoke_token()
            
            elif action == "test_connection":
                return await self._test_api_connection()
            
            else:
                return Response(
                    message=f"Error: Unknown action '{action}'. Available actions: setup, authorize, exchange_code, refresh, status, revoke, test_connection",
                    break_loop=False
                )
                
        except Exception as e:
            handle_error(e)
            return Response(
                message=f"OAuth Manager error: {str(e)}",
                break_loop=False
            )
    
    async def _setup_oauth_config(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        scopes: Optional[List[str]] = None
    ) -> Response:
        """Setup OAuth configuration"""
        
        if not client_id or not client_secret:
            return Response(
                message="Error: client_id and client_secret are required for setup",
                break_loop=False
            )
        
        default_scopes = [
            "user:read", "user:write",
            "patients:read", "patients:write", 
            "patients:summary:read",
            "calendar:read", "calendar:write",
            "clinical:read", "clinical:write",
            "billing:read", "billing:write",
            "labs:read", "labs:write"
        ]
        
        config_data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "scopes": scopes or default_scopes
        }
        
        # Store configuration in agent memory
        self.agent.set_data("drchrono_config", config_data)
        
        PrintStyle(font_color="#1B4F72").print("DrChrono OAuth configuration saved successfully")
        
        return Response(
            message=f"OAuth configuration setup complete:\n"
                   f"- Client ID: {client_id[:8]}...\n"
                   f"- Redirect URI: {redirect_uri}\n"
                   f"- Scopes: {', '.join(config_data['scopes'])}\n\n"
                   f"Next step: Use 'authorize' action to generate authorization URL",
            break_loop=False
        )
    
    async def _generate_authorization_url(self) -> Response:
        """Generate DrChrono authorization URL"""
        
        config_data = self.agent.get_data("drchrono_config")
        if not config_data:
            return Response(
                message="Error: OAuth configuration not found. Please run setup action first.",
                break_loop=False
            )
        
        params = {
            'client_id': config_data['client_id'],
            'response_type': 'code',
            'redirect_uri': config_data['redirect_uri'],
            'scope': ' '.join(config_data['scopes'])
        }
        
        auth_url = f"https://drchrono.com/o/authorize/?{urlencode(params)}"
        
        PrintStyle(font_color="#1B4F72").print("Generated DrChrono authorization URL")
        
        return Response(
            message=f"DrChrono Authorization URL:\n{auth_url}\n\n"
                   f"Instructions:\n"
                   f"1. Copy this URL and open it in your browser\n"
                   f"2. Log in to DrChrono and authorize the application\n"
                   f"3. You will be redirected to: {config_data['redirect_uri']}\n"
                   f"4. Copy the 'code' parameter from the redirect URL\n"
                   f"5. Use 'exchange_code' action with the authorization code\n\n"
                   f"Requested scopes: {', '.join(config_data['scopes'])}",
            break_loop=False
        )
    
    async def _exchange_authorization_code(self, authorization_code: str) -> Response:
        """Exchange authorization code for access token"""
        
        config_data = self.agent.get_data("drchrono_config")
        if not config_data:
            return Response(
                message="Error: OAuth configuration not found. Please run setup action first.",
                break_loop=False
            )
        
        token_data = {
            'code': authorization_code,
            'grant_type': 'authorization_code',
            'redirect_uri': config_data['redirect_uri'],
            'client_id': config_data['client_id'],
            'client_secret': config_data['client_secret']
        }
        
        try:
            response = requests.post('https://drchrono.com/o/token/', data=token_data)
            
            if response.status_code == 200:
                token_response = response.json()
                
                # Calculate expiration time
                expires_at = datetime.now() + timedelta(seconds=token_response['expires_in'])
                
                # Store token information
                token_info = {
                    "access_token": token_response['access_token'],
                    "refresh_token": token_response['refresh_token'],
                    "expires_at": expires_at.isoformat(),
                    "token_type": token_response.get('token_type', 'Bearer'),
                    "scope": token_response.get('scope', '')
                }
                
                self.agent.set_data("drchrono_tokens", token_info)
                
                PrintStyle(font_color="#1B4F72").print("Successfully obtained DrChrono access token")
                
                return Response(
                    message=f"OAuth token exchange successful!\n"
                           f"- Access token obtained and stored securely\n"
                           f"- Token expires at: {expires_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
                           f"- Granted scopes: {token_response.get('scope', 'Not specified')}\n\n"
                           f"You can now use DrChrono API operations. Use 'test_connection' to verify.",
                    break_loop=False
                )
            else:
                error_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
                return Response(
                    message=f"Token exchange failed (Status: {response.status_code}):\n{json.dumps(error_data, indent=2)}",
                    break_loop=False
                )
                
        except requests.RequestException as e:
            handle_error(e)
            return Response(
                message=f"Network error during token exchange: {str(e)}",
                break_loop=False
            )
    
    async def _refresh_token(self) -> Response:
        """Refresh the access token using refresh token"""
        
        config_data = self.agent.get_data("drchrono_config")
        token_data = self.agent.get_data("drchrono_tokens")
        
        if not config_data or not token_data:
            return Response(
                message="Error: OAuth configuration or tokens not found. Please authenticate first.",
                break_loop=False
            )
        
        refresh_data = {
            'grant_type': 'refresh_token',
            'refresh_token': token_data['refresh_token'],
            'client_id': config_data['client_id'],
            'client_secret': config_data['client_secret']
        }
        
        try:
            response = requests.post('https://drchrono.com/o/token/', data=refresh_data)
            
            if response.status_code == 200:
                token_response = response.json()
                
                # Calculate new expiration time
                expires_at = datetime.now() + timedelta(seconds=token_response['expires_in'])
                
                # Update token information
                updated_token_info = {
                    "access_token": token_response['access_token'],
                    "refresh_token": token_response.get('refresh_token', token_data['refresh_token']),
                    "expires_at": expires_at.isoformat(),
                    "token_type": token_response.get('token_type', 'Bearer'),
                    "scope": token_response.get('scope', token_data.get('scope', ''))
                }
                
                self.agent.set_data("drchrono_tokens", updated_token_info)
                
                PrintStyle(font_color="#1B4F72").print("Successfully refreshed DrChrono access token")
                
                return Response(
                    message=f"Token refresh successful!\n"
                           f"- New access token obtained\n"
                           f"- Token expires at: {expires_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
                           f"- Scopes: {token_response.get('scope', 'Not specified')}",
                    break_loop=False
                )
            else:
                error_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
                return Response(
                    message=f"Token refresh failed (Status: {response.status_code}):\n{json.dumps(error_data, indent=2)}",
                    break_loop=False
                )
                
        except requests.RequestException as e:
            handle_error(e)
            return Response(
                message=f"Network error during token refresh: {str(e)}",
                break_loop=False
            )
    
    async def _get_token_status(self) -> Response:
        """Get current token status"""
        
        config_data = self.agent.get_data("drchrono_config")
        token_data = self.agent.get_data("drchrono_tokens")
        
        if not config_data:
            return Response(
                message="OAuth Status: Not configured\nPlease run 'setup' action first.",
                break_loop=False
            )
        
        if not token_data:
            return Response(
                message="OAuth Status: Configured but not authenticated\n"
                       f"Client ID: {config_data['client_id'][:8]}...\n"
                       f"Scopes: {', '.join(config_data['scopes'])}\n\n"
                       f"Please run 'authorize' action to authenticate.",
                break_loop=False
            )
        
        # Check token expiration
        expires_at = datetime.fromisoformat(token_data['expires_at'])
        is_expired = datetime.now() >= expires_at
        time_remaining = expires_at - datetime.now()
        
        status = "EXPIRED" if is_expired else "VALID"
        
        return Response(
            message=f"OAuth Status: {status}\n"
                   f"Client ID: {config_data['client_id'][:8]}...\n"
                   f"Token expires at: {expires_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
                   f"Time remaining: {str(time_remaining).split('.')[0] if not is_expired else 'Expired'}\n"
                   f"Scopes: {token_data.get('scope', 'Not specified')}\n\n"
                   f"{'Token needs refresh!' if is_expired else 'Token is valid for API operations.'}",
            break_loop=False
        )
    
    async def _revoke_token(self) -> Response:
        """Revoke the current access token"""
        
        config_data = self.agent.get_data("drchrono_config")
        token_data = self.agent.get_data("drchrono_tokens")
        
        if not config_data or not token_data:
            return Response(
                message="Error: No active tokens to revoke.",
                break_loop=False
            )
        
        revoke_data = {
            'token': token_data['access_token'],
            'client_id': config_data['client_id'],
            'client_secret': config_data['client_secret']
        }
        
        try:
            response = requests.post('https://drchrono.com/o/revoke_token/', data=revoke_data)
            
            # Clear stored tokens regardless of response (token may already be invalid)
            self.agent.set_data("drchrono_tokens", None)
            
            PrintStyle(font_color="#1B4F72").print("DrChrono tokens revoked and cleared")
            
            return Response(
                message=f"Token revocation completed (Status: {response.status_code})\n"
                       f"All stored tokens have been cleared.\n"
                       f"You will need to re-authenticate to use DrChrono API.",
                break_loop=False
            )
            
        except requests.RequestException as e:
            # Clear tokens even if revocation request fails
            self.agent.set_data("drchrono_tokens", None)
            handle_error(e)
            return Response(
                message=f"Token revocation request failed, but local tokens cleared: {str(e)}",
                break_loop=False
            )
    
    async def _test_api_connection(self) -> Response:
        """Test API connection with current token"""
        
        token_data = self.agent.get_data("drchrono_tokens")
        if not token_data:
            return Response(
                message="Error: No authentication tokens found. Please authenticate first.",
                break_loop=False
            )
        
        try:
            headers = {
                'Authorization': f"Bearer {token_data['access_token']}",
                'Accept': 'application/json'
            }
            
            # Test with a simple API call
            response = requests.get('https://drchrono.com/api/users', headers=headers)
            
            if response.status_code == 200:
                user_data = response.json()
                return Response(
                    message=f"API Connection Test: SUCCESS\n"
                           f"- Status: {response.status_code}\n"
                           f"- Connected as user: {user_data.get('results', [{}])[0].get('username', 'Unknown') if user_data.get('results') else 'Unknown'}\n"
                           f"- API is ready for operations",
                    break_loop=False
                )
            elif response.status_code == 401:
                return Response(
                    message=f"API Connection Test: FAILED\n"
                           f"- Status: 401 Unauthorized\n"
                           f"- Token may be expired or invalid\n"
                           f"- Try refreshing the token or re-authenticating",
                    break_loop=False
                )
            else:
                return Response(
                    message=f"API Connection Test: FAILED\n"
                           f"- Status: {response.status_code}\n"
                           f"- Response: {response.text[:200]}...",
                    break_loop=False
                )
                
        except requests.RequestException as e:
            handle_error(e)
            return Response(
                message=f"API Connection Test: FAILED\n"
                       f"- Network error: {str(e)}",
                break_loop=False
            )


# Available OAuth scopes for DrChrono
AVAILABLE_SCOPES = {
    "user": ["user:read", "user:write"],
    "calendar": ["calendar:read", "calendar:write"], 
    "patients": ["patients:read", "patients:write", "patients:summary:read"],
    "billing": ["billing:read", "billing:write"],
    "clinical": ["clinical:read", "clinical:write"],
    "labs": ["labs:read", "labs:write"]
}