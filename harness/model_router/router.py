"""
ModelRouter — routes agent tasks to local (Ollama) or cloud models.

Usage:
    router = ModelRouter()
    decision = router.route("Refactor the API endpoint", "software-engineer")
    # decision.source == "cloud"

    result = router.execute("Summarize this doc", "context-engineer")
    # Uses local Ollama, falls back to cloud if unavailable
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Output token budget per agent role
# ---------------------------------------------------------------------------
# Tokens de salida cuestan 3-5x más que input, por lo que usamos valores
# conservadores: la mayoría de agentes responden en <512 tokens.
MAX_TOKENS_BY_AGENT: Dict[str, int] = {
    "project-manager": 512,       # Coordinación, respuestas cortas
    "context-engineer": 1024,     # Contexto, necesita más espacio
    "tool-mcp-engineer": 768,     # Tool descriptions
    "software-engineer": 1024,    # Código + explicación
    "data-architect": 768,        # Schemas, no muy largo
    "devops-sre": 768,            # Config, comandos
    "security-engineer": 512,     # Findings concisos
    "frontend-engineer": 1024,    # UI code
    "mobile-engineer": 1024,      # Mobile code
    "ai-engineer": 1024,          # ML pipelines
    "quality-gate": 512,          # Checklist, approve/reject
    "documentation-specialist": 1536,  # Docs largos
    "requirements-analyst": 768,  # Análisis
    "enterprise-architect": 1024, # ADR, C4
    "quant-developer": 1024,      # Estrategias cuantitativas
    "quant-scientist": 1024,      # Análisis estadístico
    "risk-manager": 512,          # Reports numéricos
    "trading-operations": 512,    # Alertas, monitoreo
    "evolve-researcher": 1024,    # Investigación
    "evolve-engineer": 768,       # Evaluación
    "evolve-analyzer": 768,       # Análisis de resultados
    "*": 512,                     # Default seguro
}

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass
class RoutingDecision:
    """Result of a routing decision."""

    source: str  # "local" or "cloud"
    model: str
    provider: str
    reason: str
    agent_role: str
    task_preview: str = ""


@dataclass
class ExecutionResult:
    """Result of model execution."""

    success: bool
    output: str
    source: str  # "local" or "cloud"
    model: str
    duration_ms: float
    error: Optional[str] = None
    tokens_used: int = 0


# ---------------------------------------------------------------------------
# Model Router
# ---------------------------------------------------------------------------


class ModelRouter:
    """
    Routes agent tasks to local (Ollama) or cloud models based on:
    - Agent role defaults
    - Task content (destructive keywords → cloud)
    - Task length (short → local, long → cloud)
    """

    def __init__(self, config_path: Optional[str] = None):
        """Inicializa la instancia de la clase."""
        self.config = self._load_config(config_path)
        self._ollama_available: Optional[bool] = None  # lazy check

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def route(self, task: str, agent_role: str = "*") -> RoutingDecision:
        """
        Determine whether a task should run locally or in the cloud.

        Priority (highest to lowest):
        1. Destructive keywords → cloud (safety override)
        2. Agent role has explicit default (not wildcard) → use it
        3. Short task (< threshold chars) → local
        4. Wildcard default (*) or fallback → local
        """
        task_stripped = task.strip()
        preview = task_stripped[:80]

        agent_defaults = self.config.get("routing_rules", {}).get("agent_defaults", {})
        wildcard_default = agent_defaults.get("*", "local")

        # Priority 1: Destructive keywords → always cloud for safety
        destructive = self.config.get("routing_rules", {}).get("destructive_keywords", [])
        task_upper = task_stripped.upper()
        for kw in destructive:
            if kw.upper() in task_upper:
                return RoutingDecision(
                    source="cloud",
                    model=self._cloud_model(),
                    provider=self._cloud_provider(),
                    reason=f"Contains destructive keyword: {kw}",
                    agent_role=agent_role,
                    task_preview=preview,
                )

        # Priority 2: Agent role has an explicit (non-wildcard) default
        role_source = agent_defaults.get(agent_role)
        if role_source is not None and role_source in ("cloud", "local"):
            return RoutingDecision(
                source=role_source,
                model=self._cloud_model() if role_source == "cloud" else self._local_model(),
                provider=self._cloud_provider() if role_source == "cloud" else self._local_provider(),
                reason=f"Agent role '{agent_role}' defaults to {role_source}",
                agent_role=agent_role,
                task_preview=preview,
            )

        # Priority 3: Short task → local (efficient for simple queries)
        threshold = self.config.get("routing_rules", {}).get("short_task_threshold_chars", 200)
        if len(task_stripped) < threshold:
            return RoutingDecision(
                source="local",
                model=self._local_model(),
                provider=self._local_provider(),
                reason=f"Short task ({len(task_stripped)} chars < {threshold})",
                agent_role=agent_role,
                task_preview=preview,
            )

        # Priority 4: Wildcard default
        return RoutingDecision(
            source=wildcard_default,
            model=self._cloud_model() if wildcard_default == "cloud" else self._local_model(),
            provider=self._cloud_provider() if wildcard_default == "cloud" else self._local_provider(),
            reason=f"Wildcard default (*) is '{wildcard_default}' for role '{agent_role}'",
            agent_role=agent_role,
            task_preview=preview,
        )

    def execute(self, task: str, agent_role: str = "*") -> ExecutionResult:
        """
        Route and execute a task on the appropriate model.

        If local is chosen but unavailable, falls back to cloud
        if ``fallback_to_cloud`` is enabled in config.
        """
        decision = self.route(task, agent_role)
        start = time.perf_counter()

        if decision.source == "local":
            result = self._try_execute_local(task, agent_role=agent_role)
            if result.success:
                elapsed = (time.perf_counter() - start) * 1000
                return ExecutionResult(
                    success=True,
                    output=result.output,
                    source="local",
                    model=decision.model,
                    duration_ms=round(elapsed, 2),
                )

            # Local failed — check fallback
            fallback = (
                self.config.get("local", {}).get("fallback_to_cloud", True)
                and self._cloud_enabled()
            )
            if fallback:
                logger.warning(
                    "Local execution failed, falling back to cloud: %s",
                    result.error,
                )
                cloud_result = self._execute_cloud(task, agent_role=agent_role)
                elapsed = (time.perf_counter() - start) * 1000
                return ExecutionResult(
                    success=cloud_result.success,
                    output=cloud_result.output,
                    source="cloud",
                    model=self._cloud_model(),
                    duration_ms=round(elapsed, 2),
                    error=f"Local failed: {result.error}" if not cloud_result.success else None,
                )

            elapsed = (time.perf_counter() - start) * 1000
            return ExecutionResult(
                success=False,
                output="",
                source="local",
                model=decision.model,
                duration_ms=round(elapsed, 2),
                error=result.error or "Local execution failed and fallback disabled",
            )

        # Cloud execution
        result = self._execute_cloud(task, agent_role=agent_role)
        elapsed = (time.perf_counter() - start) * 1000
        return ExecutionResult(
            success=result.success,
            output=result.output,
            source="cloud",
            model=decision.model,
            duration_ms=round(elapsed, 2),
            error=result.error,
        )

    # ------------------------------------------------------------------
    # Local (Ollama) execution
    # ------------------------------------------------------------------

    def _try_execute_local(self, prompt: str, agent_role: str = "*") -> ExecutionResult:
        """Try executing a prompt on local Ollama."""
        if not self._is_ollama_available():
            return ExecutionResult(
                success=False,
                output="",
                source="local",
                model=self._local_model(),
                duration_ms=0,
                error="Ollama not available. Install from https://ollama.com",
            )

        try:
            import requests

            endpoint = self._local_endpoint().rstrip("/")
            model = self._local_model()
            timeout = self.config.get("local", {}).get("timeout", 120)
            max_tokens = MAX_TOKENS_BY_AGENT.get(agent_role, MAX_TOKENS_BY_AGENT["*"])

            payload = {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "num_predict": max_tokens,
                },
            }

            resp = requests.post(
                f"{endpoint}/api/generate",
                json=payload,
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()

            return ExecutionResult(
                success=True,
                output=data.get("response", ""),
                source="local",
                model=model,
                duration_ms=0,  # caller fills this
            )

        except Exception as exc:
            return ExecutionResult(
                success=False,
                output="",
                source="local",
                model=self._local_model(),
                duration_ms=0,
                error=f"Ollama error: {exc}",
            )

    def _is_ollama_available(self) -> bool:
        """Check if Ollama is running and accessible."""
        if self._ollama_available is not None:
            return self._ollama_available

        try:
            import requests

            endpoint = self._local_endpoint().rstrip("/")
            resp = requests.get(f"{endpoint}/api/tags", timeout=5)
            self._ollama_available = resp.status_code == 200
        except Exception:
            self._ollama_available = False

        return self._ollama_available

    # ------------------------------------------------------------------
    # Cloud execution
    # ------------------------------------------------------------------

    def _execute_cloud(self, prompt: str, agent_role: str = "*") -> ExecutionResult:
        """Execute a prompt on the configured cloud API."""
        provider = self._cloud_provider()
        model = self._cloud_model()

        if provider == "zenfree":
            return self._execute_zenfree(prompt, model, agent_role=agent_role)

        # Generic OpenAI-compatible fallback
        return self._execute_openai_compat(prompt, model, agent_role=agent_role)

    def _execute_zenfree(self, prompt: str, model: str, agent_role: str = "*") -> ExecutionResult:
        """Execute via ZenFree API (or similar OpenAI-compatible)."""
        api_key = os.environ.get("ZENFREE_API_KEY") or os.environ.get("API_KEY", "")
        if not api_key:
            return ExecutionResult(
                success=False,
                output="",
                source="cloud",
                model=model,
                duration_ms=0,
                error="No API key found. Set ZENFREE_API_KEY or API_KEY env var.",
            )

        try:
            import requests

            endpoint = "https://api.zenfree.com/v1/chat/completions"  # example; adjust as needed
            timeout = 60
            max_tokens = MAX_TOKENS_BY_AGENT.get(agent_role, MAX_TOKENS_BY_AGENT["*"])

            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": max_tokens,
            }
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }

            resp = requests.post(endpoint, json=payload, headers=headers, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()

            content = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )

            return ExecutionResult(
                success=True,
                output=content,
                source="cloud",
                model=model,
                duration_ms=0,
            )

        except Exception as exc:
            return ExecutionResult(
                success=False,
                output="",
                source="cloud",
                model=model,
                duration_ms=0,
                error=f"Cloud API error: {exc}",
            )

    def _execute_openai_compat(self, prompt: str, model: str, agent_role: str = "*") -> ExecutionResult:
        """Execute via any OpenAI-compatible API."""
        api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("API_KEY", "")
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")

        if not api_key:
            return ExecutionResult(
                success=False,
                output="",
                source="cloud",
                model=model,
                duration_ms=0,
                error="No API key found. Set OPENAI_API_KEY env var.",
            )

        try:
            import requests

            timeout = 60
            max_tokens = MAX_TOKENS_BY_AGENT.get(agent_role, MAX_TOKENS_BY_AGENT["*"])
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": max_tokens,
            }
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }

            resp = requests.post(
                f"{base_url.rstrip('/')}/chat/completions",
                json=payload,
                headers=headers,
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()

            content = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )

            return ExecutionResult(
                success=True,
                output=content,
                source="cloud",
                model=model,
                duration_ms=0,
            )

        except Exception as exc:
            return ExecutionResult(
                success=False,
                output="",
                source="cloud",
                model=model,
                duration_ms=0,
                error=f"OpenAI-compat API error: {exc}",
            )

    # ------------------------------------------------------------------
    # Config helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
        """Load router configuration from YAML file."""
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "router_config.yaml",
            )

        try:
            import yaml

            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
                # Resolve env vars in strings like ${API_KEY}
                return _resolve_env_vars(config)
        except Exception as exc:
            logger.warning("Could not load router config: %s. Using defaults.", exc)
            return _default_config()

    def _local_model(self) -> str:
        return self.config.get("local", {}).get("model", "llama3")

    def _local_provider(self) -> str:
        return self.config.get("local", {}).get("provider", "ollama")

    def _local_endpoint(self) -> str:
        return self.config.get("local", {}).get("endpoint", "http://localhost:11434")

    def _local_enabled(self) -> bool:
        return self.config.get("local", {}).get("enabled", True)

    def _cloud_model(self) -> str:
        return self.config.get("cloud", {}).get("model", "gpt-4o-mini")

    def _cloud_provider(self) -> str:
        return self.config.get("cloud", {}).get("provider", "zenfree")

    def _cloud_enabled(self) -> bool:
        return self.config.get("cloud", {}).get("enabled", True)


# ---------------------------------------------------------------------------
# Config utilities
# ---------------------------------------------------------------------------


def _resolve_env_vars(config: Any) -> Any:
    """Recursively resolve ${VAR} patterns in config values."""
    if isinstance(config, str):
        if config.startswith("${") and config.endswith("}"):
            var_name = config[2:-1]
            return os.environ.get(var_name, "")
        return config
    if isinstance(config, dict):
        return {k: _resolve_env_vars(v) for k, v in config.items()}
    if isinstance(config, list):
        return [_resolve_env_vars(item) for item in config]
    return config


def _default_config() -> Dict[str, Any]:
    """Return a sensible default config if no file is found."""
    return {
        "local": {
            "enabled": True,
            "provider": "ollama",
            "model": "llama3",
            "endpoint": "http://localhost:11434",
            "timeout": 120,
            "fallback_to_cloud": True,
        },
        "cloud": {
            "enabled": True,
            "provider": "zenfree",
            "api_key": "${API_KEY}",
            "model": "gpt-4o-mini",
        },
        "routing_rules": {
            "agent_defaults": {
                "software-engineer": "cloud",
                "enterprise-architect": "cloud",
                "quant-developer": "cloud",
                "*": "local",
            },
            "destructive_keywords": ["DROP", "DELETE", "rm -rf"],
            "short_task_threshold_chars": 200,
        },
    }
