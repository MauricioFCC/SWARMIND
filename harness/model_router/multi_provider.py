from harness.model_router.multi_provider_types import *
import logging
import os
import time
import threading
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

class MultiAPIProvider:
    """Abstracción multi-provider con failover automático y balanceo de carga.

    Gestiona múltiples proveedores LLM (OpenAI, Anthropic, Google, Mistral,
    DeepSeek) con registro dinámico, health checks periódicos, round-robin
    por tier, tracking de costos y métricas de latencia P50/P95/P99.

    Ejemplo:
        mcp = MultiAPIProvider()
        mcp.register_provider(ProviderConfig(
            name="openai", api_key_env="OPENAI_API_KEY",
            base_url="https://api.openai.com/v1",
            models=["gpt-4o", "gpt-4o-mini"],
            tier="premium", cost_per_1k_input=2.5, cost_per_1k_output=10.0,
        ))
        result = mcp.execute("gpt-4o", "Hello world")
        stats = mcp.get_stats()
    """

    def __init__(self) -> None:
        """Inicializa el gestor multi-provider.

        WHY: Se requiere un estado compartido para proveedores, métricas y
        controles de costo a nivel de instancia.
        WHERE: Constructor de MultiAPIProvider.
        """
        # name -> {config, client}
        self._providers: Dict[str, Dict[str, Any]] = {}

        # tier -> list of provider names (for round-robin)
        self._tier_providers: Dict[str, List[str]] = defaultdict(list)

        # tier -> current round-robin index
        self._rr_indices: Dict[str, int] = defaultdict(int)

        # provider health cache
        self._health: Dict[str, ProviderHealth] = {}

        # latency history per provider (rolling window)
        self._latency_history: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=LATENCY_WINDOW_SIZE)
        )

        # cost tracking per provider (USD total)
        self._costs: Dict[str, float] = defaultdict(float)

        # cost tracking per model (USD total)
        self._model_costs: Dict[str, float] = defaultdict(float)

        # request counts
        self._request_counts: Dict[str, int] = defaultdict(int)
        self._error_counts: Dict[str, int] = defaultdict(int)

        # budget limits per project
        self._budgets: Dict[str, BudgetLimit] = {}

        # health check thread control
        self._health_thread: Optional[threading.Thread] = None
        self._health_stop = threading.Event()

        # lock for thread safety
        self._lock = threading.RLock()

        # iniciar health checks en background
        self._start_health_checks()

    # ------------------------------------------------------------------
    # Registro y configuración de proveedores
    # ------------------------------------------------------------------

    def register_provider(self, config: ProviderConfig) -> None:
        """Registra un nuevo proveedor de modelos LLM.

        Args:
            config: Configuración completa del proveedor.

        Raises:
            ValueError: Si el nombre del proveedor ya está registrado
                o la configuración es inválida.

        WHY: Cada proveedor necesita configuración individual (API key,
        modelos, costos) para ser invocado correctamente.
        WHERE: register_provider en MultiAPIProvider.
        """
        if not config.name:
            raise ValueError(
                "Provider name cannot be empty. "
                "WHY: Se necesita un nombre único para identificar el proveedor. "
                "WHERE: register_provider"
            )
        if not config.models:
            raise ValueError(
                f"Provider '{config.name}' must have at least one model. "
                "WHY: Sin modelos no hay ejecución posible. "
                "WHERE: register_provider"
            )
        if config.tier not in (t.value for t in ProviderTier):
            logger.warning(
                "Provider '%s' tier '%s' no es estándar, usando 'standard'. "
                "WHY: Se esperaba uno de %s. "
                "WHERE: register_provider",
                config.name, config.tier, [t.value for t in ProviderTier],
            )
            config.tier = ProviderTier.STANDARD.value

        with self._lock:
            if config.name in self._providers:
                raise ValueError(
                    f"Provider '{config.name}' already registered. "
                    "WHY: No se permite duplicados. "
                    "WHERE: register_provider"
                )

            self._providers[config.name] = {"config": config}
            self._tier_providers[config.tier].append(config.name)
            self._health[config.name] = ProviderHealth()

            logger.info(
                "Provider '%s' registrado con %d modelos en tier '%s'. "
                "WHERE: register_provider",
                config.name, len(config.models), config.tier,
            )

    def unregister_provider(self, name: str) -> None:
        """Elimina un proveedor registrado.

        Args:
            name: Nombre del proveedor a eliminar.

        WHY: Permite remover proveedores en runtime sin reiniciar la instancia.
        WHERE: unregister_provider en MultiAPIProvider.
        """
        with self._lock:
            if name not in self._providers:
                logger.warning(
                    "Provider '%s' no encontrado para eliminar. "
                    "WHY: El proveedor no estaba registrado. "
                    "WHERE: unregister_provider",
                    name,
                )
                return

            config = self._providers[name]["config"]
            tier = config.tier
            if name in self._tier_providers.get(tier, []):
                self._tier_providers[tier].remove(name)

            del self._providers[name]
            self._health.pop(name, None)
            self._latency_history.pop(name, None)
            self._costs.pop(name, None)
            self._request_counts.pop(name, None)
            self._error_counts.pop(name, None)

            logger.info(
                "Provider '%s' eliminado. WHERE: unregister_provider", name,
            )

    def get_providers(self) -> List[str]:
        """Retorna la lista de nombres de proveedores registrados.

        Returns:
            Lista de nombres de proveedores activos.
        """
        with self._lock:
            return list(self._providers.keys())

    # ------------------------------------------------------------------
    # Ejecución con failover
    # ------------------------------------------------------------------

    def execute(
        self,
        model: str,
        prompt: str,
        fallback: bool = True,
        agent_role: str = "*",
        max_tokens: Optional[int] = None,
    ) -> ExecutionResult:
        """Ejecuta un prompt en el modelo solicitado con failover opcional.

        Busca el proveedor que ofrece el modelo especificado. Si falla y
        `fallback=True`, intenta con otros proveedores del mismo tier y luego
        de tiers inferiores.

        Args:
            model: Nombre del modelo a ejecutar.
            prompt: Texto de entrada para el modelo.
            fallback: Si es True, intenta failover a otros proveedores.
            agent_role: Rol del agente (para límite de tokens).
            max_tokens: Máximo de tokens de salida (opcional, sobreescribe
                el valor por rol).

        Returns:
            ExecutionResult con el resultado de la ejecución.

        WHY: Abstrae la complejidad de elegir proveedor, manejar fallos
        y reintentar automáticamente.
        WHERE: execute en MultiAPIProvider.
        """
        if max_tokens is None:
            max_tokens = MAX_TOKENS_BY_AGENT.get(agent_role, MAX_TOKENS_BY_AGENT["*"])

        # 1. Buscar proveedor primario que ofrezca este modelo
        primary = self._find_provider_for_model(model)
        if primary is None:
            return ExecutionResult(
                success=False,
                output="",
                source="cloud",
                model=model,
                duration_ms=0,
                error=(
                    f"Model '{model}' no encontrado en ningún proveedor registrado. "
                    "WHY: El modelo debe estar listado en algún ProviderConfig.models. "
                    "WHERE: execute"
                ),
            )

        # 2. Ejecutar con failover chain
        return self._execute_with_chain(
            model=model,
            prompt=prompt,
            primary_provider=primary,
            fallback=fallback,
            agent_role=agent_role,
            max_tokens=max_tokens,
        )

    def execute_with_fallback(
        self,
        model: str,
        prompt: str,
        agent_role: str = "*",
        max_tokens: Optional[int] = None,
    ) -> ExecutionResult:
        """Ejecuta un modelo intentando múltiples proveedores en orden.

        A diferencia de execute(), este método ITERA sobre todos los
        proveedores registrados que tengan el modelo, en orden de tier
        (premium > standard > budget), hasta que uno responda exitosamente.

        Args:
            model: Nombre del modelo a ejecutar.
            prompt: Texto de entrada.
            agent_role: Rol del agente para límite de tokens.
            max_tokens: Máximo de tokens de salida.

        Returns:
            ExecutionResult con el primer resultado exitoso, o el último
            error si todos fallan.
        """
        return self.execute(
            model=model,
            prompt=prompt,
            fallback=True,
            agent_role=agent_role,
            max_tokens=max_tokens,
        )

    def _execute_with_chain(
        self,
        model: str,
        prompt: str,
        primary_provider: str,
        fallback: bool,
        agent_role: str,
        max_tokens: int,
    ) -> ExecutionResult:
        """Ejecuta en cadena: primario + failover ordenado por tier.

        Args:
            model: Modelo a ejecutar.
            prompt: Prompt de entrada.
            primary_provider: Proveedor primario.
            fallback: Habilitar failover.
            agent_role: Rol del agente.
            max_tokens: Límite de tokens de salida.

        Returns:
            ExecutionResult del primer éxito o último error.
        """
        # Construir la secuencia de proveedores a intentar
        candidates = [primary_provider]

        if fallback:
            # Agregar resto de proveedores con este modelo, ordenados por tier
            rest = self._get_other_providers_for_model(model, primary_provider)
            candidates.extend(rest)

        last_error: Optional[str] = None
        start = time.perf_counter()

        for provider_name in candidates:
            with self._lock:
                config = self._providers.get(provider_name, {}).get("config")
            if config is None:
                continue

            health = self._health.get(provider_name)
            if health is not None and not health.available:
                logger.debug(
                    "Skipping provider '%s' (unavailable). WHERE: _execute_with_chain",
                    provider_name,
                )
                continue

            logger.debug(
                "Attempting provider '%s' for model '%s'. WHERE: _execute_with_chain",
                provider_name, model,
            )

            result = self._execute_on_provider(
                provider_name=provider_name,
                config=config,
                model=model,
                prompt=prompt,
                max_tokens=max_tokens,
            )

            if result.success:
                elapsed = (time.perf_counter() - start) * 1000
                result.duration_ms = round(elapsed, 2)
                result.provider = provider_name
                self._record_success(provider_name, elapsed)
                return result

            last_error = result.error
            self._record_error(provider_name, result.error or "Unknown error")
            logger.warning(
                "Provider '%s' falló para modelo '%s': %s. "
                "WHY: Failover al siguiente proveedor. "
                "WHERE: _execute_with_chain",
                provider_name, model, result.error,
            )

        elapsed = (time.perf_counter() - start) * 1000
        return ExecutionResult(
            success=False,
            output="",
            source="cloud",
            model=model,
            duration_ms=round(elapsed, 2),
            error=(
                f"Todos los proveedores fallaron para modelo '{model}'. "
                f"Último error: {last_error}. "
                "WHY: La cadena de failover se agotó. "
                "WHERE: _execute_with_chain"
            ),
        )

    def _execute_on_provider(
        self,
        provider_name: str,
        config: ProviderConfig,
        model: str,
        prompt: str,
        max_tokens: int,
    ) -> ExecutionResult:
        """Ejecuta el prompt en un proveedor específico usando su API.

        Args:
            provider_name: Nombre del proveedor.
            config: Configuración del proveedor.
            model: Modelo a usar.
            prompt: Prompt de entrada.
            max_tokens: Máximo de tokens de salida.

        Returns:
            ExecutionResult del proveedor.
        """
        api_key = os.environ.get(config.api_key_env, "")
        if not api_key:
            return ExecutionResult(
                success=False,
                output="",
                source="cloud",
                model=model,
                duration_ms=0,
                error=(
                    f"API key '{config.api_key_env}' no configurada para "
                    f"provider '{provider_name}'. "
                    "WHY: La variable de entorno debe estar definida. "
                    "WHERE: _execute_on_provider"
                ),
                provider=provider_name,
            )

        # Normalizar nombre a minúsculas para identificar tipo de API
        pname = provider_name.lower()

        try:
            if pname == "anthropic":
                result = self._execute_anthropic(config, api_key, model, prompt, max_tokens)
            elif pname == "google":
                result = self._execute_google(config, api_key, model, prompt, max_tokens)
            elif pname in ("openai", "mistral", "deepseek", "zenfree"):
                result = self._execute_openai_compat(config, api_key, model, prompt, max_tokens)
            else:
                # Intento genérico OpenAI-compatible
                logger.debug(
                    "Provider '%s' no tiene handler específico, usando OpenAI-compat. "
                    "WHERE: _execute_on_provider",
                    provider_name,
                )
                result = self._execute_openai_compat(config, api_key, model, prompt, max_tokens)
        except Exception as exc:
            logger.error(
                "Error no manejado en provider '%s' modelo '%s': %s. "
                "WHERE: _execute_on_provider",
                provider_name, model, exc,
            )
            return ExecutionResult(
                success=False,
                output="",
                source="cloud",
                model=model,
                duration_ms=0,
                error=f"Unhandled error in {provider_name}: {exc}",
                provider=provider_name,
            )

        # Trackear costos si fue exitoso
        if result.success and result.tokens_used > 0:
            cost = self._track_cost(provider_name, model, result.tokens_used)
            logger.debug(
                "Provider '%s' cost: $%.6f for %d tokens. WHERE: _execute_on_provider",
                provider_name, cost, result.tokens_used,
            )

        result.provider = provider_name
        return result

    # ------------------------------------------------------------------
    # Handlers específicos por proveedor (delegados a provider_executors)
    # ------------------------------------------------------------------

    def _execute_openai_compat(self, config, api_key, prompt, max_tokens, temperature):
        from harness.model_router.provider_executors import execute_openai_compat
        return execute_openai_compat(self, config, api_key, prompt, max_tokens, temperature)

    def _execute_anthropic(self, config, api_key, prompt, max_tokens, temperature):
        from harness.model_router.provider_executors import execute_anthropic
        return execute_anthropic(self, config, api_key, prompt, max_tokens, temperature)

    def _execute_google(self, config, api_key, prompt, max_tokens, temperature):
        from harness.model_router.provider_executors import execute_google
        return execute_google(self, config, api_key, prompt, max_tokens, temperature)

    def _start_health_checks(self) -> None:
        """Inicia health checks en background (delegado)."""
        from harness.model_router.provider_executors import _start_health_checks as _hc
        _hc(self)

    def stop_health_checks(self) -> None:
        """Detiene health checks (delegado)."""
        from harness.model_router.provider_executors import stop_health_checks as _shc
        _shc(self)

    def _track_cost(self, provider, model, tokens):
        """Trackea costos (delegado)."""
        from harness.model_router.provider_executors import _track_cost as _tc
        return _tc(self, provider, model, tokens)

    def _calculate_cost(self, provider, tokens):
        """Calcula costo (delegado)."""
        from harness.model_router.provider_executors import _calculate_cost as _cc
        return _cc(self, provider, tokens)

    def __del__(self) -> None:
        """Cleanup: detiene health checks al destruir la instancia."""
        try:
            self.stop_health_checks()
        except Exception:
            pass


# ===================================================================
# ModelRouter (MEJORADO) — mantiene compatibilidad total hacia atrás
# ===================================================================