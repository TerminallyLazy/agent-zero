"""
API handler for EdgeQuake plugin settings.

Actions:
- load: Read current settings (API key masked)
- save: Validate and persist settings
- test: Test connection with provided (unsaved) settings
- generate_key: Generate a new random API key
- start_server: Start EdgeQuake Docker Compose stack
- stop_server: Stop EdgeQuake Docker Compose stack
- server_status: Check container and health status
"""

from flask import Request
from python.helpers.api import ApiHandler, Input, Output

def _coerce_bool(v, default=False):
    """Safely coerce a value to bool, handling string 'false'."""
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.lower() not in ("false", "0", "no", "")
    return bool(v) if v is not None else default


ALLOWED_KEYS = {
    "base_url", "api_key", "workspace_id", "tenant_id", "timeout",
    "auto_index", "index_batch_size", "auto_recall", "recall_timeout",
}


class EdgequakeSettings(ApiHandler):

    async def process(self, input: Input, request: Request) -> Output:
        action = input.get("action", "load")

        if action == "load":
            return self._load()
        elif action == "save":
            return self._save(input.get("settings", {}))
        elif action == "test":
            return self._test(input.get("settings", {}))
        elif action == "generate_key":
            return self._generate_key()
        elif action == "start_server":
            return self._start_server(input.get("settings", {}))
        elif action == "stop_server":
            return self._stop_server()
        elif action == "server_status":
            return self._server_status()
        else:
            return {"error": f"Unknown action: {action}"}

    def _load(self) -> dict:
        from plugins.edgequake.helpers.edgequake_client import get_edgequake_settings

        settings = get_edgequake_settings()
        # Mask API key for display
        api_key = settings.get("api_key", "")
        if api_key and len(api_key) > 4:
            settings["api_key"] = "****" + api_key[-4:]
        elif api_key:
            settings["api_key"] = "****"
        return {"settings": settings}

    def _save(self, settings: dict) -> dict:
        from plugins.edgequake.helpers.edgequake_client import (
            get_edgequake_settings,
            save_edgequake_settings,
        )

        if not settings:
            return {"error": "No settings provided"}

        # Only accept known settings keys
        settings = {k: v for k, v in settings.items() if k in ALLOWED_KEYS}

        # Merge with existing — if API key is masked, keep the original
        current = get_edgequake_settings()
        api_key = settings.get("api_key", "").strip()
        if api_key.startswith("****") or not api_key:
            settings["api_key"] = current.get("api_key", "")

        # Validate base_url
        base_url = settings.get("base_url", "").strip()
        if not base_url:
            settings["base_url"] = "http://localhost:8080"

        # Ensure timeout is an int
        try:
            settings["timeout"] = int(settings.get("timeout", 30))
        except (ValueError, TypeError):
            settings["timeout"] = 30

        # Coerce Phase 3 settings types
        settings["auto_index"] = _coerce_bool(settings.get("auto_index", False))
        try:
            settings["index_batch_size"] = int(settings.get("index_batch_size", 5))
        except (ValueError, TypeError):
            settings["index_batch_size"] = 5
        settings["auto_recall"] = _coerce_bool(settings.get("auto_recall", False))
        try:
            settings["recall_timeout"] = int(settings.get("recall_timeout", 3))
        except (ValueError, TypeError):
            settings["recall_timeout"] = 3

        save_edgequake_settings(settings)
        self._write_docker_env(settings)
        return {"success": True}

    def _write_docker_env(self, settings: dict) -> None:
        """Write .env file for docker-compose.yml env var interpolation.

        Reads the LLM provider and API key from Agent Zero's main settings
        so EdgeQuake uses the same model configuration automatically.

        EdgeQuake expects:
        - EDGEQUAKE_DEFAULT_LLM_PROVIDER / EDGEQUAKE_DEFAULT_LLM_MODEL
        - EDGEQUAKE_DEFAULT_EMBEDDING_PROVIDER / MODEL / DIMENSION
        - Provider-specific API keys: OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.
        """
        import os
        import models
        from python.helpers.files import get_abs_path
        from python.helpers.settings import get_settings as get_a0_settings

        a0 = get_a0_settings()
        # Use chat model provider by default; fall back to util
        provider = a0.get("chat_model_provider", "") or a0.get("util_model_provider", "openai")
        model_name = a0.get("chat_model_name", "") or a0.get("util_model_name", "")
        api_key = models.get_api_key(provider)
        if not api_key or api_key == "None":
            api_key = a0.get("api_keys", {}).get(provider, "")

        # Map A0 provider names to EdgeQuake provider IDs
        provider_map = {
            "openai": "openai",
            "anthropic": "anthropic",
            "google": "gemini",
            "openrouter": "openrouter",
            "groq": "openai",  # Groq uses OpenAI-compatible API
            "ollama": "ollama",
            "lmstudio": "lmstudio",
        }
        eq_provider = provider_map.get(provider, "openai")

        # Map A0 provider to the env var EdgeQuake reads for the API key
        api_key_var_map = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "gemini": "GEMINI_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
            "ollama": "OLLAMA_HOST",
            "lmstudio": "LMSTUDIO_HOST",
        }
        api_key_var = api_key_var_map.get(eq_provider, "OPENAI_API_KEY")

        # Embedding defaults per provider
        embedding_defaults = {
            "openai": ("openai", "text-embedding-3-small", "1536"),
            "anthropic": ("openai", "text-embedding-3-small", "1536"),  # Anthropic has no embeddings
            "gemini": ("gemini", "gemini-embedding-001", "3072"),
            "openrouter": ("openai", "text-embedding-3-small", "1536"),
            "ollama": ("ollama", "embeddinggemma:latest", "768"),
            "lmstudio": ("lmstudio", "nomic-embed-text-v1.5", "768"),
        }
        emb_provider, emb_model, emb_dim = embedding_defaults.get(
            eq_provider, ("openai", "text-embedding-3-small", "1536")
        )

        # For Groq or OpenRouter through OpenAI-compatible, pass API base
        api_base = a0.get("chat_model_api_base", "") or ""

        env_path = get_abs_path("plugins/edgequake/docker/.env")
        safe_key = api_key if api_key and api_key != "None" else ""
        lines = [
            f"EDGEQUAKE_API_KEY={settings.get('api_key', '')}",
            f"# LLM provider selection",
            f"EDGEQUAKE_DEFAULT_LLM_PROVIDER={eq_provider}",
            f"EDGEQUAKE_DEFAULT_LLM_MODEL={model_name}",
            f"# Embedding provider",
            f"EDGEQUAKE_DEFAULT_EMBEDDING_PROVIDER={emb_provider}",
            f"EDGEQUAKE_DEFAULT_EMBEDDING_MODEL={emb_model}",
            f"EDGEQUAKE_DEFAULT_EMBEDDING_DIMENSION={emb_dim}",
            f"# Provider API key",
            f"{api_key_var}={safe_key}",
        ]
        # For OpenAI-compatible providers that aren't native OpenAI
        if api_base and eq_provider == "openai" and provider != "openai":
            lines.append(f"OPENAI_API_BASE={api_base}")
        # If using OpenRouter, also set OPENAI_API_KEY for embedding fallback
        if eq_provider == "openrouter" and safe_key:
            lines.append(f"# OpenRouter needs separate embedding; using OpenAI if available")
            openai_key = models.get_api_key("openai") or ""
            if openai_key and openai_key != "None":
                lines.append(f"OPENAI_API_KEY={openai_key}")

        try:
            os.makedirs(os.path.dirname(env_path), exist_ok=True)
            with open(env_path, "w") as f:
                f.write("\n".join(lines) + "\n")
        except Exception:
            pass  # Non-critical — user can still set env vars manually

    def _test(self, settings: dict) -> dict:
        from plugins.edgequake.helpers.edgequake_client import (
            get_edgequake_settings,
            test_connection,
        )

        if not settings:
            return {"error": "No settings provided"}

        # If API key is masked, substitute from saved settings
        api_key = settings.get("api_key", "").strip()
        if api_key.startswith("****") or not api_key:
            current = get_edgequake_settings()
            settings["api_key"] = current.get("api_key", "")

        if not settings.get("api_key", "").strip():
            return {"error": "API key is required to test connection"}

        return test_connection(settings=settings)

    def _generate_key(self) -> dict:
        from plugins.edgequake.helpers.edgequake_server import generate_api_key

        return {"api_key": generate_api_key()}

    def _start_server(self, settings: dict) -> dict:
        from plugins.edgequake.helpers.edgequake_server import start_server
        from plugins.edgequake.helpers.edgequake_client import get_edgequake_settings

        # Merge provided settings with saved settings for env vars
        saved = get_edgequake_settings()
        if settings:
            # If API key is masked, keep the saved one
            api_key = settings.get("api_key", "").strip()
            if api_key.startswith("****") or not api_key:
                settings["api_key"] = saved.get("api_key", "")
            saved.update({k: v for k, v in settings.items() if k in ALLOWED_KEYS})

        return start_server(saved)

    def _stop_server(self) -> dict:
        from plugins.edgequake.helpers.edgequake_server import stop_server

        return stop_server()

    def _server_status(self) -> dict:
        from plugins.edgequake.helpers.edgequake_server import server_status

        return server_status()
