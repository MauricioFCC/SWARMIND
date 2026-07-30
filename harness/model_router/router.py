"""
ModelRouter — Enrutador multi-provider con failover automático, balanceo de carga,
health checks, tracking de costos y latencias P50/P95/P99.

Soporta:
  - OpenAI (GPT-4o, GPT-4o-mini)
  - Anthropic (Claude 3.5 Sonnet, Claude 3 Haiku)
  - Google (Gemini 1.5 Pro, Gemini 1.5 Flash)
  - Mistral (Mistral Large, Mixtral)
  - DeepSeek (DeepSeek-V2, DeepSeek-Coder-V2)

Arquitectura:
  MultiAPIProvider  →  Abstracción multi-provider con failover y round-robin
  ModelRouter       →  Routing legacy + nuevos métodos route_with_fallback, get_provider_stats, set_budget

Compatibilidad total hacia atrás con la API original de ModelRouter.

Uso:
    router = ModelRouter()
    decision = router.route("Refactor API", "software-engineer")
    result = router.execute("Summarize doc", "context-engineer")
    stats = router.get_provider_stats()
"""

from __future__ import annotations

import logging
import os
import time
import threading
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes globales
# ---------------------------------------------------------------------------

# Tokens de salida por rol de agente (cuestan 3-5x más que input)
MAX_TOKENS_BY_AGENT: Dict[str, int] = {
    # 5 roles universales
    "coordinator": 512,
    "builder": 1024,
    "scientist": 1024,
    "guardian": 512,
    "evolve": 768,
    # Compatibilidad con roles antiguos
    "project-manager": 512,
    "context-engineer": 1024,
    "software-engineer": 1024,
    "data-architect": 768,
    "devops-sre": 768,
    "security-engineer": 512,
    "frontend-engineer": 1024,
    "mobile-engineer": 1024,
    "ai-engineer": 1024,
    "quality-gate": 512,
    "documentation-specialist": 1536,
    "requirements-analyst": 768,
    "enterprise-architect": 1024,
    "quant-developer": 1024,
    "quant-scientist": 1024,
    "risk-manager": 512,
    "trading-operations": 512,
    "tool-mcp-engineer": 768,
    "evolve-researcher": 1024,
    "evolve-engineer": 768,
    "evolve-analyzer": 768,
    "*": 512,
}

# Intervalo por defecto entre health checks (segundos)
HEALTH_CHECK_INTERVAL_S: float = 60.0

# Ventana para métricas de latencia (número de muestras)
LATENCY_WINDOW_SIZE: int = 1000

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ProviderTier(str, Enum):
    """Tier de proveedor para balanceo de carga y priorización."""

    PREMIUM = "premium"
    STANDARD = "standard"
    BUDGET = "budget"


class ProviderStatus(str, Enum):
    """Estado de disponibilidad de un proveedor."""

    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Dataclasses (compatibles con las originales + nuevas)
# ---------------------------------------------------------------------------


@dataclass
class RoutingDecision:
    """Resultado de una decisión de enrutamiento.

    Attributes:
        source: Origen del modelo ("local" o "cloud").
        model: Nombre del modelo seleccionado.
        provider: Nombre del proveedor.
        reason: Justificación de la decisión.
        agent_role: Rol del agente que originó la tarea.
        task_preview: Vista previa de la tarea (primeros 80 caracteres).
    """

    source: str
    model: str
    provider: str
    reason: str
    agent_role: str
    task_preview: str = ""


@dataclass
class ExecutionResult:
    """Resultado de la ejecución de un modelo.

    Attributes:
        success: Indica si la ejecución fue exitosa.
        output: Texto generado por el modelo.
        source: Origen ("local" o "cloud").
        model: Modelo utilizado.
        duration_ms: Duración de la ejecución en milisegundos.
        error: Mensaje de error si la ejecución falló.
        tokens_used: Cantidad de tokens consumidos (aproximado).
        provider: Proveedor que ejecutó la solicitud.
    """

    success: bool
    output: str
    source: str
    model: str
    duration_ms: float
    error: Optional[str] = None
    tokens_used: int = 0
    provider: str = ""


