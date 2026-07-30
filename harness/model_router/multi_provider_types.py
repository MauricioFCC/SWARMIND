"""MultiAPIProvider — Abstraccion multi-proveedor con fallover.

Gestiona multiples proveedores LLM (OpenAI, Anthropic, Google, Mistral, DeepSeek)
con registro dinamico, health checks, cost tracking y failover.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

# Constantes globales

# Tokens de salida por rol de agente (cuestan 3-5x más que input)
MAX_TOKENS_BY_AGENT: dict[str, int] = {
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

# Enums


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


# Dataclasses (compatibles con las originales + nuevas)


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
    error: str | None = None
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
    models: list[str]
    tier: str = ProviderTier.STANDARD.value
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    max_retries: int = 3
    timeout_ms: int = 30000
    headers_extra: dict[str, str] = field(default_factory=dict)

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


# MultiAPIProvider — Abstracción multi-provider con failover y balanceo


