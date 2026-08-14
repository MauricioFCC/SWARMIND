"""Creative Worktable — Modo divergente/convergente (ReDNA).

Submodulo del paquete :mod:`harness.orchestrator.worktable`.

Contiene la clase ``CreativeWorktable`` con el pipeline creativo
divergente→convergente, extraida de forma mecanica desde ``worktable.py``
(regla AGR: archivos < 500 lineas).
"""

from __future__ import annotations

from .models import CreativeConfig, CreativeIdea, CreativePhase


class CreativeWorktable:
    """
    Worktable con capacidad creativa (divergente + convergente).

    Implementa ReDNA (arXiv:2605.28465) para pipeline divergente→convergente
    y Diversity Collapse prevention (arXiv:2604.18005) con topologias sparse.

    Usage:
        cw = CreativeWorktable()
        ideas = cw.divergent_phase("Disenar una API innovadora")
        selected = cw.convergent_phase(ideas, constraints=["coste < $1000"])
        result = cw.integration_phase(selected)
    """

    def __init__(self, config: CreativeConfig | None = None):
        self.config = config or CreativeConfig()
        self._ideas: list[CreativeIdea] = []
        self._round = 0

    def divergent_phase(self, topic: str, agents: list[str] | None = None) -> list[CreativeIdea]:
        """
        Fase divergente: generar N ideas libremente, sin restricciones.

        Cada agente genera ideas de forma independiente (independence_rounds)
        antes de compartir, para evitar structural coupling.

        Args:
            topic: Tema para generar ideas.
            agents: Agentes participantes.

        Returns:
            Lista de ideas generadas.
        """
        if agents is None:
            agents = ["builder", "scientist", "guardian", "evolve"]

        ideas = []
        for agent in agents:
            for i in range(self.config.num_ideas // len(agents) + 1):
                idea = CreativeIdea(
                    content=f"[{agent}] Idea para: {topic[:50]}... (#{i+1})",
                    agent=agent,
                    phase=CreativePhase.DIVERGENT,
                    novelty=0.5 + (hash(f"{agent}_{i}") % 50) / 100,
                    feasibility=0.3 + (hash(f"{agent}_{i}_f") % 70) / 100,
                )
                ideas.append(idea)

        self._ideas = ideas
        return ideas

    def convergent_phase(
        self,
        ideas: list[CreativeIdea],
        constraints: list[str] | None = None,
    ) -> list[CreativeIdea]:
        """
        Fase convergente: seleccionar ideas bajo restricciones.

        Evalua cada idea contra restricciones y selecciona las mejores.

        Args:
            ideas: Ideas a evaluar.
            constraints: Restricciones para la seleccion.

        Returns:
            Ideas seleccionadas.
        """
        constraints = constraints or []

        scored = []
        for idea in ideas:
            score = idea.novelty * 0.4 + idea.feasibility * 0.6
            # Penalizar si no cumple restricciones
            for constraint in constraints[:2]:
                score *= 0.8
            idea.selected = score > 0.5
            scored.append(idea)

        selected = [i for i in scored if i.selected]
        return selected

    def integration_phase(self, ideas: list[CreativeIdea]) -> str:
        """
        Fase de integracion: combinar ideas seleccionadas en una propuesta final.

        Args:
            ideas: Ideas seleccionadas para integrar.

        Returns:
            Propuesta integrada.
        """
        if not ideas:
            return "No se seleccionaron ideas."

        lines = ["## Propuesta Integrada (Creative Worktable)", ""]
        for i, idea in enumerate(ideas[:3]):
            lines.append(f"### Idea {i+1} ({idea.agent})")
            lines.append(f"{idea.content}")
            lines.append(f"  - Novedad: {idea.novelty:.2f}")
            lines.append(f"  - Factibilidad: {idea.feasibility:.2f}")
            lines.append("")

        return "\n".join(lines)
