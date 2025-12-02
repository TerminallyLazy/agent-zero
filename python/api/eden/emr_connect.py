"""
Eden API - EMR Connection Endpoints

POST /eden/emr/connect - Initiate OAuth flow
GET /eden/emr/callback - OAuth callback handler
POST /eden/emr/sync - Manual inbox sync
GET /eden/emr/status - Check connection status
"""

from datetime import datetime
from typing import Optional
import os

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

        return {"error": "Unknown action"}, 400

    async def _initiate_oauth(self, input: dict) -> dict:
        """Generate OAuth authorization URL."""
        # Get OAuth config from environment
        client_id = os.environ.get("DRCHRONO_CLIENT_ID", "")
        redirect_uri = os.environ.get(
            "DRCHRONO_REDIRECT_URI",
            "http://localhost:50001/eden/emr/callback"
        )

        if not client_id:
            return {
                "error": "Dr. Chrono client ID not configured",
                "setup_required": True,
            }, 400

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
            }, 400

        if not code:
            return {"error": "Authorization code required"}, 400

        # Get OAuth config
        client_id = os.environ.get("DRCHRONO_CLIENT_ID", "")
        client_secret = os.environ.get("DRCHRONO_CLIENT_SECRET", "")
        redirect_uri = os.environ.get(
            "DRCHRONO_REDIRECT_URI",
            "http://localhost:50001/eden/emr/callback"
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


# Handler for /eden/emr/* endpoints
EMRConnect = EMRConnectHandler