@dataclass
class ProviderConfig:
    """Configuración de un proveedor de modelos LLM.

    Attributes:
        name: Nombre interno del proveedor (ej: "openai", "anthropic").
        api_key_env: Variable de entorno donde se lee la API key.
        base_url: URL base de la API del proveedor.
        models: Lista de modelos que ofrece este proveedor.
        tier: Categoría de servicio ("premium", "standard", "budget").
        cost_per_1k_input: Costo USD por cada 1K tokens de entrada.
        cost_per_1k_output: Costo USD por cada 1K tokens de salida.
        max_retries: Número máximo de reintentos ante fallo transitorio.
        timeout_ms: Timeout de la solicitud en milisegundos.
        headers_extra: Cabeceras HTTP adicionales específicas del proveedor.

    Raises:
        ValueError: Si name está vacío o models está vacío.
    """

    name: str
    api_key_env: str
    base_url: str
    models: List[str]
    tier: str = ProviderTier.STANDARD.value
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    max_retries: int = 3
    timeout_ms: int = 30000
    headers_extra: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Valida campos obligatorios después de la inicialización.

        WHY: Evita registrar proveedores con configuraciones inválidas
        que causarían errores difíciles de diagnosticar más adelante.
        WHERE: __post_init__ de ProviderConfig.
        """
        if not self.name:
            raise ValueError(
                "Provider name cannot be empty. "
                "WHY: Se necesita un nombre único para identificar el proveedor. "
                "WHERE: ProviderConfig.__post_init__"
            )
        if not self.models:
            raise ValueError(
                f"Provider '{self.name}' must have at least one model. "
                "WHY: Sin modelos no hay ejecución posible. "
                "WHERE: ProviderConfig.__post_init__"
            )
        if self.max_retries < 0:
            raise ValueError(
                f"Provider '{self.name}' max_retries cannot be negative ({self.max_retries}). "
                "WHY: Los reintentos deben ser un número no negativo. "
                "WHERE: ProviderConfig.__post_init__"
            )
        if self.timeout_ms <= 0:
            raise ValueError(
                f"Provider '{self.name}' timeout_ms must be > 0 ({self.timeout_ms}). "
                "WHY: El timeout debe ser un valor positivo. "
                "WHERE: ProviderConfig.__post_init__"
            )


@dataclass
class ProviderHealth:
    """Estado de salud de un proveedor en el último chequeo.

    Attributes:
        status: Estado general del proveedor.
        available: Si el proveedor está disponible actualmente.
        latency_p50: Percentil 50 de latencia en ms.
        latency_p95: Percentil 95 de latencia en ms.
        latency_p99: Percentil 99 de latencia en ms.
        error_rate: Tasa de error en el período (0.0 a 1.0).
        last_check: Timestamp del último chequeo (time.time).
        last_success: Timestamp del último éxito.
        consecutive_failures: Fallos consecutivos desde el último éxito.
    """

    status: ProviderStatus = ProviderStatus.UNKNOWN
    available: bool = True
    latency_p50: float = 0.0
    latency_p95: float = 0.0
    latency_p99: float = 0.0
    error_rate: float = 0.0
    last_check: float = 0.0
    last_success: float = 0.0
    consecutive_failures: int = 0


@dataclass
class BudgetLimit:
    """Límite de presupuesto para un proyecto.

    Attributes:
        limit: Monto máximo en USD.
        spent: Monto gastado acumulado en USD.
        alert_threshold: Fracción del límite para emitir alerta (0.0 a 1.0).
    """

    limit: float
    spent: float = 0.0
    alert_threshold: float = 0.8


# ---------------------------------------------------------------------------
# MultiAPIProvider — Abstracción multi-provider con failover y balanceo
# ---------------------------------------------------------------------------


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
    # Handlers específicos por proveedor
    # ------------------------------------------------------------------

    def _execute_openai_compat(
        self,
        config: ProviderConfig,
        api_key: str,
        model: str,
        prompt: str,
        max_tokens: int,
    ) -> ExecutionResult:
        """Ejecuta contra APIs OpenAI-compatibles (OpenAI, Mistral, DeepSeek, etc.).

        Args:
            config: Configuración del proveedor.
            api_key: API key.
            model: Modelo.
            prompt: Prompt.
            max_tokens: Límite de tokens.

        Returns:
            ExecutionResult con la respuesta.
        """
        import requests

        base_url = config.base_url.rstrip("/")
        timeout_s = config.timeout_ms / 1000.0

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
        headers.update(config.headers_extra)

        try:
            resp = requests.post(
                f"{base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=timeout_s,
            )
            resp.raise_for_status()
            data = resp.json()

            content = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            # Estimación de tokens desde la respuesta o cálculo
            usage = data.get("usage", {})
            total_tokens = usage.get("total_tokens", 0)

            return ExecutionResult(
                success=True,
                output=content,
                source="cloud",
                model=model,
                duration_ms=0.0,
                tokens_used=total_tokens,
            )

        except requests.exceptions.Timeout as exc:
            return ExecutionResult(
                success=False,
                output="",
                source="cloud",
                model=model,
                duration_ms=0.0,
                error=(
                    f"Timeout ({timeout_s}s) en provider '{config.name}': {exc}. "
                    "WHY: El servidor no respondió dentro del límite. "
                    "WHERE: _execute_openai_compat"
                ),
            )
        except requests.exceptions.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else 0
            error_detail = ""
            if exc.response is not None:
                try:
                    error_detail = exc.response.json().get("error", {}).get("message", "")
                except Exception:
                    error_detail = exc.response.text[:200]

            return ExecutionResult(
                success=False,
                output="",
                source="cloud",
                model=model,
                duration_ms=0.0,
                error=(
                    f"HTTP {status_code} en '{config.name}': {error_detail}. "
                    "WHY: La API rechazó la solicitud. "
                    "WHERE: _execute_openai_compat"
                ),
            )
        except Exception as exc:
            return ExecutionResult(
                success=False,
                output="",
                source="cloud",
                model=model,
                duration_ms=0.0,
                error=(
                    f"Error en provider '{config.name}': {exc}. "
                    f"WHY: Fallo no categorizado en la comunicación HTTP. "
                    f"WHERE: _execute_openai_compat"
                ),
            )

    def _execute_anthropic(
        self,
        config: ProviderConfig,
        api_key: str,
        model: str,
        prompt: str,
        max_tokens: int,
    ) -> ExecutionResult:
        """Ejecuta contra la API de Anthropic (Claude).

        Args:
            config: Configuración del proveedor.
            api_key: API key de Anthropic.
            model: Modelo (ej: "claude-3-5-sonnet-20241022").
            prompt: Prompt de entrada.
            max_tokens: Máximo de tokens de salida.

        Returns:
            ExecutionResult con la respuesta.
        """
        import requests

        base_url = config.base_url.rstrip("/")
        timeout_s = config.timeout_ms / 1000.0

        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
        }
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        headers.update(config.headers_extra)

        try:
            resp = requests.post(
                f"{base_url}/messages",
                json=payload,
                headers=headers,
                timeout=timeout_s,
            )
            resp.raise_for_status()
            data = resp.json()

            content = ""
            content_blocks = data.get("content", [])
            if content_blocks:
                # Anthropic puede devolver múltiples bloques (text, tool_use)
                for block in content_blocks:
                    if block.get("type") == "text":
                        content += block.get("text", "")

            # Anthropic reporta usage.input_tokens + usage.output_tokens
            usage = data.get("usage", {})
            total_tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)

            return ExecutionResult(
                success=True,
                output=content,
                source="cloud",
                model=model,
                duration_ms=0.0,
                tokens_used=total_tokens,
            )

        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            detail = ""
            if exc.response is not None:
                try:
                    err = exc.response.json()
                    detail = err.get("error", {}).get("message", str(err))
                except Exception:
                    detail = exc.response.text[:200]
            return ExecutionResult(
                success=False,
                output="",
                source="cloud",
                model=model,
                duration_ms=0.0,
                error=(
                    f"Anthropic HTTP {status}: {detail}. "
                    "WHY: La API de Anthropic rechazó la solicitud. "
                    "WHERE: _execute_anthropic"
                ),
            )
        except Exception as exc:
            return ExecutionResult(
                success=False,
                output="",
                source="cloud",
                model=model,
                duration_ms=0.0,
                error=(
                    f"Anthropic error: {exc}. "
                    "WHY: Fallo en la comunicación con Anthropic. "
                    "WHERE: _execute_anthropic"
                ),
            )

    def _execute_google(
        self,
        config: ProviderConfig,
        api_key: str,
        model: str,
        prompt: str,
        max_tokens: int,
    ) -> ExecutionResult:
        """Ejecuta contra la API de Google Gemini.

        Args:
            config: Configuración del proveedor.
            api_key: API key de Google.
            model: Modelo (ej: "gemini-1.5-pro").
            prompt: Prompt de entrada.
            max_tokens: Máximo de tokens de salida.

        Returns:
            ExecutionResult con la respuesta.
        """
        import requests

        base_url = config.base_url.rstrip("/")
        timeout_s = config.timeout_ms / 1000.0

        # Gemini usa generateContent con estructura específica
        url = f"{base_url}/v1/models/{model}:generateContent"

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": max_tokens,
            },
        }
        headers = {
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        }
        headers.update(config.headers_extra)

        try:
            resp = requests.post(
                url, json=payload, headers=headers, timeout=timeout_s,
            )
            resp.raise_for_status()
            data = resp.json()

            # Extraer texto de la respuesta Gemini
            content = ""
            candidates = data.get("candidates", [])
            if candidates:
                content_parts = candidates[0].get("content", {}).get("parts", [])
                for part in content_parts:
                    content += part.get("text", "")

            # Gemini puede reportar usageMetadata
            usage = data.get("usageMetadata", {})
            total_tokens = usage.get("totalTokenCount", 0)

            return ExecutionResult(
                success=True,
                output=content,
                source="cloud",
                model=model,
                duration_ms=0.0,
                tokens_used=total_tokens,
            )

        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            detail = ""
            if exc.response is not None:
                try:
                    err = exc.response.json()
                    detail = err.get("error", {}).get("message", str(err))
                except Exception:
                    detail = exc.response.text[:200]
            return ExecutionResult(
                success=False,
                output="",
                source="cloud",
                model=model,
                duration_ms=0.0,
                error=(
                    f"Google Gemini HTTP {status}: {detail}. "
                    "WHY: La API de Gemini rechazó la solicitud. "
                    "WHERE: _execute_google"
                ),
            )
        except Exception as exc:
            return ExecutionResult(
                success=False,
                output="",
                source="cloud",
                model=model,
                duration_ms=0.0,
                error=(
                    f"Google Gemini error: {exc}. "
                    "WHY: Fallo en la comunicación con Gemini. "
                    "WHERE: _execute_google"
                ),
            )

    # ------------------------------------------------------------------
    # Health checks
    # ------------------------------------------------------------------

    def health_check(self, provider: Optional[str] = None) -> bool:
        """Ejecuta health check sobre uno o todos los proveedores.

        Args:
            provider: Nombre del proveedor. Si es None, verifica todos.

        Returns:
            True si el/los proveedor(es) están disponibles.

        WHY: Permite verificar disponibilidad bajo demanda, además de
        los chequeos periódicos en background.
        WHERE: health_check en MultiAPIProvider.
        """
        if provider is not None:
            return self._check_single_provider(provider)

        # Verificar todos los proveedores
        all_ok = True
        with self._lock:
            names = list(self._providers.keys())
        for pname in names:
            ok = self._check_single_provider(pname)
            all_ok = all_ok and ok
        return all_ok

    def _check_single_provider(self, name: str) -> bool:
        """Verifica disponibilidad de un proveedor individual.

        Realiza una solicitud liviana (listado de modelos o ping) para
        determinar si el proveedor responde.

        Args:
            name: Nombre del proveedor.

        Returns:
            True si el proveedor está disponible.
        """
        with self._lock:
            entry = self._providers.get(name)
            if entry is None:
                logger.warning(
                    "Health check: provider '%s' no registrado. WHERE: _check_single_provider",
                    name,
                )
                return False
            config = entry["config"]

        start = time.perf_counter()
        available = False
        try:
            import requests

            timeout_s = max(5.0, config.timeout_ms / 2000.0)  # mitad del timeout

            # Intentar obtener lista de modelos (liviano si el endpoint
            # soporta GET /models, o fallback a un POST mínimo)
            base_url = config.base_url.rstrip("/")
            api_key = os.environ.get(config.api_key_env, "")

            if config.name.lower() == "anthropic":
                # Anthropic no tiene GET /models pública sencilla; hacemos GET /
                resp = requests.get(
                    f"{base_url}/", timeout=timeout_s,
                    headers={"x-api-key": api_key},
                )
                available = resp.status_code < 500

            elif config.name.lower() == "google":
                # Google tiene GET /v1/models
                resp = requests.get(
                    f"{base_url}/v1/models",
                    timeout=timeout_s,
                    headers={"x-goog-api-key": api_key},
                )
                available = resp.status_code == 200

            else:
                # OpenAI-compatible: GET /models
                resp = requests.get(
                    f"{base_url}/models",
                    timeout=timeout_s,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                )
                available = resp.status_code == 200

        except Exception as exc:
            logger.debug(
                "Health check fail for '%s': %s. WHERE: _check_single_provider",
                name, exc,
            )
            available = False

        elapsed_ms = (time.perf_counter() - start) * 1000

        with self._lock:
            health = self._health.get(name)
            if health is None:
                health = ProviderHealth()
                self._health[name] = health

            health.last_check = time.time()
            health.available = available
            if available:
                health.last_success = time.time()
                health.consecutive_failures = 0
                health.status = ProviderStatus.AVAILABLE
                # Actualizar latencia con la del health check
                self._latency_history[name].append(elapsed_ms)
                self._update_percentiles(name, health)
            else:
                health.consecutive_failures += 1
                if health.consecutive_failures >= 3:
                    health.status = ProviderStatus.UNAVAILABLE
                else:
                    health.status = ProviderStatus.DEGRADED

        return available

    def _update_percentiles(self, name: str, health: ProviderHealth) -> None:
        """Actualiza los percentiles de latencia para un proveedor.

        Args:
            name: Nombre del proveedor.
            health: Objeto de salud a actualizar.
        """
        history = self._latency_history.get(name)
        if not history or len(history) < 5:
            return

        sorted_latencies = sorted(history)
        n = len(sorted_latencies)
        health.latency_p50 = sorted_latencies[int(n * 0.50)]
        health.latency_p95 = sorted_latencies[int(n * 0.95)]
        health.latency_p99 = sorted_latencies[int(n * 0.99)]

        # Calcular error rate en ventana
        total_reqs = self._request_counts.get(name, 1)
        errs = self._error_counts.get(name, 0)
        health.error_rate = errs / max(total_reqs, 1)

    def _start_health_checks(self) -> None:
        """Inicia el hilo de health checks periódicos en background.

        WHY: Los health checks automáticos aseguran que el estado de
        disponibilidad se mantenga actualizado sin intervención del
        llamante.
        WHERE: _start_health_checks.
        """
        if self._health_thread is not None and self._health_thread.is_alive():
            return

        self._health_stop.clear()

        def _loop() -> None:
            while not self._health_stop.is_set():
                try:
                    self.health_check()
                except Exception as exc:
                    logger.error(
                        "Health check background error: %s. "
                        "WHY: El hilo de health check no debe interrumpirse. "
                        "WHERE: _loop en _start_health_checks",
                        exc,
                    )
                self._health_stop.wait(HEALTH_CHECK_INTERVAL_S)

        self._health_thread = threading.Thread(
            target=_loop,
            name="mapi-healthcheck",
            daemon=True,
        )
        self._health_thread.start()
        logger.debug(
            "Health check background thread iniciado (intervalo=%ds). "
            "WHERE: _start_health_checks",
            HEALTH_CHECK_INTERVAL_S,
        )

    def stop_health_checks(self) -> None:
        """Detiene el hilo de health checks periódicos.

        WHY: Necesario para un shutdown limpio cuando la instancia ya
        no se necesita.
        WHERE: stop_health_checks.
        """
        self._health_stop.set()
        if self._health_thread is not None:
            self._health_thread.join(timeout=5.0)
            logger.debug(
                "Health check thread detenido. WHERE: stop_health_checks",
            )

    # ------------------------------------------------------------------
    # Round-robin y selección de proveedor
    # ------------------------------------------------------------------

    def _find_provider_for_model(self, model: str) -> Optional[str]:
        """Busca el proveedor óptimo para un modelo.

        Prioriza por tier (premium > standard > budget) y hace round-robin
        entre proveedores del mismo tier.

        Args:
            model: Nombre del modelo a buscar.

        Returns:
            Nombre del proveedor seleccionado, o None si no se encuentra.
        """
        with self._lock:
            # Agrupar proveedores por tier
            candidates_by_tier: Dict[str, List[str]] = defaultdict(list)
            for pname, entry in self._providers.items():
                cfg = entry["config"]
                health = self._health.get(pname)
                if health is not None and not health.available:
                    continue
                if model in cfg.models:
                    candidates_by_tier[cfg.tier].append(pname)

            # Probar tiers en orden
            tier_order = [
                ProviderTier.PREMIUM.value,
                ProviderTier.STANDARD.value,
                ProviderTier.BUDGET.value,
            ]

            for tier in tier_order:
                candidates = candidates_by_tier.get(tier, [])
                if not candidates:
                    continue

                # Round-robin dentro del tier
                idx = self._rr_indices[tier] % len(candidates)
                self._rr_indices[tier] = idx + 1
                return candidates[idx]

        return None

    def _get_other_providers_for_model(
        self, model: str, exclude: str,
    ) -> List[str]:
        """Retorna otros proveedores que ofrecen el modelo, ordenados por tier.

        Args:
            model: Modelo a buscar.
            exclude: Proveedor a excluir (el primario).

        Returns:
            Lista ordenada de proveedores alternativos.
        """
        candidates: List[Tuple[str, int]] = []
        tier_rank = {
            ProviderTier.PREMIUM.value: 0,
            ProviderTier.STANDARD.value: 1,
            ProviderTier.BUDGET.value: 2,
        }

        with self._lock:
            for pname, entry in self._providers.items():
                if pname == exclude:
                    continue
                cfg = entry["config"]
                health = self._health.get(pname)
                if health is not None and not health.available:
                    continue
                if model in cfg.models:
                    rank = tier_rank.get(cfg.tier, 99)
                    candidates.append((pname, rank))

        # Ordenar por tier (menor rank = mejor tier)
        candidates.sort(key=lambda x: x[1])
        return [c[0] for c in candidates]

    # ------------------------------------------------------------------
    # Cost tracking
    # ------------------------------------------------------------------

    def _track_cost(self, provider: str, model: str, total_tokens: int) -> float:
        """Registra el costo de una ejecución y retorna el monto.

        Distribuye proporcionalmente entre input/output estimando una
        relación 1:3 (output cuesta ~3x más por token).

        Args:
            provider: Nombre del proveedor.
            model: Nombre del modelo.
            total_tokens: Tokens totales consumidos (input + output).

        Returns:
            Costo estimado en USD.
        """
        cost = self._calculate_cost(provider, total_tokens)

        with self._lock:
            self._costs[provider] += cost
            self._model_costs[model] += cost
            self._request_counts[provider] += 1

        return cost

    def _calculate_cost(self, provider: str, total_tokens: int) -> float:
        """Calcula el costo estimado de una ejecución.

        Asume una proporción 70% input / 30% output como estimación
        cuando no se tiene el detalle.

        Args:
            provider: Nombre del proveedor.
            total_tokens: Tokens totales consumidos.

        Returns:
            Costo estimado en USD.
        """
        with self._lock:
            entry = self._providers.get(provider)
            if entry is None:
                return 0.0
            config = entry["config"]

        # Estimación: ~70% input, ~30% output
        input_tokens = int(total_tokens * 0.7)
        output_tokens = total_tokens - input_tokens

        cost_input = (input_tokens / 1000) * config.cost_per_1k_input
        cost_output = (output_tokens / 1000) * config.cost_per_1k_output

        return cost_input + cost_output

    def get_total_cost(self, provider: Optional[str] = None) -> float:
        """Retorna el costo total acumulado en USD.

        Args:
            provider: Nombre del proveedor. Si es None, suma todos.

        Returns:
            Costo total en USD.
        """
        with self._lock:
            if provider is not None:
                return self._costs.get(provider, 0.0)
            return sum(self._costs.values())

    # ------------------------------------------------------------------
    # Budget control
    # ------------------------------------------------------------------

    def set_budget(self, project: str, limit: float, alert_threshold: float = 0.8) -> None:
        """Establece un presupuesto máximo para un proyecto.

        Args:
            project: Identificador del proyecto.
            limit: Límite máximo en USD.
            alert_threshold: Fracción del límite para emitir alerta (default 0.8).

        Raises:
            ValueError: Si limit <= 0 o alert_threshold fuera de [0,1].

        WHY: Control de costos por proyecto para evitar sobrecostos no
        planificados.
        WHERE: set_budget en MultiAPIProvider.
        """
        if limit <= 0:
            raise ValueError(
                f"Budget limit debe ser > 0, recibido {limit}. "
                "WHY: Un presupuesto debe ser positivo. "
                "WHERE: set_budget"
            )
        if not 0 <= alert_threshold <= 1:
            raise ValueError(
                f"alert_threshold debe estar entre 0 y 1, recibido {alert_threshold}. "
                "WHY: La fracción de alerta debe ser un valor válido. "
                "WHERE: set_budget"
            )

        with self._lock:
            if project in self._budgets:
                existing = self._budgets[project]
                existing.limit = limit
                existing.alert_threshold = alert_threshold
                logger.info(
                    "Budget actualizado para '%s': $%.2f (threshold=%.0f%%). "
                    "WHERE: set_budget",
                    project, limit, alert_threshold * 100,
                )
            else:
                self._budgets[project] = BudgetLimit(
                    limit=limit,
                    alert_threshold=alert_threshold,
                )
                logger.info(
                    "Budget creado para '%s': $%.2f (threshold=%.0f%%). "
                    "WHERE: set_budget",
                    project, limit, alert_threshold * 100,
                )

    def check_budget(self, project: str) -> Tuple[float, float, bool]:
        """Verifica el estado del presupuesto de un proyecto.

        Args:
            project: Identificador del proyecto.

        Returns:
            Tupla (spent, limit, exceeded) donde exceeded es True si
            spent >= limit.
        """
        with self._lock:
            budget = self._budgets.get(project)
            if budget is None:
                return 0.0, 0.0, False

            exceeded = budget.spent >= budget.limit
            return budget.spent, budget.limit, exceeded

    def _allocate_cost_to_project(self, project: str, cost: float) -> None:
        """Asigna un costo a un proyecto y verifica límites.

        Args:
            project: Identificador del proyecto.
            cost: Costo en USD a asignar.
        """
        with self._lock:
            budget = self._budgets.get(project)
            if budget is None:
                return

            budget.spent += cost

            if budget.spent >= budget.limit:
                logger.warning(
                    "Proyecto '%s' ha excedido el presupuesto: $%.2f / $%.2f. "
                    "WHY: El límite de gasto fue alcanzado. "
                    "WHERE: _allocate_cost_to_project",
                    project, budget.spent, budget.limit,
                )
            elif budget.spent >= budget.limit * budget.alert_threshold:
                logger.info(
                    "Proyecto '%s' ha alcanzado %.0f%% del presupuesto: $%.2f / $%.2f. "
                    "WHERE: _allocate_cost_to_project",
                    project, budget.alert_threshold * 100, budget.spent, budget.limit,
                )

    # ------------------------------------------------------------------
    # Métricas y estadísticas
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Retorna estadísticas completas de todos los proveedores.

        Returns:
            Diccionario con métricas por proveedor, incluyendo estado,
            latencias, costos, tasas de error y conteo de requests.
        """
        stats: Dict[str, Any] = {
            "providers": {},
            "total_cost_usd": 0.0,
            "total_requests": 0,
            "global_health": ProviderStatus.UNKNOWN.value,
        }

        with self._lock:
            for pname in self._providers:
                config = self._providers[pname]["config"]
                health = self._health.get(pname)
                history = self._latency_history.get(pname)

                pstats: Dict[str, Any] = {
                    "tier": config.tier,
                    "models": config.models,
                    "health": {
                        "available": health.available if health else False,
                        "status": health.status.value if health else ProviderStatus.UNKNOWN.value,
                        "latency_p50_ms": round(health.latency_p50, 2) if health else 0.0,
                        "latency_p95_ms": round(health.latency_p95, 2) if health else 0.0,
                        "latency_p99_ms": round(health.latency_p99, 2) if health else 0.0,
                        "error_rate": round(health.error_rate, 4) if health else 0.0,
                        "consecutive_failures": health.consecutive_failures if health else 0,
                        "last_check": health.last_check if health else 0,
                    } if health else {},
                    "costs": {
                        "total_usd": round(self._costs.get(pname, 0.0), 6),
                    },
                    "requests": {
                        "total": self._request_counts.get(pname, 0),
                        "errors": self._error_counts.get(pname, 0),
                    },
                    "samples": len(history) if history else 0,
                }

                stats["providers"][pname] = pstats
                stats["total_cost_usd"] += self._costs.get(pname, 0.0)
                stats["total_requests"] += self._request_counts.get(pname, 0)

        stats["total_cost_usd"] = round(stats["total_cost_usd"], 6)

        # Determinar estado global
        all_available = all(
            self._health.get(p, ProviderHealth()).available
            for p in self._providers
        )
        any_available = any(
            self._health.get(p, ProviderHealth()).available
            for p in self._providers
        )

        if all_available and stats["providers"]:
            stats["global_health"] = ProviderStatus.AVAILABLE.value
        elif any_available:
            stats["global_health"] = ProviderStatus.DEGRADED.value
        else:
            stats["global_health"] = ProviderStatus.UNAVAILABLE.value

        return stats

    def get_provider_stats(self, name: str) -> Optional[Dict[str, Any]]:
        """Retorna estadísticas detalladas de un proveedor específico.

        Args:
            name: Nombre del proveedor.

        Returns:
            Diccionario con métricas del proveedor o None si no existe.
        """
        all_stats = self.get_stats()
        return all_stats.get("providers", {}).get(name)

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    def _record_success(self, provider: str, latency_ms: float) -> None:
        """Registra una ejecución exitosa y actualiza métricas de latencia.

        Args:
            provider: Nombre del proveedor.
            latency_ms: Latencia de la ejecución en milisegundos.
        """
        with self._lock:
            self._latency_history[provider].append(latency_ms)
            self._request_counts[provider] += 1

            health = self._health.get(provider)
            if health is not None:
                health.last_success = time.time()
                health.consecutive_failures = 0
                health.status = ProviderStatus.AVAILABLE
                health.available = True
                self._update_percentiles(provider, health)

    def _record_error(self, provider: str, error: str) -> None:
        """Registra un error de ejecución.

        Args:
            provider: Nombre del proveedor.
            error: Mensaje de error.
        """
        with self._lock:
            self._error_counts[provider] += 1
            self._request_counts[provider] += 1

            health = self._health.get(provider)
            if health is not None:
                health.consecutive_failures += 1
                if health.consecutive_failures >= 3:
                    health.status = ProviderStatus.UNAVAILABLE
                    health.available = False
                elif health.consecutive_failures >= 1:
                    health.status = ProviderStatus.DEGRADED

    def __del__(self) -> None:
        """Cleanup: detiene health checks al destruir la instancia."""
        self.stop_health_checks()


# ===================================================================
# ModelRouter (MEJORADO) — mantiene compatibilidad total hacia atrás
# ===================================================================


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
