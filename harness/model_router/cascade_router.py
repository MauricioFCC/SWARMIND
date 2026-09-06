"""cascade_router.py — Patron STEER-lite: intenta small, escala si hay duda.

Complementa a ``ComplexityRouter`` (decide una vez) con ejecucion en
cascada: corre el tier decidido y, si la confianza del resultado esta
bajo el umbral, escala al siguiente tier (small -> frontier). Cada
intento registra (route, confidence, cost) para calibrar thresholds
offline. Escape_hatch permite forzar un tier.

Frontera 2026: cascada sin router entrenado (STEER), distribucion
70% budget / 20% mid / 10% frontier (-60-80% vs todo-premium);
precios default calibrables (nano $0.20/MTok in, razonamiento $2/$8).

Uso:
    router = CascadeRouter(decide_fn=lambda t: ("small", 0.8))
    result = router.run(task, execute_fn)
    # result.final_route, result.attempts, result.total_cost_usd
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger("harness.model_router.cascade_router")

# ---------------------------------------------------------------------------
# Constantes (MAG — precios USD por millon de tokens, defaults calibrables)
# ---------------------------------------------------------------------------
#: Umbral de confianza bajo el cual se escala al siguiente tier.
DEFAULT_CONFIDENCE_THRESHOLD = 0.7
#: Maximo de intentos por run (small + escalado a frontier).
MAX_ATTEMPTS = 2
#: Hit de ratio bajo el cual el cache tiene bug estructural (ver tracker).
TOKENS_PER_MILLION = 1_000_000


@dataclass(frozen=True)
class TierPrice:
    """Precio USD por millon de tokens de un tier.

    Attributes:
        input_per_mtok: USD por millon de tokens de entrada.
        output_per_mtok: USD por millon de tokens de salida.
    """

    input_per_mtok: float
    output_per_mtok: float


#: Tabla de precios default (calibrable; fuentes: frontera jun-2026).
PRICE_TABLE: dict[str, TierPrice] = {
    "small": TierPrice(input_per_mtok=0.25, output_per_mtok=1.25),
    "frontier": TierPrice(input_per_mtok=5.0, output_per_mtok=25.0),
}

#: Orden de escalado de la cascada.
TIER_ORDER: tuple[str, ...] = ("small", "frontier")


@dataclass(frozen=True)
class CascadeAttempt:
    """Un intento de la cascada (auditable para calibracion offline).

    Attributes:
        route: Tier ejecutado.
        confidence: Confianza del resultado (0.0-1.0).
        cost_usd: Costo estimado del intento en USD.
        escalated: True si este intento es un escalado (no el inicial).
    """

    route: str
    confidence: float
    cost_usd: float
    escalated: bool = False


@dataclass(frozen=True)
class CascadeResult:
    """Resultado de la cascada con log de intentos y costo total.

    Attributes:
        final_route: Tier del ultimo intento (el que responde).
        attempts: Intentos en orden de ejecucion.
        total_cost_usd: Suma de costos de los intentos.
    """

    final_route: str
    attempts: tuple[CascadeAttempt, ...]
    total_cost_usd: float


class CascadeRouter:
    """Ejecutor en cascada small -> frontier con gate de confianza.

    Args:
        decide_fn: (task) -> (route, confidence) inicial. Route debe
            estar en TIER_ORDER.
        price_table: Precios por tier (default PRICE_TABLE).
        confidence_threshold: Bajo este valor se escala (default 0.7).
        max_attempts: Tope de intentos (default MAX_ATTEMPTS).
    """

    def __init__(
        self,
        decide_fn: Callable[[str], tuple[str, float]],
        price_table: dict[str, TierPrice] | None = None,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        max_attempts: int = MAX_ATTEMPTS,
    ) -> None:
        self._decide_fn = decide_fn
        self._price_table = price_table or PRICE_TABLE
        self._threshold = confidence_threshold
        self._max_attempts = max_attempts

    @property
    def price_table(self) -> dict[str, TierPrice]:
        """Tabla de precios vigente (para tests y calibracion)."""
        return self._price_table

    def run(
        self,
        task: str,
        execute_fn: Callable[[str, str], tuple[float, int, int]],
        force_tier: str | None = None,
    ) -> CascadeResult:
        """Ejecuta la cascada sobre la tarea.

        Args:
            task: Texto de la tarea (no vacio).
            execute_fn: (tier, task) -> (confidence, in_tokens, out_tokens).
            force_tier: Si se indica, ejecuta solo ese tier (escape hatch).

        Returns:
            CascadeResult con ruta final, intentos y costo total.

        Raises:
            ValueError: Si task esta vacio o el tier es desconocido.
        """
        if not task.strip():
            raise ValueError(
                "WHAT: task vacia. "
                "WHY: sin tarea no hay cascada que ejecutar. "
                "WHERE: CascadeRouter.run"
            )
        if force_tier is not None:
            self._require_known_tier(force_tier)
            return self._single_attempt(task, execute_fn, force_tier, escalated=False)
        route, _decided_confidence = self._decide_fn(task)
        self._require_known_tier(route)
        first = self._execute_attempt(task, execute_fn, route, escalated=False)
        if route == "small" and first.confidence < self._threshold:
            second = self._execute_attempt(task, execute_fn, "frontier", escalated=True)
            return self._build_result("frontier", (first, second))
        return self._build_result(route, (first,))

    def _single_attempt(
        self,
        task: str,
        execute_fn: Callable[[str, str], tuple[float, int, int]],
        tier: str,
        escalated: bool,
    ) -> CascadeResult:
        """Ejecuta un unico tier (escape hatch o ruta directa)."""
        attempt = self._execute_attempt(task, execute_fn, tier, escalated=escalated)
        return self._build_result(tier, (attempt,))

    def _execute_attempt(
        self,
        task: str,
        execute_fn: Callable[[str, str], tuple[float, int, int]],
        tier: str,
        escalated: bool,
    ) -> CascadeAttempt:
        """Ejecuta un tier y tasa su costo con la tabla de precios."""
        confidence, in_tokens, out_tokens = execute_fn(tier, task)
        price = self._price_table[tier]
        cost = (
            in_tokens * price.input_per_mtok + out_tokens * price.output_per_mtok
        ) / TOKENS_PER_MILLION
        logger.info(
            "cascade attempt route=%s confidence=%.2f cost_usd=%.6f escalated=%s",
            tier, confidence, cost, escalated,
        )
        return CascadeAttempt(
            route=tier, confidence=confidence, cost_usd=cost, escalated=escalated
        )

    @staticmethod
    def _build_result(
        final_route: str, attempts: tuple[CascadeAttempt, ...]
    ) -> CascadeResult:
        """Ensambla el resultado con el costo total."""
        total = sum(a.cost_usd for a in attempts)
        return CascadeResult(
            final_route=final_route, attempts=attempts, total_cost_usd=total
        )

    @staticmethod
    def _require_known_tier(tier: str) -> None:
        """Valida que el tier pertenezca a TIER_ORDER."""
        if tier not in TIER_ORDER:
            raise ValueError(
                f"WHAT: tier desconocido: {tier}. "
                f"WHY: debe ser uno de {list(TIER_ORDER)}. "
                f"WHERE: CascadeRouter._require_known_tier"
            )
