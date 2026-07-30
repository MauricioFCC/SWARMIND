"""ModelRouter — Enrutamiento de tareas a modelos LLM."""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from harness.model_router.multi_provider import (
    MAX_TOKENS_BY_AGENT,
    MultiAPIProvider,
    ProviderConfig,
    ProviderHealth,
    RoutingDecision,
    ExecutionResult,
    BudgetLimit,
)

logger = logging.getLogger(__name__)
class ModelRouter:
    """Enrutador de tareas de agentes a modelos locales o cloud multi-provider.

    Mejora sobre la versión original:
      - Multi-provider con failover automático
      - Health checks periódicos
      - Cost tracking por proveedor y proyecto
      - Latencia P50/P95/P99
      - Round-robin entre proveedores del mismo tier
      - Control de presupuesto por proyecto

    Uso (compatible):
        router = ModelRouter()
        decision = router.route("Refactor API", "software-engineer")
        result = router.execute("Summarize doc", "context-engineer")
        stats = router.get_provider_stats()
        router.set_budget("project-alpha", 50.0)
    """

    def __init__(self, config_path: Optional[str] = None):
        """Inicializa el router con configuración y proveedores por defecto.

        Args:
            config_path: Ruta al archivo YAML de configuración. Si es None,
                se busca 'router_config.yaml' en el mismo directorio.

        WHY: Se requiere cargar configuración y registrar los proveedores
        cloud disponibles para que el router funcione.
        WHERE: __init__ de ModelRouter.
        """
        self.config = self._load_config(config_path)
        self._ollama_available: Optional[bool] = None  # lazy check

        # Multi-provider engine
        self._multi_provider = MultiAPIProvider()
        self._register_default_providers()

        # Proyecto activo para cost tracking
        self._active_project: Optional[str] = None

    def _register_default_providers(self) -> None:
        """Registra los proveedores cloud definidos en la configuración.

        WHY: Los proveedores deben estar disponibles sin configuración
        adicional del usuario.
        WHERE: _register_default_providers.
        """
        providers_cfg = self.config.get("providers", [])
        if not providers_cfg:
            # Si no hay providers en config, registrar defaults basados en env
            self._register_env_providers()
            return

        for pcfg in providers_cfg:
            try:
                config = ProviderConfig(
                    name=pcfg.get("name", "unknown"),
                    api_key_env=pcfg.get("api_key_env", ""),
                    base_url=pcfg.get("base_url", ""),
                    models=pcfg.get("models", []),
                    tier=pcfg.get("tier", ProviderTier.STANDARD.value),
                    cost_per_1k_input=pcfg.get("cost_per_1k_input", 0.0),
                    cost_per_1k_output=pcfg.get("cost_per_1k_output", 0.0),
                    max_retries=pcfg.get("max_retries", 3),
                    timeout_ms=pcfg.get("timeout_ms", 30000),
                    headers_extra=pcfg.get("headers_extra", {}),
                )
                self._multi_provider.register_provider(config)
            except Exception as exc:
                logger.warning(
                    "Error registrando provider '%s': %s. "
                    "WHY: Proveedor inválido en config será omitido. "
                    "WHERE: _register_default_providers",
                    pcfg.get("name", "?"), exc,
                )

    def _register_env_providers(self) -> None:
        """Registra proveedores detectando variables de entorno.

        WHY: Para que funcione out-of-the-box sin configuración YAML,
        detectando qué APIs están configuradas.
        WHERE: _register_env_providers.
        """
        # OPENAI
        if os.environ.get("OPENAI_API_KEY"):
            self._multi_provider.register_provider(ProviderConfig(
                name="openai",
                api_key_env="OPENAI_API_KEY",
                base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                models=["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
                tier=ProviderTier.PREMIUM.value,
                cost_per_1k_input=2.50,
                cost_per_1k_output=10.00,
                timeout_ms=60000,
            ))

        # ANTHROPIC
        if os.environ.get("ANTHROPIC_API_KEY"):
            self._multi_provider.register_provider(ProviderConfig(
                name="anthropic",
                api_key_env="ANTHROPIC_API_KEY",
                base_url=os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com"),
                models=[
                    "claude-3-5-sonnet-20241022",
                    "claude-3-5-haiku-20241022",
                    "claude-3-opus-20240229",
                ],
                tier=ProviderTier.PREMIUM.value,
                cost_per_1k_input=3.00,
                cost_per_1k_output=15.00,
                timeout_ms=60000,
            ))

        # GOOGLE GEMINI
        if os.environ.get("GOOGLE_API_KEY"):
            self._multi_provider.register_provider(ProviderConfig(
                name="google",
                api_key_env="GOOGLE_API_KEY",
                base_url=os.environ.get("GOOGLE_BASE_URL", "https://generativelanguage.googleapis.com"),
                models=["gemini-1.5-pro", "gemini-1.5-flash", "gemini-1.0-pro"],
                tier=ProviderTier.STANDARD.value,
                cost_per_1k_input=3.50,
                cost_per_1k_output=10.50,
                timeout_ms=60000,
            ))

        # MISTRAL
        if os.environ.get("MISTRAL_API_KEY"):
            self._multi_provider.register_provider(ProviderConfig(
                name="mistral",
                api_key_env="MISTRAL_API_KEY",
                base_url=os.environ.get("MISTRAL_BASE_URL", "https://api.mistral.ai/v1"),
                models=["mistral-large-latest", "mistral-medium-latest", "open-mistral-nemo"],
                tier=ProviderTier.STANDARD.value,
                cost_per_1k_input=2.00,
                cost_per_1k_output=6.00,
                timeout_ms=60000,
            ))

        # DEEPSEEK
        if os.environ.get("DEEPSEEK_API_KEY"):
            self._multi_provider.register_provider(ProviderConfig(
                name="deepseek",
                api_key_env="DEEPSEEK_API_KEY",
                base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
                models=["deepseek-chat", "deepseek-coder"],
                tier=ProviderTier.BUDGET.value,
                cost_per_1k_input=0.14,
                cost_per_1k_output=0.28,
                timeout_ms=120000,
            ))

        # ZENFREE (compatibilidad legacy)
        if os.environ.get("ZENFREE_API_KEY") or os.environ.get("API_KEY"):
            key_env = "ZENFREE_API_KEY" if os.environ.get("ZENFREE_API_KEY") else "API_KEY"
            self._multi_provider.register_provider(ProviderConfig(
                name="zenfree",
                api_key_env=key_env,
                base_url="https://api.zenfree.com/v1",
                models=["gpt-4o-mini", "gpt-4o"],
                tier=ProviderTier.STANDARD.value,
                cost_per_1k_input=0.15,
                cost_per_1k_output=0.60,
                timeout_ms=60000,
            ))

    # ------------------------------------------------------------------
    # Public API — compatibilidad total
    # ------------------------------------------------------------------

    def route(self, task: str, agent_role: str = "*") -> RoutingDecision:
        """Determina si una tarea debe ejecutarse local o en cloud.

        Prioridad (mayor a menor):
        1. Keywords destructivas → cloud (seguridad)
        2. Rol de agente con default explícito → usa ese default
        3. Tarea corta (< threshold) → local
        4. Wildcard default (*) o fallback → local

        Args:
            task: Descripción de la tarea a enrutar.
            agent_role: Rol del agente que solicita la tarea.

        Returns:
            RoutingDecision con la decisión de enrutamiento.
        """
        task_stripped = task.strip()
        preview = task_stripped[:80]

        agent_defaults = self.config.get("routing_rules", {}).get("agent_defaults", {})
        wildcard_default = agent_defaults.get("*", "local")

        # Priority 1: Destructive keywords → siempre cloud
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

        # Priority 2: Rol tiene default explícito
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

        # Priority 3: Tarea corta → local
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
        """Enruta y ejecuta una tarea en el modelo apropiado.

        Si se elige local pero no está disponible, hace fallback a cloud
        si ``fallback_to_cloud`` está habilitado en config.

        Args:
            task: Tarea a ejecutar.
            agent_role: Rol del agente.

        Returns:
            ExecutionResult con el resultado de la ejecución.
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

            # Local falló — verificar fallback
            fallback = (
                self.config.get("local", {}).get("fallback_to_cloud", True)
                and self._cloud_enabled()
            )
            if fallback:
                logger.warning(
                    "Local execution failed, falling back to cloud: %s. "
                    "WHERE: execute",
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

        # Cloud execution — ahora usa MultiAPIProvider con failover
        cloud_result = self._execute_cloud(task, agent_role=agent_role)
        elapsed = (time.perf_counter() - start) * 1000
        return ExecutionResult(
            success=cloud_result.success,
            output=cloud_result.output,
            source="cloud",
            model=decision.model,
            duration_ms=round(elapsed, 2),
            error=cloud_result.error,
        )

    def route_with_fallback(self, task: str, agent_role: str = "*") -> ExecutionResult:
        """Enruta y ejecuta con failover entre múltiples proveedores cloud.

        A diferencia de execute(), este método ITERA sobre todos los
        proveedores cloud registrados que tengan el modelo apropiado,
        intentando cada uno hasta obtener una respuesta exitosa.

        Args:
            task: Tarea a ejecutar.
            agent_role: Rol del agente.

        Returns:
            ExecutionResult con el resultado exitoso o el último error.

        WHY: Maximiza la probabilidad de éxito usando failover automático
        entre proveedores.
        WHERE: route_with_fallback en ModelRouter.
        """
        start = time.perf_counter()
        decision = self.route(task, agent_role)

        if decision.source == "local":
            # Si la ruta es local, primero intentamos local
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

            # Local falló, intentamos cloud con failover multi-provider
            logger.info(
                "Local no disponible, intentando cloud con failover. "
                "WHERE: route_with_fallback",
            )

        # Ejecutar cloud con failover entre proveedores
        cloud_model = self._cloud_model()
        max_tokens = MAX_TOKENS_BY_AGENT.get(agent_role, MAX_TOKENS_BY_AGENT["*"])

        result = self._multi_provider.execute(
            model=cloud_model,
            prompt=task,
            fallback=True,
            agent_role=agent_role,
            max_tokens=max_tokens,
        )

        if not result.success:
            # Último intento: proveedores con modelos alternativos
            result = self._multi_provider.execute(
                model=self._get_fallback_model(),
                prompt=task,
                fallback=True,
                agent_role=agent_role,
                max_tokens=max_tokens,
            )

        elapsed = (time.perf_counter() - start) * 1000
        result.duration_ms = round(elapsed, 2)
        return result

    def _get_fallback_model(self) -> str:
        """Retorna un modelo de fallback cuando el principal no funciona.

        WHY: Si el modelo principal no está disponible en ningún proveedor,
        se necesita una alternativa.
        WHERE: _get_fallback_model.

        Returns:
            Nombre del modelo de fallback.
        """
        # Intentar modelos más baratos/comunes como fallback
        fallback_models = [
            "gpt-4o-mini",
            "claude-3-5-haiku-20241022",
            "gemini-1.5-flash",
            "mistral-medium-latest",
            "deepseek-chat",
        ]

        for model in fallback_models:
            provider = self._multi_provider._find_provider_for_model(model)
            if provider is not None:
                return model

        return "gpt-4o-mini"  # default universal

    # ------------------------------------------------------------------
    # Provider stats y budget
    # ------------------------------------------------------------------

    def get_provider_stats(self) -> Dict[str, Any]:
        """Retorna estadísticas detalladas de todos los proveedores cloud.

        Incluye:
          - Estado de salud (available/degraded/unavailable)
          - Latencia P50/P95/P99 por proveedor
          - Tasa de error
          - Costo acumulado por proveedor
          - Conteo de requests

        Returns:
            Diccionario con métricas por proveedor y resumen global.

        WHY: Permite monitorear el rendimiento y costo de cada proveedor
        para tomar decisiones de optimización.
        WHERE: get_provider_stats en ModelRouter.
        """
        return self._multi_provider.get_stats()

    def set_budget(self, project: str, limit: float, alert_threshold: float = 0.8) -> None:
        """Establece un presupuesto máximo para un proyecto.

        Args:
            project: Identificador del proyecto.
            limit: Límite máximo en USD.
            alert_threshold: Fracción para alerta temprana (0.0 a 1.0).

        Raises:
            ValueError: Si limit <= 0.

        WHY: Control de costos para evitar sobrecostos no planificados.
        WHERE: set_budget en ModelRouter.
        """
        self._multi_provider.set_budget(project, limit, alert_threshold)
        self._active_project = project

    def check_budget(self, project: Optional[str] = None) -> Tuple[float, float, bool]:
        """Verifica el estado del presupuesto de un proyecto.

        Args:
            project: Identificador del proyecto. Si es None, usa el activo.

        Returns:
            Tupla (spent, limit, exceeded).
        """
        p = project or self._active_project
        if p is None:
            return 0.0, 0.0, False
        return self._multi_provider.check_budget(p)

    def get_total_cost(self, provider: Optional[str] = None) -> float:
        """Retorna el costo total acumulado en USD.

        Args:
            provider: Nombre del proveedor. Si es None, suma todos.

        Returns:
            Costo total en USD.
        """
        return self._multi_provider.get_total_cost(provider)

    # ------------------------------------------------------------------
    # Local (Ollama) execution
    # ------------------------------------------------------------------

    def _try_execute_local(self, prompt: str, agent_role: str = "*") -> ExecutionResult:
        """Ejecuta un prompt en Ollama local.

        Args:
            prompt: Texto de entrada.
            agent_role: Rol del agente para límite de tokens.

        Returns:
            ExecutionResult con la respuesta local.
        """
        if not self._is_ollama_available():
            return ExecutionResult(
                success=False,
                output="",
                source="local",
                model=self._local_model(),
                duration_ms=0,
                error="Ollama no disponible. Instalar desde https://ollama.com",
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
        """Verifica si Ollama está corriendo y accesible.

        Returns:
            True si Ollama responde correctamente.
        """
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
    # Cloud execution (mejorado con MultiAPIProvider)
    # ------------------------------------------------------------------

    def _execute_cloud(self, prompt: str, agent_role: str = "*") -> ExecutionResult:
        """Ejecuta un prompt en cloud usando MultiAPIProvider con failover.

        Args:
            prompt: Texto de entrada.
            agent_role: Rol del agente.

        Returns:
            ExecutionResult del mejor proveedor disponible.
        """
        model = self._cloud_model()
        max_tokens = MAX_TOKENS_BY_AGENT.get(agent_role, MAX_TOKENS_BY_AGENT["*"])

        # Usar execute_with_fallback para intentar todos los proveedores
        result = self._multi_provider.execute_with_fallback(
            model=model,
            prompt=prompt,
            agent_role=agent_role,
            max_tokens=max_tokens,
        )

        return result

    # ------------------------------------------------------------------
    # Config helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
        """Carga configuración desde archivo YAML.

        Args:
            config_path: Ruta al archivo. Si es None, busca en el directorio
                del módulo.

        Returns:
            Diccionario con la configuración resuelta.
        """
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "router_config.yaml",
            )

        try:
            import yaml

            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
                return _resolve_env_vars(config)
        except Exception as exc:
            logger.warning(
                "Could not load router config: %s. Using defaults. "
                "WHERE: _load_config",
                exc,
            )
            return _default_config()

    def _local_model(self) -> str:
        """Retorna el modelo local configurado."""
        return self.config.get("local", {}).get("model", "llama3")

    def _local_provider(self) -> str:
        """Retorna el proveedor local configurado."""
        return self.config.get("local", {}).get("provider", "ollama")

    def _local_endpoint(self) -> str:
        """Retorna el endpoint del proveedor local."""
        return self.config.get("local", {}).get("endpoint", "http://localhost:11434")

    def _local_enabled(self) -> bool:
        """Indica si el proveedor local está habilitado."""
        return self.config.get("local", {}).get("enabled", True)

    def _cloud_model(self) -> str:
        """Retorna el modelo cloud por defecto."""
        return self.config.get("cloud", {}).get("model", "gpt-4o-mini")

    def _cloud_provider(self) -> str:
        """Retorna el proveedor cloud por defecto."""
        return self.config.get("cloud", {}).get("provider", "openai")

    def _cloud_enabled(self) -> bool:
        """Indica si el cloud está habilitado."""
        return self.config.get("cloud", {}).get("enabled", True)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """Libera recursos: detiene health checks y limpia estado.

        WHY: Necesario para un shutdown graceful en aplicaciones de larga
        duración.
        WHERE: shutdown en ModelRouter.
        """
        self._multi_provider.stop_health_checks()
        logger.info("ModelRouter shutdown completado. WHERE: shutdown")


# ---------------------------------------------------------------------------
# Config utilities
# ---------------------------------------------------------------------------


def _resolve_env_vars(config: Any) -> Any:
    """Resuelve recursivamente patrones ${VAR} en valores de configuración.

    Args:
        config: Valor, dict o lista con posibles ${VAR} a resolver.

    Returns:
        Configuración con variables de entorno resueltas.
    """
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
    """Retorna una configuración por defecto si no hay archivo.

    Returns:
        Diccionario con valores sensibles por defecto.
    """
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
            "provider": "openai",
            "api_key": "${OPENAI_API_KEY}",
            "model": "gpt-4o-mini",
        },
        "providers": [],
        "routing_rules": {
            "agent_defaults": {
                "software-engineer": "cloud",
                "enterprise-architect": "cloud",
                "quant-developer": "cloud",
                "ai-engineer": "cloud",
                "security-engineer": "cloud",
                "evolve-researcher": "cloud",
                "evolve-engineer": "cloud",
                "data-architect": "cloud",
                "devops-sre": "cloud",
                "context-engineer": "local",
                "documentation-specialist": "local",
                "tool-mcp-engineer": "local",
                "qualifier-agent": "local",
                "quality-gate": "local",
                "*": "local",
            },
            "destructive_keywords": [
                "DROP", "DELETE", "rm -rf", "terraform destroy",
                "terraform apply", "format C:", "dd if=",
                "kubectl delete", "docker rm -f",
            ],
            "short_task_threshold_chars": 200,
        },
    }
