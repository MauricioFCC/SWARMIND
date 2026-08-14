"""Modelos de datos del enrutador por complejidad semantica.

Extraccion mecanica de las dataclasses ``ComplexityDecision`` y
``ComplexityResult`` del modulo original (sin cambios de logica ni firmas).

Classes:
    ComplexityDecision: Decision de enrutamiento (route, score, signals, reason).
    ComplexityResult: Resultado completo con metadatos y compatibilidad dict-like.

Referencia: RouteLLM (arXiv 2406.18665).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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
