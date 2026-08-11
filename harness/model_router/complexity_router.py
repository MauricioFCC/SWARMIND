"""
ModelRouter — Enrutamiento por complejidad semántica estilo RouteLLM (ADR-0041 H7).

Complementa a ModelRouter existente (harness/model_router/router.py), que enruta
por dominio/longitud. Este módulo estima la COMPLEJIDAD SEMÁNTICA de una tarea
score 0..100 mediante señales heurísticas y decide entre un modelo small y un
modelo frontier, con umbral calibrable en caliente y red de seguridad con
validación del modelo small (route_with_validation).

Referencia: RouteLLM (arXiv 2406.18665) — routing por dificultad para ahorrar
~2x en costo sin degradar calidad.

API pública:
- decide(task) -> ComplexityDecision  (señales activadas como tuple)
- route(task, model_preference=None) -> ComplexityResult  (API nueva)
- route(task, small_model, frontier_model) -> ComplexityResult dict-like (API legacy)
- route_with_validation(task, small, frontier, validate_small) -> ComplexityResult
- route_with_fallback(task, small_fn, frontier_fn) -> Any
- set_threshold(v) / threshold

Señales (features) y ponderaciones (verificadas aritméticamente en tests):
  - Longitud: >=800 +30 (long_high), >=400 +15 (long_medium), <=60 -15 (short)
  - Keywords de razonamiento: +50 (cap)
  - Dominio complejo (legal, ciencia, etc.): +20
  - Términos simples (formatea, traduce, etc.): -20
  - Múltiples instrucciones: +10
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes (sin magic numbers — todos nombrados)
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
SCORE_KEYWORD_REASONING: float = 50.0
SCORE_REASONING_MAX: float = 50.0
SCORE_COMPLEX_DOMAIN: float = 20.0
SCORE_SIMPLE_TERM: float = -20.0
SCORE_MULTI_INSTRUCTION: float = 10.0
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
    """Decisión de enrutamiento por complejidad semántica."""

    route: str  # "small" o "frontier"
    score: float  # complejidad estimada 0..100
    signals: tuple[str, ...]  # señales ACTIVADAS (nombres)
    reason: str  # explicacion legible

    def summary(self) -> str:
        """Resumen legible de la decisión para logs y UI."""
        return (
            f"route={self.route}, score={self.score:.1f}, "
            f"signals={', '.join(self.signals)}, reason={self.reason}"
        )


@dataclass(frozen=True)
class ComplexityResult:
    """Resultado completo de routing con metadatos.

    Implementa __getitem__ para compatibilidad con la API legacy
    (out["route"], out["model"], out["score"], out["reason"]).
    """

    decision: ComplexityDecision
    task_text: str
    model_route: str  # "small" or "frontier"
    estimated_savings_ratio: float  # factor esperado de ahorro de tokens (~2x en simple)
    confidence: float  # confianza en la decision (0.0–1.0)
    model: str = ""  # nombre del modelo seleccionado (compat legacy)

    def __getitem__(self, key: str) -> Any:
        """Acceso dict-style para compatibilidad con API legacy."""
        if key == "route":
            return self.decision.route
        if key == "model":
            return self.model
        if key == "score":
            return self.decision.score
        if key == "reason":
            return self.decision.reason
        raise KeyError(key)

    def __contains__(self, key: object) -> bool:
        """Soporta `"score" in out` sin iterar por índices (API legacy)."""
        return key in ("route", "model", "score", "reason")


class ComplexityRouter:
    """Router por complejidad semántica 0..100.

    Args:
        threshold: Umbral de complejidad (score >= umbral -> frontier).
        domain_hint: Pista de dominio complejo (ej. "legal") que inyecta
            la señal domain_complex aunque no haya keywords en el texto.
    """

    def __init__(
        self,
        threshold: float = DEFAULT_THRESHOLD,
        domain_hint: str | None = None,
    ) -> None:
        self.threshold = threshold
        self._domain_hint = domain_hint

    # -----------------------------------------------------------------
    # Señal extraction (heuristicas sobre el texto de la tarea)
    # -----------------------------------------------------------------

    def _extract_signals(self, task_text: str) -> dict[str, Any]:
        """Extrae señales heuristicas del texto de la tarea."""
        if not task_text:
            return {
                SIGNAL_SHORT_TASK: True,
                SIGNAL_KEYWORD_REASONING: False,
                SIGNAL_DOMAIN_COMPLEX: False,
                SIGNAL_SIMPLE_TASK_TERM: True,
                SIGNAL_MULTI_INSTRUCTION: False,
            }

        task_lower = task_text.lower()

        # 1. ¿Es una tarea corta? (<= 60 chars)
        is_short = len(task_text) <= LONG_LOW

        # 2. Keywords de razonamiento
        has_reasoning = any(kw in task_lower for kw in KEYWORD_REASONING)

        # 3. Dominio complejo (keywords o domain_hint explícito)
        has_complex_domain = any(
            kw in task_lower for kw in KEYWORD_COMPLEX_DOMAINS
        ) or bool(self._domain_hint)

        # 4. Términos simples (formatea, traduce, etc.)
        has_simple_term = any(kw in task_lower for kw in SIMPLE_TASK_TERMS)

        # 5. Múltiples instrucciones (comas o conectores lógicos)
        multi_instr = task_lower.count(", ") > 2 or any(
            conn in task_lower for conn in ["luego", "porque", "entonces", "ademas"]
        )

        return {
            SIGNAL_SHORT_TASK: is_short,
            SIGNAL_KEYWORD_REASONING: has_reasoning,
            SIGNAL_DOMAIN_COMPLEX: has_complex_domain,
            SIGNAL_SIMPLE_TASK_TERM: has_simple_term,
            SIGNAL_MULTI_INSTRUCTION: multi_instr,
        }

    def _long_signal(self, task_length: int) -> str | None:
        """Señal de longitud activada (None si el rango es neutral)."""
        if task_length >= LONG_HIGH:
            return SIGNAL_LONG_HIGH
        if task_length >= LONG_MED:
            return SIGNAL_LONG_MEDIUM
        if task_length <= LONG_LOW:
            return SIGNAL_SHORT_TASK
        return None

    def _compute_score(
        self, signals: dict[str, Any], task_length: int
    ) -> float:
        """Computa un score de complejidad 0..100 a partir de las señales."""
        score = SCORE_MIN

        # Señal de longitud (solo contribuye en rangos no-neutrales)
        long_signal = self._long_signal(task_length)
        if long_signal == SIGNAL_LONG_HIGH:
            score += SCORE_LENGTH_HIGH
        elif long_signal == SIGNAL_LONG_MEDIUM:
            score += SCORE_LENGTH_MEDIUM
        elif long_signal == SIGNAL_SHORT_TASK:
            score += SCORE_SHORT_TASK

        # Señal de razonamiento (cap 50)
        if signals.get(SIGNAL_KEYWORD_REASONING, False):
            score += SCORE_KEYWORD_REASONING

        # Señal de dominio complejo
        if signals.get(SIGNAL_DOMAIN_COMPLEX, False):
            score += SCORE_COMPLEX_DOMAIN

        # Señal de término simple (penaliza)
        if signals.get(SIGNAL_SIMPLE_TASK_TERM, False):
            score += SCORE_SIMPLE_TERM

        # Múltiples instrucciones (leva un poco)
        if signals.get(SIGNAL_MULTI_INSTRUCTION, False):
            score += SCORE_MULTI_INSTRUCTION

        # Clamp a 0..100
        return max(SCORE_MIN, min(SCORE_MAX, score))

    def _activated_signals(
        self, signals: dict[str, Any], long_signal: str | None
    ) -> tuple[str, ...]:
        """Nombres de las señales ACTIVADAS (tuple ordenada, sin duplicados)."""
        active: set[str] = {name for name, value in signals.items() if value}
        if long_signal:
            active.add(long_signal)
        return tuple(sorted(active))

    # -----------------------------------------------------------------
    # Decisión principal (API nueva)
    # -----------------------------------------------------------------

    def decide(self, task_text: str) -> ComplexityDecision:
        """Decide small vs frontier con señales heurísticas.

        Args:
            task_text: Texto descriptivo de la tarea.

        Returns:
            ComplexityDecision con route, score, señales activadas y razón.

        Raises:
            ValueError: Si task_text es vacío o solo espacios.
        """
        if not task_text or not task_text.strip():
            raise ValueError(
                "task_text cannot be empty. "
                "WHY: Sin texto no hay señales que extraer. "
                "WHERE: ComplexityRouter.decide"
            )

        signals = self._extract_signals(task_text)
        task_length = len(task_text)
        score = self._compute_score(signals, task_length)
        long_signal = self._long_signal(task_length)

        if score >= self.threshold:
            route = ROUTE_FRONTIER
            reason = (
                f"Complexity score {score:.1f} >= threshold {self.threshold}: "
                "frontier model for deep reasoning"
            )
        else:
            route = ROUTE_SMALL
            reason = (
                f"Complexity score {score:.1f} < threshold {self.threshold}: "
                "small model sufficient"
            )

        return ComplexityDecision(
            route=route,
            score=score,
            signals=self._activated_signals(signals, long_signal),
            reason=reason,
        )

    def _savings_ratio(self, score: float) -> float:
        """Factor estimado de ahorro según score (3x simple, 1.5x media, 1x frontier)."""
        if score < 30:
            return 3.0
        if score < 70:
            return 1.5
        return 1.0

    # -----------------------------------------------------------------
    # API corta route() (doble firma: nueva y legacy)
    # -----------------------------------------------------------------

    def route(
        self,
        task_text: str,
        model_preference: str | None = None,
        frontier_model: str | None = None,
    ) -> ComplexityResult:
        """
        Enruta una tarea al modelo appropriate.

        Doble firma compatible:
        - API nueva: route(task, model_preference=None) -> ComplexityResult
          (model_preference en {None, "small", "frontier"})
        - API legacy: route(task, small_model, frontier_model) -> ComplexityResult
          dict-like con model = small_model/frontier_model según la ruta.

        Args:
            task_text: Texto descriptivo de la tarea.
            model_preference: "small"/"frontier" para forzar ruta, o el
                nombre del modelo small en la firma legacy.
            frontier_model: Nombre del modelo frontier (solo firma legacy).

        Returns:
            ComplexityResult con decision, metadatos y modelo seleccionado.
        """
        # Detectar firma legacy: route(task, small_model, frontier_model)
        if (
            frontier_model is not None
            and model_preference not in (None, ROUTE_SMALL, ROUTE_FRONTIER)
        ):
            decision = self.decide(task_text)
            model = (
                model_preference
                if decision.route == ROUTE_SMALL
                else frontier_model
            )
            return ComplexityResult(
                decision=decision,
                task_text=task_text,
                model_route=decision.route,
                estimated_savings_ratio=self._savings_ratio(decision.score),
                confidence=self._confidence(decision.score),
                model=model,
            )

        # API nueva: manejar preferencia explícita o routing normal
        if not task_text:
            decision = ComplexityDecision(
                route=ROUTE_SMALL,
                score=0.0,
                signals=(),
                reason="Empty task routed to small model",
            )
            return ComplexityResult(
                decision=decision,
                task_text=task_text,
                model_route=ROUTE_SMALL,
                estimated_savings_ratio=1.0,
                confidence=1.0,
            )

        if model_preference in (ROUTE_SMALL, ROUTE_FRONTIER):
            signals = self._extract_signals(task_text)
            decision = ComplexityDecision(
                route=model_preference,
                score=float(
                    self._compute_score(signals, len(task_text))
                ),
                signals=self._activated_signals(
                    signals, self._long_signal(len(task_text))
                ),
                reason=f"Forced preference for {model_preference} model",
            )
            return ComplexityResult(
                decision=decision,
                task_text=task_text,
                model_route=model_preference,
                estimated_savings_ratio=self._savings_ratio(decision.score),
                confidence=0.8,  # baja confianza al saltar el router
            )

        decision = self.decide(task_text)
        return ComplexityResult(
            decision=decision,
            task_text=task_text,
            model_route=decision.route,
            estimated_savings_ratio=self._savings_ratio(decision.score),
            confidence=self._confidence(decision.score),
        )

    def _confidence(self, score: float) -> float:
        """Confianza en la decisión (más alta en scores extremos)."""
        return min(1.0, 0.5 + 0.01 * score)

    # -----------------------------------------------------------------
    # Red de seguridad: validación del modelo small
    # -----------------------------------------------------------------

    def route_with_validation(
        self,
        task_text: str,
        small_model: str,
        frontier_model: str,
        validate_small: Callable[[str], bool] | None = None,
    ) -> ComplexityResult:
        """
        Red de seguridad: escala a frontier si la validación del small falla.

        Reglas:
        - Ruta frontier: NUNCA escala hacia abajo ni ejecuta el validador.
        - Ruta small con validate_small=None: mantiene small (sin validar).
        - Ruta small con validate_small que retorna False o lanza: -> frontier.
        - Ruta small con validate_small que retorna True: mantiene small.

        Args:
            task_text: Texto de la tarea.
            small_model: Nombre del modelo small.
            frontier_model: Nombre del modelo frontier.
            validate_small: Callable que valida la salida del modelo small
                (True = válida, False = escalar).

        Returns:
            ComplexityResult dict-like con route/model finales.
        """
        decision = self.decide(task_text)

        # Ruta frontier: nunca valida ni baja
        if decision.route == ROUTE_FRONTIER:
            return ComplexityResult(
                decision=decision,
                task_text=task_text,
                model_route=ROUTE_FRONTIER,
                estimated_savings_ratio=self._savings_ratio(decision.score),
                confidence=self._confidence(decision.score),
                model=frontier_model,
            )

        # Ruta small: validar si hay validador
        if validate_small is None:
            return ComplexityResult(
                decision=decision,
                task_text=task_text,
                model_route=ROUTE_SMALL,
                estimated_savings_ratio=self._savings_ratio(decision.score),
                confidence=self._confidence(decision.score),
                model=small_model,
            )

        try:
            ok = validate_small(task_text)
        except Exception:  # noqa: BLE001 - fail-safe intencional: escalar a frontier
            logger.warning(
                "validate_small lanzó excepción; escalando a frontier. "
                "WHY: El validador no pudo confirmar la salida small. "
                "WHERE: ComplexityRouter.route_with_validation"
            )
            ok = False

        if ok:
            return ComplexityResult(
                decision=decision,
                task_text=task_text,
                model_route=ROUTE_SMALL,
                estimated_savings_ratio=self._savings_ratio(decision.score),
                confidence=self._confidence(decision.score),
                model=small_model,
            )

        # Validación falló -> escalar a frontier (mantener decisión original)
        escalated = ComplexityDecision(
            route=ROUTE_FRONTIER,
            score=decision.score,
            signals=decision.signals,
            reason=f"{decision.reason} | escalated: small validation failed",
        )
        return ComplexityResult(
            decision=escalated,
            task_text=task_text,
            model_route=ROUTE_FRONTIER,
            estimated_savings_ratio=1.0,
            confidence=self._confidence(decision.score),
            model=frontier_model,
        )

    # -----------------------------------------------------------------
    # Utilidad: routing con fallback (ejecuta funciones)
    # -----------------------------------------------------------------

    def route_with_fallback(
        self,
        task_text: str,
        small_fn: Callable[[str], Any],
        frontier_fn: Callable[[str], Any],
    ) -> Any:
        """
        Ejecuta small first; si falla o la confidence es baja, escala a frontier.

        Returns:
            El resultado de la función ganadora.
        """
        result = self.route(task_text)
        if result.decision.route == ROUTE_SMALL and result.confidence >= 0.7:
            logger.info("Routing to small model (confidence=%.2f)", result.confidence)
            return small_fn(task_text)
        else:
            logger.info(
                "Routing to frontier model (score=%.1f, confidence=%.2f)",
                result.decision.score,
                result.confidence,
            )
            return frontier_fn(task_text)

    # -----------------------------------------------------------------
    # Umbral calibrable en caliente
    # -----------------------------------------------------------------

    def set_threshold(self, value: float) -> None:
        """Recalibra el umbral de complejidad en caliente.

        Args:
            value: Nuevo umbral en [0, 100].

        Raises:
            ValueError: Si value está fuera de [0, 100].
        """
        if value < 0.0 or value > 100.0:
            raise ValueError(
                f"threshold must be in [0, 100], got {value}. "
                "WHY: Un umbral fuera de rango rompe la semántica del score. "
                "WHERE: ComplexityRouter.set_threshold"
            )
        self.threshold = value
