"""
Eden API - EMR Connection Endpoints

POST /eden/emr_connect - Handle all EMR connection actions:
  - action: "connect" - Initiate OAuth flow
  - action: "callback" - OAuth callback handler
  - action: "sync" - Manual inbox sync
  - action: "status" - Check connection status
  - action: "disconnect" - Disconnect from EMR
  - action: "save_credentials" - Save API credentials
  - action: "get_credentials" - Get saved credentials (masked)
"""

from datetime import datetime
from typing import Optional
import os
import json
from pathlib import Path

try:
    from python.helpers.api import ApiHandler
except ImportError:
    class ApiHandler:
        @classmethod
        def requires_auth(cls) -> bool:
            return True

from python.helpers.eden.drchrono_client import (
    get_authorization_url,
    exchange_code_for_tokens,
    EDEN_SCOPES,
)
from python.helpers.eden.emr_adapter import get_adapter, DrChronoAdapter


# EMR credentials storage (in production, use secure storage)
_emr_credentials: dict = {}

# File path for persistent credential storage
CREDENTIALS_FILE = Path(__file__).parent.parent.parent.parent / ".eden_credentials.json"


def _load_saved_credentials() -> dict:
    """Load credentials from file if they exist."""
    if CREDENTIALS_FILE.exists():
        try:
            with open(CREDENTIALS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_credentials_to_file(creds: dict) -> bool:
    """Save credentials to file."""
    try:
        with open(CREDENTIALS_FILE, "w") as f:
            json.dump(creds, f)
        # Set restrictive permissions (owner read/write only)
        os.chmod(CREDENTIALS_FILE, 0o600)
        return True
    except Exception as e:
        print(f"Failed to save credentials: {e}")
        return False


class EMRConnectHandler(ApiHandler):
    """Handle EMR connection OAuth flow."""

    @classmethod
    def requires_auth(cls) -> bool:
        # Callback needs to be accessible without auth
        return False

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["GET", "POST"]

    async def process(self, input: dict, request) -> dict:
        """Route EMR connection requests."""
        action = input.get("action", "connect")

        if action == "connect":
            return await self._initiate_oauth(input)
        elif action == "callback":
            return await self._handle_callback(input)
        elif action == "sync":
            return await self._sync_inbox(input)
        elif action == "status":
            return await self._get_status()
        elif action == "disconnect":
            return await self._disconnect()
        elif action == "save_credentials":
            return await self._save_credentials(input)
        elif action == "get_credentials":
            return await self._get_credentials()

        return {"error": "Unknown action"}, 400

    async def _initiate_oauth(self, input: dict) -> dict:
        """Generate OAuth authorization URL."""
        # Try saved credentials first, then environment variables
        saved_creds = _load_saved_credentials()
        client_id = saved_creds.get("client_id") or os.environ.get("DRCHRONO_CLIENT_ID", "")
        redirect_uri = os.environ.get(
            "DRCHRONO_REDIRECT_URI",
            "http://localhost:50001/eden"  # OAuth callback handled by frontend
        )

        if not client_id:
            return {
                "error": "Dr. Chrono client ID not configured. Please enter your API credentials in Settings.",
                "setup_required": True,
            }

        auth_url = get_authorization_url(
            client_id=client_id,
            redirect_uri=redirect_uri,
            scopes=EDEN_SCOPES,
        )

        return {
            "authorization_url": auth_url,
            "message": "Redirect user to authorization URL",
        }

    async def _handle_callback(self, input: dict) -> dict:
        """Handle OAuth callback with authorization code."""
        code = input.get("code")
        error = input.get("error")

        if error:
            return {
                "error": f"OAuth error: {error}",
                "description": input.get("error_description", ""),
            }

        if not code:
            return {"error": "Authorization code required"}

        # Get OAuth config - try saved credentials first
        saved_creds = _load_saved_credentials()
        client_id = saved_creds.get("client_id") or os.environ.get("DRCHRONO_CLIENT_ID", "")
        client_secret = saved_creds.get("client_secret") or os.environ.get("DRCHRONO_CLIENT_SECRET", "")
        redirect_uri = os.environ.get(
            "DRCHRONO_REDIRECT_URI",
            "http://localhost:50001/eden"
        )

        try:
            credentials = await exchange_code_for_tokens(
                code=code,
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
            )

            # Store credentials
            global _emr_credentials
            _emr_credentials = {
                "access_token": credentials.access_token,
                "refresh_token": credentials.refresh_token,
                "expires_at": credentials.expires_at.isoformat(),
                "client_id": client_id,
                "client_secret": client_secret,
            }

            # Connect adapter
            adapter = get_adapter("drchrono")
            await adapter.connect(_emr_credentials)

            return {
                "success": True,
                "message": "Successfully connected to Dr. Chrono",
                "redirect": "/eden",  # Redirect back to Eden UI
            }

        except Exception as e:
            return {
                "error": f"Failed to exchange code: {str(e)}",
            }, 500

    async def _sync_inbox(self, input: dict) -> dict:
        """Manually trigger inbox sync."""
        global _emr_credentials

        if not _emr_credentials:
            return {"error": "EMR not connected"}, 400

        try:
            adapter = get_adapter("drchrono")

            # Ensure connected
            if not await adapter.is_connected():
                await adapter.connect(_emr_credentials)

            # Fetch inbox items
            since = input.get("since")  # Optional datetime filter
            items = await adapter.fetch_inbox_items(since=since)

            # Process into clusters
            from python.helpers.eden.clustering import ClusteringService
            service = ClusteringService.get_instance()
            clusters = await service.process_inbox_items(items)

            return {
                "success": True,
                "items_fetched": len(items),
                "clusters_updated": len(clusters),
                "message": f"Synced {len(items)} items into {len(clusters)} clusters",
            }

        except Exception as e:
            return {
                "error": f"Sync failed: {str(e)}",
            }, 500

    async def _get_status(self) -> dict:
        """Get EMR connection status."""
        global _emr_credentials

        if not _emr_credentials:
            return {
                "connected": False,
                "emr_type": None,
            }

        try:
            adapter = get_adapter("drchrono")
            is_connected = await adapter.is_connected()

            return {
                "connected": is_connected,
                "emr_type": "drchrono",
                "expires_at": _emr_credentials.get("expires_at"),
            }

        except Exception as e:
            return {
                "connected": False,
                "emr_type": "drchrono",
                "error": str(e),
            }

    async def _disconnect(self) -> dict:
        """Disconnect from EMR."""
        global _emr_credentials

        try:
            adapter = get_adapter("drchrono")
            await adapter.disconnect()
        except:
            pass

        _emr_credentials = {}

        return {
            "success": True,
            "message": "Disconnected from EMR",
        }

    async def _save_credentials(self, input: dict) -> dict:
        """Save API credentials to file."""
        client_id = input.get("client_id", "").strip()
        client_secret = input.get("client_secret", "").strip()

        if not client_id or not client_secret:
            return {"error": "Both client_id and client_secret are required"}

        # Don't save if it's the masked placeholder
        if client_secret.startswith("•"):
            # Keep existing secret, just update client_id
            existing = _load_saved_credentials()
            if existing.get("client_secret"):
                client_secret = existing["client_secret"]
            else:
                return {"error": "Please enter your actual client secret"}

        creds = {
            "client_id": client_id,
            "client_secret": client_secret,
        }

        if _save_credentials_to_file(creds):
            return {
                "success": True,
                "message": "Credentials saved successfully",
            }
        else:
            return {"error": "Failed to save credentials"}

    async def _get_credentials(self) -> dict:
        """Get saved credentials (with secret masked)."""
        saved = _load_saved_credentials()

        if not saved:
            return {
                "client_id": "",
                "has_secret": False,
            }

        return {
            "client_id": saved.get("client_id", ""),
            "has_secret": bool(saved.get("client_secret")),
        }


# Handler for /eden/emr_connect endpoint
EMRConnect = EMRConnectHandler
