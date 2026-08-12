"""Enrutamiento y red de seguridad (mixin ``_RoutingMixin``).

Extraccion mecanica de los metodos de decision/routing del modulo
original (sin cambios de logica ni firmas).

Classes:
    _RoutingMixin: Mixin con decide/route/route_with_validation/
        route_with_fallback/set_threshold usados por ``ComplexityRouter``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from .constants import ROUTE_FRONTIER, ROUTE_SMALL
from .models import ComplexityDecision, ComplexityResult

logger = logging.getLogger("harness.model_router.complexity_router")


class _RoutingMixin:
    """Mixin con las decisiones de enrutamiento y la red de seguridad."""

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
