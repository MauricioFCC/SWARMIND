"""Orquestador de debates multi-agente (extraccion mecanica).

Clase publica DebateOrchestrator: API principal (debate/consolidate),
dispatch por defecto y logging via AgentBus. Las estrategias y los
helpers de agregacion se heredan de mixins en submódulos contiguos.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from harness.failure_registry import (
    FailureRegistry,
    FailureType,
    Severity,
)
from harness.failure_registry import registry as _default_failure_registry
from harness.orchestrator.minority_sentinel import MinoritySentinel

from .aggregation import _AggregationMixin
from .models import (
    CONVERGENCE_THRESHOLD,
    NO_CONSENSUS_AGREEMENT_THRESHOLD,
    DebateResult,
    DebateStrategy,
    DispatchFn,
)
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


    def __init__(
        self,
        vector_store: Any | None = None,
        *,
        failure_registry: FailureRegistry | None = None,
        sentinel: MinoritySentinel | None = None,
    ) -> None:
        """
        Args:
            vector_store: Optional LanceVectorStore for persistence.
            failure_registry: Registry de fallos inyectable (DI). Default: el
                singleton ``harness.failure_registry.registry``. Inyectar uno
                aislado en tests evita escribir en ``db/failures.jsonl``.
            sentinel: MinoritySentinel opcional (DI) para mayoria revertible.
                Si se inyecta, tras agregar la mayoria en ``_majority_winner``
                se pasa por ``sentinel.review`` (ACL 2026). Default None =>
                comportamiento actual (backward-compat).
        """
        from harness.orchestrator.agent_bus import AgentBus

        self._store = vector_store
        self._bus = AgentBus(vector_store=vector_store)
        self._sentinel = sentinel

        # Registry de fallos para drenar debates sin consenso
        # (failure distillation)
        self._failure_registry = (
            failure_registry
            if failure_registry is not None
            else _default_failure_registry
        )

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
        result = self._dispatch_strategy(
            task, effective_agents, strategy, max_rounds, effective_fn, session_id,
        )

        # Log debate result
        self._log_debate_result(result)

        # Failure distillation: drenar debates sin consenso
        if result.agent_agreement < NO_CONSENSUS_AGREEMENT_THRESHOLD:
            self._drain_debate_failure_to_registry(result)

        return result

    async def debate_async(
        self,
        task: str,
        agents: list[str],
        strategy: DebateStrategy = DebateStrategy.CONSENSUS,
        max_rounds: int = 2,
        dispatch_fn: DispatchFn | None = None,
        convergence_threshold: float = CONVERGENCE_THRESHOLD,
    ) -> DebateResult:
        """
        Ejecuta un debate multi-agente por la ruta asincrona.

        Para ``CONSENSUS`` usa la estrategia paralela
        (``_execute_consensus_async``, PaCoRe: latencia O(n) -> O(1)). Para
        ``CRITIQUE``/``DELIBERATION`` delega en la ruta sincrona via
        ``asyncio.to_thread`` (su logica es inherentemente secuencial).
        Comparte validacion, logging y failure distillation con ``debate``
        (ruta sync, que permanece sin cambios).

        Args:
            task: Tarea o pregunta a debatir.
            agents: Nombres de agentes (minimo 2).
            strategy: Estrategia de debate a usar.
            max_rounds: Maximo de rondas de debate.
            dispatch_fn: Callable ``(agent, task, context) -> str``. Si se
                omite, se usa ``_default_dispatch``.
            convergence_threshold: Umbral de convergencia para el consenso
                async (solo aplica a ``CONSENSUS``).

        Returns:
            DebateResult con la respuesta final y el historial del debate.

        Raises:
            ValueError: Si la tarea esta vacia o hay menos de 2 agentes.
        """
        # --- Validation ---
        if not task or not task.strip():
            raise ValueError("Debate task cannot be empty.")
        if not agents or len(agents) < 2:
            raise ValueError("Debate requires at least 2 agents.")

        effective_agents = list(agents)
        effective_fn = dispatch_fn or self._default_dispatch
        session_id = str(uuid.uuid4())[:8]

        self._log_debate_start(session_id, task, strategy, effective_agents)

        # --- Strategy dispatch (async) ---
        if strategy == DebateStrategy.CONSENSUS:
            result = await self._execute_consensus_async(
                task, effective_agents, max_rounds, effective_fn, session_id,
                convergence_threshold=convergence_threshold,
            )
        else:
            result = await asyncio.to_thread(
                self._dispatch_strategy,
                task, effective_agents, strategy, max_rounds, effective_fn, session_id,
            )

        self._log_debate_result(result)

        # Failure distillation: drenar debates sin consenso
        if result.agent_agreement < NO_CONSENSUS_AGREEMENT_THRESHOLD:
            self._drain_debate_failure_to_registry(result)

        return result

    def _dispatch_strategy(
        self,
        task: str,
        agents: list[str],
        strategy: DebateStrategy,
        max_rounds: int,
        dispatch_fn: DispatchFn,
        session_id: str,
    ) -> DebateResult:
        """
        Selecciona y ejecuta la estrategia de debate (ruta sincrona).

        Args:
            task: Tarea a debatir.
            agents: Agentes participantes.
            strategy: Estrategia a ejecutar.
            max_rounds: Maximo de rondas.
            dispatch_fn: Callable de dispatch.
            session_id: ID de sesion.

        Returns:
            DebateResult de la estrategia seleccionada.

        Raises:
            ValueError: Si la estrategia no es conocida.
        """
        if strategy == DebateStrategy.CONSENSUS:
            return self._execute_consensus(
                task, agents, max_rounds, dispatch_fn, session_id,
            )
        if strategy == DebateStrategy.CRITIQUE:
            return self._execute_critique(
                task, agents, max_rounds, dispatch_fn, session_id,
            )
        if strategy == DebateStrategy.DELIBERATION:
            return self._execute_deliberation(
                task, agents, max_rounds, dispatch_fn, session_id,
            )
        raise ValueError(f"Unknown debate strategy: {strategy}")

    def _drain_debate_failure_to_registry(self, result: DebateResult) -> None:
        """Drena un debate sin consenso al FailureRegistry central.

        Persiste un ``FailureRecord`` cuando el ``agent_agreement`` del
        resultado cae por debajo de ``NO_CONSENSUS_AGREEMENT_THRESHOLD``: los
        agentes no convergieron en una respuesta comun. WHY: alimenta el loop
        de auto-mejora para destilar el patron de desacuerdo en skills
        (failure distillation, arXiv 2607.29468 SESA).

        Es tolerante a fallos de persistencia: si el registry lanza OSError
        se loguea un warning y NO se propaga. WHY: el resultado del debate no
        debe romper por la persistencia del fallo (el drain es best-effort).

        Args:
            result: Resultado del debate con ``agent_agreement`` bajo.
        """
        agents = result.metadata.get("agents", [])
        agents_text = ", ".join(str(a) for a in agents) or "(desconocidos)"
        try:
            self._failure_registry.record(
                task=result.task,
                failure_type=FailureType.RUNTIME,
                error_msg=(
                    f"Debate sin consenso: strategy="
                    f"'{result.strategy.value}' agents=[{agents_text}] "
                    f"agent_agreement={result.agent_agreement:.2f}"
                ),
                root_cause=(
                    f"Los agentes [{agents_text}] no alcanzaron consenso en la "
                    f"tarea '{result.task[:80]}' con estrategia "
                    f"'{result.strategy.value}': agent_agreement="
                    f"{result.agent_agreement:.2f} < "
                    f"{NO_CONSENSUS_AGREEMENT_THRESHOLD}"
                ),
                resolution="pending",
                severity=Severity.MEDIUM,
                function_name="DebateOrchestrator.debate",
                tags=("debate", result.strategy.value),
            )
        except OSError as exc:
            logger.warning(
                "WHAT=no se pudo persistir el fallo de debate en "
                "FailureRegistry WHY=%s WHERE=DebateOrchestrator."
                "_drain_debate_failure_to_registry (el resultado del debate "
                "se devolvio igual; el drain es best-effort)",
                exc,
            )

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