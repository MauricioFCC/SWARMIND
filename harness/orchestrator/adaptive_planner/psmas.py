"""AdaptivePlanner PSMAS — mixin con phase scheduling y compresion.

Extraccion mecanica de los metodos PSMAS de la clase ``AdaptivePlanner``
del modulo original ``harness/orchestrator/adaptive_planner.py`` (sin
cambios de logica ni firmas).
"""

from __future__ import annotations

import logging

from .constants import (
    ALWAYS_ACTIVE_AGENTS,
    PHASE_BUILDER,
    PHASE_GUARDIAN,
    PHASE_SCIENTIST,
    PSMAS_DEFAULT_WINDOW,
    PSMAS_MIN_AGENTS,
)
from .models import PhasePlan, PlanStrategy

logger = logging.getLogger(__name__)


class _PSMASMixin:
    """Mixin con los metodos de Phase-Scheduled Multi-Agent Systems."""

    def _apply_phase_scheduling(
        self,
        strategy: PlanStrategy,
        agents: list[str] | None,
        task_type: str,
    ) -> None:
        """
        Aplica phase scheduling PSMAS si hay suficientes agentes.

        Solo se activa cuando:
          - Hay 3+ agentes en la lista
          - La estrategia lo soporta (HYBRID o FAN_OUT_FAN_IN)

        Args:
            strategy: Estrategia seleccionada.
            agents: Lista de agentes disponibles.
            task_type: Tipo de tarea detectado.
        """
        if not agents or len(agents) < PSMAS_MIN_AGENTS:
            self._phase_plan = PhasePlan()
            return

        # Phase scheduling es más efectivo con estrategias multi-agente
        if strategy in (PlanStrategy.HYBRID, PlanStrategy.FAN_OUT_FAN_IN):
            self._phase_plan = PhasePlan(
                agent_phases=self._assign_agent_phases(agents, task_type),
                task_type=task_type,
            )
            logger.info(
                "PSMAS: phase plan asignado para %d agentes "
                "(estrategia=%s, tipo=%s)",
                len(agents), strategy.value, task_type,
            )
        else:
            # Con estrategias single/secuencial, fase 0 para todos
            self._phase_plan = PhasePlan(
                agent_phases={a: 0.0 for a in agents},
                task_type=task_type,
            )

    def _assign_agent_phases(
        self,
        agents: list[str],
        task_type: str,
    ) -> dict[str, float]:
        """
        Asigna fase angular (0-360°) a cada agente según PSMAS.

        La técnica PSMAS (arXiv 2604.17400, abril 2026) asigna fases
        angulares a los agentes para activarlos solo en su ventana
        programada, logrando 27.3% de reducción de tokens.

        Reglas de asignación:
          - builder/planner/coordinator → fase 0° (siempre activos)
          - scientist/researcher → fase 120°
          - guardian/quality/reviewer → fase 240°
          - Otros agentes sin dependencias → misma fase (paralelo)

        Args:
            agents: Lista de IDs de agentes.
            task_type: Tipo de tarea (influye en asignación).

        Returns:
            Dict[str, float] mapeando agente → fase en grados.
        """
        phases: dict[str, float] = {}
        n = len(agents)
        if n == 0:
            return phases

        # Contadores para distribución uniforme de agentes genéricos
        generic_idx = 0

        for agent in agents:
            agent_lower = agent.lower()

            # Agentes siempre activos en fase 0
            if agent_lower in ALWAYS_ACTIVE_AGENTS:
                phases[agent] = PHASE_BUILDER

            # Científicos / investigadores en fase 120°
            elif any(kw in agent_lower for kw in ("scientist", "research", "analyst")):
                phases[agent] = PHASE_SCIENTIST

            # Guardianes / revisores en fase 240°
            elif any(kw in agent_lower for kw in ("guardian", "quality", "review", "audit")):
                phases[agent] = PHASE_GUARDIAN

            else:
                # Agentes genéricos: distribuir uniformemente
                # Los que comparten fase pueden ejecutarse en paralelo
                if generic_idx % 3 == 0:
                    phases[agent] = PHASE_BUILDER
                elif generic_idx % 3 == 1:
                    phases[agent] = PHASE_SCIENTIST
                else:
                    phases[agent] = PHASE_GUARDIAN
                generic_idx += 1

        return phases

    def get_active_agents(
        self,
        agents: list[str],
        phase_degrees: float,
        window: float = PSMAS_DEFAULT_WINDOW,
    ) -> list[str]:
        """
        Retorna solo agentes dentro de la ventana angular desde ``phase_degrees``.

        Los agentes fuera de la ventana reciben context summaries
        comprimidos para ahorrar tokens.

        Args:
            agents: Lista de agentes a filtrar.
            phase_degrees: Fase actual del ciclo (0-360°).
            window: Ventana angular en grados (default 60°).

        Returns:
            Lista de agentes activos en la fase actual.
        """
        if not agents:
            return []

        # Sin plan de fases: todos activos
        if not self._phase_plan.agent_phases:
            return agents

        active: list[str] = []
        seen: set = set()

        # Primera pasada: agentes dentro de la ventana
        for agent in agents:
            agent_phase = self._phase_plan.agent_phases.get(agent, 0.0)
            # Distancia angular mínima (circular)
            diff = abs(agent_phase - phase_degrees) % 360.0
            diff = min(diff, 360.0 - diff)

            if diff <= window:
                active.append(agent)
                seen.add(agent)

        # Segunda pasada: siempre incluir agentes en fase 0 (críticos)
        for agent in agents:
            if agent in seen:
                continue
            agent_phase = self._phase_plan.agent_phases.get(agent, 0.0)
            if agent_phase == PHASE_BUILDER:
                active.append(agent)
                seen.add(agent)

        # Tercera pasada: si no hay activos, incluir los más cercanos
        if not active:
            # Encontrar agente más cercano a la fase actual
            closest = min(
                agents,
                key=lambda a: min(
                    abs(self._phase_plan.agent_phases.get(a, 0.0) - phase_degrees) % 360.0,
                    360.0 - abs(self._phase_plan.agent_phases.get(a, 0.0) - phase_degrees) % 360.0,
                ),
            )
            active.append(closest)

        logger.debug(
            "PSMAS get_active_agents: phase=%s, window=%s, "
            "activos=%d/%d",
            phase_degrees, window, len(active), len(agents),
        )

        return active

    def compress_context_for_idle(
        self,
        agent_id: str,
        context: str,
        target_tokens: int,
    ) -> str:
        """
        Comprime el contexto para agentes inactivos (solo envían summary).

        Extrae líneas con información esencial y descarta el resto,
        reduciendo drásticamente el consumo de tokens.

        Args:
            agent_id: ID del agente destino (para logging).
            context: Contexto original completo.
            target_tokens: Tokens objetivo para el resumen comprimido.

        Returns:
            Contexto comprimido (solo información esencial).
        """
        if not context:
            return ""

        # Estimación rápida de tokens (chars/4)
        estimated_tokens = max(1, len(context) // 4)
        if estimated_tokens <= target_tokens:
            return context

        # Líneas con información esencial
        essential_keywords = [
            "task:", "goal:", "objective:", "output:", "result:",
            "decision:", "conclusion:", "summary:", "resumen:",
            "requerim", "requisito", "api:", "endpoint:",
            "error:", "warning:", "critical:", "importante:",
            "strategy:", "plan:", "status:", "progress:",
        ]

        lines = context.split("\n")
        essential_lines: list[str] = []
        header_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Mantener encabezados de sección
            if stripped.startswith(("###", "===")):
                header_lines.append(stripped)
                continue

            # Mantener líneas con palabras clave
            if any(kw in stripped.lower() for kw in essential_keywords):
                essential_lines.append(stripped)

        # Combinar encabezados + líneas esenciales
        compressed = "\n".join(header_lines + essential_lines)

        # Si aún excede, truncar por tokens
        if len(compressed) // 4 > target_tokens:
            char_limit = target_tokens * 4
            compressed = compressed[:char_limit] + (
                "\n[...truncated for idle agent...]"
            )

        # Si no hay nada esencial, tomar las primeras líneas significativas
        if not compressed.strip():
            meaningful = [line for line in lines if line.strip()][
                :max(3, target_tokens // 10)
            ]
            compressed = "\n".join(meaningful)

        logger.debug(
            "PSMAS compress_context: agente=%s, %d → %d tokens (objetivo=%d)",
            agent_id, estimated_tokens, max(1, len(compressed) // 4),
            target_tokens,
        )

        return compressed

    def get_phase_plan(self) -> dict:
        """
        Obtiene el plan de fases PSMAS actual.

        Returns:
            Dict con agent_phases, task_type, window, created_at.
            Vacío si no hay phase scheduling activo.
        """
        return self._phase_plan.to_dict()
