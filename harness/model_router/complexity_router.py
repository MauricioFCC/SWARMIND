"""ComplexityRouter — Enrutamiento por complejidad semántica (estilo RouteLLM).

Complementa a ModelRouter (harness/model_router/router.py), que enruta por
dominio/longitud con fallback multi-proveedor. Este módulo estima la
COMPLEJIDAD SEMÁNTICA de una tarea (score 0..100) mediante señales
heurísticas y decide entre un modelo small y un modelo frontier, con umbral
calibrable en caliente y red de seguridad con validación del modelo small.

Referencia: RouteLLM (arXiv 2406.18665) — routing por dificultad para
ahorrar ~2x en costo sin degradar calidad.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

# Umbral por defecto de complejidad: score >= umbral -> frontier
DEFAULT_THRESHOLD: float = 50.0

# Umbrales de longitud de tarea (caracteres)
LONG_HIGH: int = 800
LONG_MED: int = 400
LONG_LOW: int = 60

# Ponderaciones de cada señal
SCORE_LENGTH_HIGH: float = 30.0
SCORE_LENGTH_MEDIUM: float = 15.0
SCORE_SHORT_TASK: float = -15.0
SCORE_KEYWORD_REASONING: float = 25.0
SCORE_REASONING_MAX: float = 50.0
SCORE_COMPLEX_DOMAIN: float = 20.0
SCORE_SIMPLE_TERM: float = -20.0
SCORE_MULTI_INSTRUCTION: float = 10.0
COMMA_MULTI_THRESHOLD: int = 3
SCORE_MIN: float = 0.0
SCORE_MAX: float = 100.0

# Vocabulario de señales
KEYWORD_REASONING: frozenset[str] = frozenset({
    "analiza", "razona", "compara", "sintetiza", "diseña", "arquitectura",
    "debug", "optimiza", "evalúa", "justifica", "deriva", "prueba", "demuestra",
})
KEYWORD_COMPLEX_DOMAINS: frozenset[str] = frozenset({
    "legal", "ciencia", "investigacion", "cuantitativo", "seguridad",
})
SIMPLE_TASK_TERMS: frozenset[str] = frozenset({
    "formatea", "traduce", "resume", "extrae", "clasifica", "lista", "renombra", "parsea",
})

# Nombres de señales y rutas
SIGNAL_SHORT_TASK: str = "short_task"
SIGNAL_LONG_MEDIUM: str = "long_medium"
SIGNAL_LONG_HIGH: str = "long_high"
SIGNAL_KEYWORD_REASONING: str = "keyword_reasoning"
SIGNAL_DOMAIN_COMPLEX: str = "domain_complex"
SIGNAL_SIMPLE_TASK_TERM: str = "simple_task_term"
SIGNAL_MULTI_INSTRUCTION: str = "multi_instruction"
ROUTE_SMALL: str = "small"
ROUTE_FRONTIER: str = "frontier"


@dataclass(frozen=True)
class ComplexityDecision:
    """Decisión de enrutamiento por complejidad semántica.

    Attributes:
        route: Ruta elegida ("small" o "frontier").
        score: Complejidad estimada de la tarea (0..100).
        signals: Señales que contribuyeron al score.
        reason: Explicación legible de la decisión.
    """

    route: str
    score: float
    signals: tuple[str, ...]
    reason: str

    def summary(self) -> str:
        """Devuelve un resumen legible de la decisión.

        Returns:
            Cadena con ruta, score, señales y razón.
        """
        signals_str = ", ".join(self.signals) if self.signals else "ninguna"
        return (
            f"ComplexityDecision(route={self.route}, score={self.score:.1f}, "
            f"signals=[{signals_str}]) -- {self.reason}"
        )


class ComplexityRouter:
    """Enrutador de tareas por complejidad semántica (estilo RouteLLM).

    Uso:
        router = ComplexityRouter()
        decision = router.decide("analiza y deriva la complejidad de este algoritmo")
        out = router.route(task, "gpt-4o-mini", "gpt-4o")
        out = router.route_with_validation(task, small, frontier, validate_small)
    """

    def __init__(self, threshold: float = DEFAULT_THRESHOLD, domain_hint: str | None = None):
        """Inicializa el router con umbral calibrable.

        Args:
            threshold: Umbral de complejidad en [0, 100]. score >= threshold
                se enruta a frontier.
            domain_hint: Dominio conocido de la tarea (ej. "legal"). Si es un
                dominio complejo, suma la señal de dominio complejo.

        Raises:
            ValueError: Si threshold no está en [0, 100].

        WHY: El umbral define el punto de corte entre ahorro (small) y
        calidad (frontier); debe validarse para evitar estados inválidos.
        WHERE: __init__ de ComplexityRouter.
        """
        self._validate_threshold(threshold)
        self.threshold: float = threshold
        self.domain_hint: str | None = domain_hint

    # -- scoring -----------------------------------------------------------

    def _score(self, task: str) -> tuple[float, tuple[str, ...]]:
        """Calcula la complejidad de una tarea (0..100) y sus señales.

        Args:
            task: Descripción de la tarea a puntuar.

        Returns:
            Tupla (score, signals) con la complejidad estimada y las señales
            que contribuyeron.

        Raises:
            ValueError: Si task está vacía.

        WHY: La complejidad se estima por señales heurísticas sumables que
        luego se convierten en una decisión de ruta.
        WHERE: _score de ComplexityRouter.
        """
        if not task or not task.strip():
            raise ValueError(
                "Tarea vacía no puede puntuarse. "
                "WHY: Sin texto no hay señales de complejidad que evaluar. "
                "WHERE: ComplexityRouter._score"
            )
        task_lower = task.lower()
        score = 0.0
        signals: list[str] = []
        score, signals = self._apply_length_signal(len(task), score, signals)
        score, signals = self._apply_reasoning_signal(task_lower, score, signals)
        score, signals = self._apply_domain_signal(task_lower, score, signals)
        score, signals = self._apply_simple_signal(task_lower, score, signals)
        score, signals = self._apply_multi_signal(task, score, signals)
        score = min(max(score, SCORE_MIN), SCORE_MAX)
        return score, tuple(signals)

    def _apply_length_signal(self, length: int, score: float, signals: list[str]) -> tuple[float, list[str]]:
        """Aplica la señal de longitud: larga alta/media o corta.

        Args:
            length: Longitud de la tarea en caracteres.
            score: Score acumulado.
            signals: Señales acumuladas.

        Returns:
            Tupla (score, signals) actualizada.
        """
        if length > LONG_HIGH:
            return score + SCORE_LENGTH_HIGH, signals + [SIGNAL_LONG_HIGH]
        if length > LONG_MED:
            return score + SCORE_LENGTH_MEDIUM, signals + [SIGNAL_LONG_MEDIUM]
        if length < LONG_LOW:
            return score + SCORE_SHORT_TASK, signals + [SIGNAL_SHORT_TASK]
        return score, signals

    def _apply_reasoning_signal(self, task_lower: str, score: float, signals: list[str]) -> tuple[float, list[str]]:
        """Aplica la señal de keywords de razonamiento (+25 c/u, máx +50).

        Args:
            task_lower: Tarea en minúsculas.
            score: Score acumulado.
            signals: Señales acumuladas.

        Returns:
            Tupla (score, signals) actualizada.
        """
        found = [kw for kw in KEYWORD_REASONING if kw in task_lower]
        if not found:
            return score, signals
        bonus = min(SCORE_REASONING_MAX, SCORE_KEYWORD_REASONING * len(found))
        return score + bonus, signals + [SIGNAL_KEYWORD_REASONING] * len(found)

    def _apply_domain_signal(self, task_lower: str, score: float, signals: list[str]) -> tuple[float, list[str]]:
        """Aplica la señal de dominio complejo (+20) desde el texto o domain_hint.

        Args:
            task_lower: Tarea en minúsculas.
            score: Score acumulado.
            signals: Señales acumuladas.

        Returns:
            Tupla (score, signals) actualizada.
        """
        if any(domain in task_lower for domain in KEYWORD_COMPLEX_DOMAINS):
            return score + SCORE_COMPLEX_DOMAIN, signals + [SIGNAL_DOMAIN_COMPLEX]
        if self.domain_hint and self.domain_hint.lower() in KEYWORD_COMPLEX_DOMAINS:
            return score + SCORE_COMPLEX_DOMAIN, signals + [SIGNAL_DOMAIN_COMPLEX]
        return score, signals

    def _apply_simple_signal(self, task_lower: str, score: float, signals: list[str]) -> tuple[float, list[str]]:
        """Aplica la señal de término de tarea simple (-20).

        Args:
            task_lower: Tarea en minúsculas.
            score: Score acumulado.
            signals: Señales acumuladas.

        Returns:
            Tupla (score, signals) actualizada.
        """
        if any(term in task_lower for term in SIMPLE_TASK_TERMS):
            return score + SCORE_SIMPLE_TERM, signals + [SIGNAL_SIMPLE_TASK_TERM]
        return score, signals

    def _apply_multi_signal(self, task: str, score: float, signals: list[str]) -> tuple[float, list[str]]:
        """Aplica la señal de múltiples instrucciones (+10) si hay >3 comas.

        Args:
            task: Tarea original.
            score: Score acumulado.
            signals: Señales acumuladas.

        Returns:
            Tupla (score, signals) actualizada.
        """
        if task.count(",") > COMMA_MULTI_THRESHOLD:
            return score + SCORE_MULTI_INSTRUCTION, signals + [SIGNAL_MULTI_INSTRUCTION]
        return score, signals

    # -- decisión ----------------------------------------------------------

    def decide(self, task: str) -> ComplexityDecision:
        """Decide la ruta por complejidad: small o frontier.

        Args:
            task: Descripción de la tarea a enrutar.

        Returns:
            ComplexityDecision con ruta, score, señales y razón.

        Raises:
            ValueError: Si task está vacía.

        WHY: El umbral separa tareas baratas (small) de tareas que exigen
        razonamiento frontier.
        WHERE: decide de ComplexityRouter.
        """
        score, signals = self._score(task)
        route = ROUTE_FRONTIER if score >= self.threshold else ROUTE_SMALL
        comparison = ">=" if route == ROUTE_FRONTIER else "<"
        reason = (
            f"Ruta '{route}': score {score:.1f} {comparison} umbral {self.threshold:.1f}; "
            f"señales: {self._signals_human(signals)}."
        )
        return ComplexityDecision(route=route, score=score, signals=signals, reason=reason)

    @staticmethod
    def _signals_human(signals: tuple[str, ...]) -> str:
        """Convierte señales en texto legible.

        Args:
            signals: Señales activadas.

        Returns:
            Lista separada por comas o "ninguna" si está vacía.
        """
        return ", ".join(signals) if signals else "ninguna"

    def route(self, task: str, small_model: str, frontier_model: str) -> dict[str, str]:
        """Enruta una tarea y devuelve el modelo elegido (API corta).

        Args:
            task: Descripción de la tarea a enrutar.
            small_model: Modelo a usar en rutas "small".
            frontier_model: Modelo a usar en rutas "frontier".

        Returns:
            Dict con "model", "route", "score" y "reason".

        Raises:
            ValueError: Si task está vacía.
        """
        decision = self.decide(task)
        model = small_model if decision.route == ROUTE_SMALL else frontier_model
        return {
            "model": model,
            "route": decision.route,
            "score": f"{decision.score:.1f}",
            "reason": decision.reason,
        }

    # -- umbral ------------------------------------------------------------

    def set_threshold(self, threshold: float) -> None:
        """Recalibra el umbral de complejidad en caliente.

        Args:
            threshold: Nuevo umbral en [0, 100].

        Raises:
            ValueError: Si threshold está fuera de [0, 100].

        WHY: Permite ajustar el punto de corte sin reiniciar el router,
        útil para calibrar ahorro vs. calidad en producción.
        WHERE: set_threshold de ComplexityRouter.
        """
        self._validate_threshold(threshold)
        self.threshold = threshold

    @staticmethod
    def _validate_threshold(threshold: float) -> None:
        """Valida que el umbral esté dentro de [0, 100].

        Args:
            threshold: Umbral a validar.

        Raises:
            ValueError: Si threshold < 0 o > 100.

        WHY: Un umbral fuera de rango produciría routing inconsistente.
        WHERE: _validate_threshold de ComplexityRouter.
        """
        if not SCORE_MIN <= threshold <= SCORE_MAX:
            raise ValueError(
                f"Threshold inválido: {threshold}. "
                "WHY: El umbral debe estar en [0, 100] para que el "
                "routing por complejidad sea consistente. "
                "WHERE: ComplexityRouter._validate_threshold"
            )

    # -- red de seguridad --------------------------------------------------

    def route_with_validation(
        self,
        task: str,
        small_model: str,
        frontier_model: str,
        validate_small: Callable[[str], bool] | None = None,
    ) -> dict[str, str]:
        """Enruta con red de seguridad: valida la ruta small antes de usarla.

        Si la ruta es "small" y validate_small devuelve False (o lanza una
        excepción), la decisión escala a frontier. Nunca escala hacia abajo
        y no ejecuta el validador en rutas frontier.

        Args:
            task: Descripción de la tarea a enrutar.
            small_model: Modelo a usar en rutas "small".
            frontier_model: Modelo a usar en rutas "frontier".
            validate_small: Callable(str) -> bool que valida que la tarea es
                apta para el modelo small. Si es None, no se valida.

        Returns:
            Dict con "model", "route", "score" y "reason".

        Raises:
            ValueError: Si task está vacía.

        WHY: Red de seguridad: si el modelo small no puede garantizar
        calidad (validación fallida o lanzada), se escala a frontier para
        no degradar el resultado. Ahorro con fallback controlado.
        WHERE: route_with_validation de ComplexityRouter.
        """
        decision = self.decide(task)
        if decision.route == ROUTE_SMALL and validate_small is not None:
            decision = self._maybe_escalate(decision, task, validate_small)
        model = small_model if decision.route == ROUTE_SMALL else frontier_model
        return {
            "model": model,
            "route": decision.route,
            "score": f"{decision.score:.1f}",
            "reason": decision.reason,
        }

    def _maybe_escalate(
        self,
        decision: ComplexityDecision,
        task: str,
        validate_small: Callable[[str], bool],
    ) -> ComplexityDecision:
        """Escala a frontier si la validación del modelo small falla.

        Args:
            decision: Decisión original (ruta small).
            task: Tarea enrutada.
            validate_small: Validador del modelo small.

        Returns:
            Decisión escalada a frontier o la original si la validación pasa.

        WHY: La validación puede fallar o lanzar; en ambos casos la red de
        seguridad prefiere frontier sobre un resultado no garantizado.
        WHERE: _maybe_escalate de ComplexityRouter.
        """
        try:
            is_valid = validate_small(task)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Validador small lanzó excepción; se escala a frontier: %s. "
                "WHY: No se asume apta una tarea que no pudo validarse. "
                "WHERE: ComplexityRouter._maybe_escalate",
                exc,
            )
            is_valid = False
        if is_valid:
            return decision
        return ComplexityDecision(
            route=ROUTE_FRONTIER,
            score=decision.score,
            signals=decision.signals,
            reason=decision.reason + " Escalada a frontier por validación fallida.",
        )
