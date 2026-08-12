"""Epic Mode — Workflows multi-paso para tareas largas (Traycer-inspired).

Submodulo del paquete :mod:`harness.orchestrator.worktable`.

Contiene la clase ``EpicMode``, extraida de forma mecanica desde
``worktable.py`` (regla AGR: archivos < 500 lineas).
"""

from __future__ import annotations

from typing import Any

from .core import Worktable
from .models import Compendium


class EpicMode:
    """
    Modo Epico para tareas largas y estructuradas multi-paso.

    Ejecuta: Plan -> Execute -> Review -> Iterate hasta completar.
    Basado en Epic mode de Traycer y el pipeline DAG de TaskPlanner.

    Usage:
        epic = EpicMode()
        result = epic.run("Implementar sistema de autenticacion")
    """

    def __init__(self, max_iterations: int = 3) -> None:
        """
        Args:
            max_iterations: Maximo de iteraciones Plan->Execute->Review.
        """
        self._max_iterations = max_iterations
        self._artifacts: list[dict[str, Any]] = []

    def run(self, topic: str) -> Compendium:
        """
        Ejecutar workflow epico completo.

        Itera: Planear -> Ejecutar (creative debate) -> Revisar,
        rompiendo temprano si se detecta 'completo' o 'aceptado'.

        Args:
            topic: Tema o tarea a completar.

        Returns:
            Compendium con resumen del workflow epico.
        """
        wt = Worktable()
        current_topic = topic
        iteration = 0

        for iteration in range(self._max_iterations):
            # Plan
            plan = wt.debate(f"Planificar: {current_topic}", rounds=2)

            # Execute via creative debate
            execution = wt.debate(f"Ejecutar: {current_topic}",
                                  creative_mode=True, rounds=2)

            # Review
            review = wt.debate(f"Revisar: {current_topic}", rounds=2)

            self._artifacts.append({
                "iteration": iteration,
                "plan": plan.summary,
                "execution": execution.summary,
                "review": review.summary,
            })

            # Check if done
            if "completo" in review.summary.lower() or "aceptado" in review.summary.lower():
                break

        return Compendium(
            summary=f"Epic mode completado en {iteration + 1} iteraciones",
            agreements=[f"{len(self._artifacts)} artefactos generados"],
            trade_offs=[{"from": "EpicMode", "concern": "Iteraciones vs calidad"}],
            recommendations=["Revisar artefactos generados"],
        )
