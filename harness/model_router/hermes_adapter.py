"""
Model Router Adapter â€” Uses Hermes providers when available, falls back to local Ollama.

This adapter allows Swarmind to leverage Hermes Agent's provider ecosystem
 while maintaining backward compatibility with the standalone router.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

try:
    # Try Hermes config system
    from hermes_constants import get_hermes_home
    HERMES_AVAILABLE = True
except ImportError:
    HERMES_AVAILABLE = False


class HermesModelAdapter:
    """
    Adapter that detects Hermes config and uses its providers.
    
    Falls back to the original ModelRouter logic if Hermes is not configured.
    """

    def __init__(self, original_router=None):
        self._hermes_config = self._load_hermes_config()
        self._original_router = original_router

    def _load_hermes_config(self) -> dict[str, Any] | None:
        """Load Hermes model configuration if available."""
        if not HERMES_AVAILABLE:
            return None

        try:
            hermes_home = get_hermes_home()
            config_path = hermes_home / "config.yaml"

            if config_path.exists():
                import yaml
                return yaml.safe_load(config_path.read_text())
        except Exception as _exc:  # noqa: BLE001
            logger.warning("hermes_adapter: %s", _exc)

        return None

    def route(self, task: str, agent_role: str = "*") -> dict[str, Any]:
        """Route a task using Hermes config or fallback."""
        if self._hermes_config:
            # Use Hermes model configuration
            model_config = self._hermes_config.get("model", {})
            default_model = model_config.get("default", "gpt-4o-mini")
            provider = model_config.get("provider", "openrouter")

            return {
                "source": "hermes",
                "model": default_model,
                "provider": provider,
                "reason": f"Hermes config for @{agent_role}",
            }

        # Fallback to original router
        if self._original_router:
            return self._original_router.route(task, agent_role)

        return {"source": "local", "model": "llama3", "provider": "ollama"}

    def execute(self, prompt: str, agent_role: str = "*") -> str:
        """Execute using Hermes or fallback."""
        # When running inside Hermes, the model is already configured
        # Just return the prompt as context for the agent to process
        if "HERMES_SESSION_ID" in os.environ:
            return f"[Hermes] Prompt ready for @{agent_role}: {prompt}"

        # Outside Hermes, use original Router logic
        if self._original_router:
            result = self._original_router.execute(prompt, agent_role)
            return result.output if result.success else f"[Error] {result.error}"

        return "[No model available]"


# Hook function for run.py
def apply_hermes_routing(task: str, target_agent: str, routing_source: str) -> dict[str, Any]:
    """Apply Hermes-aware routing when available."""
    if not HERMES_AVAILABLE:
        return {"source": routing_source, "model": "unknown", "provider": "unknown"}

    try:
        import importlib
        importlib.util.find_spec("hermes_tools")
        # In Hermes context, routing is automatic
        return {
            "source": "hermes",
            "model": os.environ.get("HERMES_DEFAULT_MODEL", "gpt-4o-mini"),
            "provider": os.environ.get("HERMES_DEFAULT_PROVIDER", "openrouter"),
        }
    except ImportError:
        pass

    return {"source": routing_source, "model": "unknown", "provider": "unknown"}
