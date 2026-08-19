"""Orquestador de debates multi-agente (extraccion mecanica).

Clase publica DebateOrchestrator: API principal (debate/consolidate),
dispatch por defecto y logging via AgentBus. Las estrategias y los
helpers de agregacion se heredan de mixins en submódulos contiguos.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from .aggregation import _AggregationMixin
from .models import DebateResult, DebateStrategy, DispatchFn
from .strategies import _StrategiesMixin

logger = logging.getLogger(__name__)

class DebateOrchestrator(_StrategiesMixin, _AggregationMixin):
    """
    Orchestrates multi-agent debate for complex tasks.

    The orchestrator uses a **dispatch function** to obtain agent responses.
    This indirection makes testing trivial (pass a mock) and keeps the
    orchestrator decoupled from LLM invocation.

    Each round of debate is logged via AgentBus for full traceability.

    Attributes:
        _store:   LanceVectorStore instance (optional).
        _bus:     AgentBus for inter-agent communication logging.
    """


    def __init__(self, vector_store: Any | None = None) -> None:
        """
        Args:
            vector_store: Optional LanceVectorStore for persistence.
        """
        from harness.orchestrator.agent_bus import AgentBus

        self._store = vector_store
        self._bus = AgentBus(vector_store=vector_store)

    def debate(
        self,
        task: str,
        agents: list[str],
        strategy: DebateStrategy = DebateStrategy.CONSENSUS,
        max_rounds: int = 2,
        dispatch_fn: DispatchFn | None = None,
    ) -> DebateResult:
        """
        Execute a multi-agent debate and return the consolidated result.

        Args:
            task: The task or question to debate.
            agents: List of agent names (e.g. ``["builder", "scientist"]``).
            strategy: The debate strategy to use.
            max_rounds: Maximum number of debate rounds (strategy-dependent).
            dispatch_fn: Optional callable to obtain agent responses.
                If omitted, a simple fallback is used (for testing).

        Returns:
            A DebateResult with the final answer and full debate history.

        Raises:
            ValueError: If the task is empty or fewer than 2 agents provided.
        """
        # --- Validation ---
        if not task or not task.strip():
            raise ValueError("Debate task cannot be empty.")
        if not agents or len(agents) < 2:
            raise ValueError("Debate requires at least 2 agents.")

        effective_agents = list(agents)
        effective_fn = dispatch_fn or self._default_dispatch

        session_id = str(uuid.uuid4())[:8]

        # Log debate start via AgentBus
        self._log_debate_start(session_id, task, strategy, effective_agents)

        # --- Strategy dispatch ---
        if strategy == DebateStrategy.CONSENSUS:
            result = self._execute_consensus(
                task, effective_agents, max_rounds, effective_fn, session_id,
            )
        elif strategy == DebateStrategy.CRITIQUE:
            result = self._execute_critique(
                task, effective_agents, max_rounds, effective_fn, session_id,
            )
        elif strategy == DebateStrategy.DELIBERATION:
            result = self._execute_deliberation(
                task, effective_agents, max_rounds, effective_fn, session_id,
            )
        else:
            raise ValueError(f"Unknown debate strategy: {strategy}")

        # Log debate result
        self._log_debate_result(result)

        return result

    @staticmethod
    def consolidate(result: DebateResult) -> str:
        """
        Extract the final consolidated answer from a debate result.

        Args:
            result: A completed DebateResult.

        Returns:
            The final answer as a string.
        """
        return result.final_answer

    @staticmethod
    def _default_dispatch(agent: str, task: str, context: dict[str, Any]) -> str:
        """
        Default dispatch function that returns a generic response.

        This is used when no ``dispatch_fn`` is provided to the ``debate()``
        method. It produces a templated response based on the agent name.
        """
        phase = context.get("phase", "unknown")
        templates = {
            "builder": (
                f"[Builder] Analisis de implementacion para: {task[:80]}.\n"
                f"Propongo una solucion modular con alta cohesion y bajo "
                f"acoplamiento, priorizando rendimiento y mantenibilidad."
            ),
            "scientist": (
                f"[Scientist] Analisis de investigacion para: {task[:80]}.\n"
                f"Revision de literatura y mejores practicas. "
                f"Recomiendo evaluar multiples alternativas antes de decidir."
            ),
            "guardian": (
                f"[Guardian] Revision de calidad para: {task[:80]}.\n"
                f"Verificando cobertura de tests, seguridad OWASP, "
                f"y documentacion completa."
            ),
            "coordinator": (
                f"[Coordinator] Facilitacion del debate para: {task[:80]}.\n"
                f"Coordinando perspectivas de todos los agentes para "
                f"consolidar una decision final."
            ),
        }

        base = templates.get(agent, f"[{agent}] Respondiendo a: {task[:80]}.")
        if phase == "conference_vote":
            other = context.get("other_answers", {})
            other_summary = "; ".join(
                f"{a}: {o[:60]}..." for a, o in other.items()
            )
            base += f"\nVoto tras revisar otros: {other_summary}"
        elif phase == "critique":
            context.get("answer_to_review", "")
            base += (
                "\nCritica a la respuesta propuesta:\n"
                "- Puntos fuertes: enfoque estructurado.\n"
                "- Areas de mejora: considerar mas casos borde, "
                "agregar metricas de validacion."
            )
        elif phase == "refinement":
            critique_text = context.get("critique", "")
            base += (
                f"\nRefinamiento incorporando critica:\n"
                f"{critique_text[:100]}... "
                f"Mejoras aplicadas al diseno original."
            )

        return base

    def _log_debate_start(
        self,
        session_id: str,
        task: str,
        strategy: DebateStrategy,
        agents: list[str],
    ) -> None:
        """Log the start of a debate session to AgentBus."""
        try:
            self._bus.post_message(
                channel=f"#debate-{session_id}",
                from_agent="@coordinator",
                to_agent="@all",
                message=(
                    f"ðŸŽ¯ **DEBATE INICIADO**\n"
                    f"Tarea: {task}\n"
                    f"Estrategia: {strategy.value}\n"
                    f"Agentes: {', '.join(agents)}"
                ),
                message_type="notification",
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Debate start log non-fatal: %s", exc)

    def _log_agent_message(
        self,
        session_id: str,
        agent: str,
        task: str,
        output: str,
        round_num: int,
        phase: str = "contribution",
    ) -> None:
        """Log an individual agent's contribution to AgentBus."""
        try:
            self._bus.post_message(
                channel=f"#debate-{session_id}",
                from_agent=f"@{agent}",
                to_agent="@coordinator",
                message=(
                    f"Ronda {round_num} [{phase}]:\n"
                    f"{output[:500]}"
                ),
                message_type="response",
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Agent message log non-fatal: %s", exc)

    def _log_debate_result(self, result: DebateResult) -> None:
        """Log the final debate result to AgentBus."""
        try:
            self._bus.post_message(
                channel=f"#debate-{result.session_id}",
                from_agent="@coordinator",
                to_agent="@all",
                message=(
                    f"✅ **DEBATE COMPLETADO**\n"
                    f"Estrategia: {result.strategy.value}\n"
                    f"Rondas: {len(result.rounds)}\n"
                    f"Confianza: {result.confidence:.2f}\n"
                    f"Acuerdo entre agentes: {result.agent_agreement:.2f}\n"
                    f"Respuesta final: {result.final_answer[:300]}"
                ),
                message_type="notification",
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Debate result log non-fatal: %s", exc)