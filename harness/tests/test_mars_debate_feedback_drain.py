"""Tests del drenaje de fallos de MARS y Debate al FailureRegistry.

Cubre el cableado FR (failure distillation, arXiv 2607.29468 SESA) para los
dos orquestadores que faltaban, replicando el patron ya establecido en
``AdaptivePlanner`` (ver ``test_adaptive_planner_feedback_drain.py``):

Hilo 1 — MARS scheduler:
  (a) una tarea con ``success=False`` drena 1 fallo con tags incluyendo
      ``"mars"``;
  (b) una tarea con ``success=True`` NO drena;
  (c) un registry inyectado que lanza OSError NO rompe el scheduler.

Hilo 2 — Debate orchestrator:
  (d) un resultado sin consenso (``agent_agreement`` bajo) drena 1 fallo con
      tags incluyendo ``"debate"``;
  (e) un resultado con consenso NO drena;
  (f) un registry inyectado que lanza OSError NO rompe el debate.

Ademas verifica la inyeccion por DI (registry aislado, no el singleton real).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from harness.failure_registry import FailureRegistry, FailureType, Severity
from harness.orchestrator.debate_orchestrator import (
    DebateOrchestrator,
    DebateStrategy,
)
from harness.orchestrator.mars_scheduler import MARSScheduler, TaskSpec

MARS_LOGGER = "harness.orchestrator.mars_scheduler.scheduling_mixin"
DEBATE_LOGGER = "harness.orchestrator.debate_orchestrator.orchestrator"

# ---------------------------------------------------------------------------
# Fixtures y helpers compartidos
# ---------------------------------------------------------------------------


@pytest.fixture
def registry(tmp_path: Path) -> FailureRegistry:
    """FailureRegistry aislado en directorio temporal (no toca el real)."""
    return FailureRegistry(path=tmp_path / "failures.jsonl")


class _ExplodingRegistry:
    """Registry fake que siempre falla al persistir (simula OSError)."""

    def record(self, **kwargs: object) -> None:
        """Simula un fallo de persistencia del registry real."""
        raise OSError("disco lleno (simulado)")


# ---------------------------------------------------------------------------
# Hilo 1 — MARS scheduler
# ---------------------------------------------------------------------------


def _run_mars_task(
    scheduler: MARSScheduler,
    *,
    success: bool,
    task_id: str = "t1",
    task_type: str = "code_gen",
    description: str = "implementar endpoint REST",
    agent_id: str = "builder",
    latency: float = 2.0,
    cost: float = 150.0,
) -> None:
    """Registra un agente, planifica una tarea y reporta su outcome."""
    scheduler.register_agent(agent_id, skills={"code": 1.0})
    task = TaskSpec(
        task_id=task_id,
        task_type=task_type,
        value=10,
        skills_needed={"code": 0.5},
        description=description,
    )
    assignment = scheduler.schedule_task(task)
    assert assignment is not None, "la tarea debe asignarse para poder fallar"
    scheduler.record_outcome(task_id, assignment.agent_id, success, latency, cost)


class TestMARSDrainRecordsFailure:
    """Con success=False el scheduler debe drenar un FailureRecord."""

    def test_records_single_failure(self, registry: FailureRegistry) -> None:
        """Una tarea fallida deja exactamente 1 registro."""
        scheduler = MARSScheduler(exploration_rate=0.0, failure_registry=registry)
        _run_mars_task(scheduler, success=False)
        assert len(registry) == 1

    def test_failure_type_and_severity(self, registry: FailureRegistry) -> None:
        """El fallo debe ser RUNTIME/MEDIUM con resolution pending."""
        scheduler = MARSScheduler(exploration_rate=0.0, failure_registry=registry)
        _run_mars_task(scheduler, success=False)
        record = registry.get_recent(1)[0]
        assert record.failure_type is FailureType.RUNTIME
        assert record.severity is Severity.MEDIUM
        assert record.resolution == "pending"

    def test_tags_include_mars_and_agent(self, registry: FailureRegistry) -> None:
        """Los tags deben incluir 'mars' y el agente asignado."""
        scheduler = MARSScheduler(exploration_rate=0.0, failure_registry=registry)
        _run_mars_task(scheduler, success=False, agent_id="builder")
        record = registry.get_recent(1)[0]
        assert "mars" in record.tags
        assert "builder" in record.tags

    def test_error_and_root_cause_cite_latency_cost_and_agent(
        self, registry: FailureRegistry,
    ) -> None:
        """error_msg y root_cause deben citar latencia, costo y agente."""
        scheduler = MARSScheduler(exploration_rate=0.0, failure_registry=registry)
        _run_mars_task(
            scheduler, success=False, latency=2.5, cost=175.0, agent_id="builder",
        )
        record = registry.get_recent(1)[0]
        for text in (record.error_msg, record.root_cause):
            assert "2.50" in text
            assert "builder" in text

    def test_task_uses_description(self, registry: FailureRegistry) -> None:
        """La tarea del fallo debe reflejar la descripcion de la TaskSpec."""
        scheduler = MARSScheduler(exploration_rate=0.0, failure_registry=registry)
        _run_mars_task(
            scheduler, success=False, description="desplegar microservicio en k8s",
        )
        record = registry.get_recent(1)[0]
        assert "desplegar microservicio en k8s" in record.task


class TestMARSSuccessDoesNotRecord:
    """Con success=True el scheduler NO debe drenar nada."""

    def test_success_does_not_record(self, registry: FailureRegistry) -> None:
        """Una tarea exitosa no deja registros."""
        scheduler = MARSScheduler(exploration_rate=0.0, failure_registry=registry)
        _run_mars_task(scheduler, success=True)
        assert len(registry) == 0


class TestMARSDrainResilience:
    """El drain de MARS no debe propagar fallos de persistencia."""

    def test_oserror_does_not_break_scheduler(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Un OSError del registry solo genera warning, no excepcion."""
        scheduler = MARSScheduler(
            exploration_rate=0.0, failure_registry=_ExplodingRegistry(),
        )
        with caplog.at_level(logging.WARNING, logger=MARS_LOGGER):
            _run_mars_task(scheduler, success=False)
        assert "FailureRegistry" in caplog.text

    def test_outcome_still_recorded_in_scheduler(self) -> None:
        """Aunque el drain falle, el scheduler conserva el outcome."""
        scheduler = MARSScheduler(
            exploration_rate=0.0, failure_registry=_ExplodingRegistry(),
        )
        _run_mars_task(scheduler, success=False)
        assert scheduler._total_failures == 1
        assert len(scheduler.get_completed_history()) == 1


class TestMARSDependencyInjection:
    """La inyeccion debe respetar el registry provisto y el default."""

    def test_injected_registry_is_used(self, registry: FailureRegistry) -> None:
        """El scheduler debe usar el registry inyectado, no el singleton."""
        scheduler = MARSScheduler(failure_registry=registry)
        assert scheduler._failure_registry is registry

    def test_default_is_module_singleton(self) -> None:
        """Sin inyeccion, el default es el singleton del paquete."""
        from harness.failure_registry import registry as module_registry

        scheduler = MARSScheduler()
        assert scheduler._failure_registry is module_registry


# ---------------------------------------------------------------------------
# Hilo 2 — Debate orchestrator
# ---------------------------------------------------------------------------


def _disagreeing_dispatch(agent: str, task: str, context: dict[str, Any]) -> str:
    """Dispatch que produce respuestas divergentes (sin consenso)."""
    responses = {
        "builder": "Implementar con Rust y Axum.",
        "scientist": "Implementar con Go y Gin.",
        "guardian": "Implementar con Python y FastAPI.",
    }
    return responses.get(agent, "Opcion neutral sin aporte.")


def _agreeing_dispatch(agent: str, task: str, context: dict[str, Any]) -> str:
    """Dispatch que produce respuestas identicas (consenso total)."""
    return "Implementar con Rust y Axum, con tests y documentacion."


def _make_orchestrator(registry: FailureRegistry) -> DebateOrchestrator:
    """Crea un DebateOrchestrator con registry aislado (sin LanceDB)."""
    return DebateOrchestrator(vector_store=None, failure_registry=registry)


class TestDebateDrainRecordsFailure:
    """Sin consenso el debate debe drenar un FailureRecord."""

    def test_no_consensus_records_single_failure(
        self, registry: FailureRegistry,
    ) -> None:
        """Un debate sin consenso deja exactamente 1 registro."""
        orch = _make_orchestrator(registry)
        result = orch.debate(
            task="Elegir framework para la API",
            agents=["builder", "scientist", "guardian"],
            strategy=DebateStrategy.CONSENSUS,
            max_rounds=1,
            dispatch_fn=_disagreeing_dispatch,
        )
        assert result.agent_agreement < 0.5
        assert len(registry) == 1

    def test_failure_type_and_severity(self, registry: FailureRegistry) -> None:
        """El fallo debe ser RUNTIME/MEDIUM con resolution pending."""
        orch = _make_orchestrator(registry)
        orch.debate(
            task="Elegir framework para la API",
            agents=["builder", "scientist", "guardian"],
            strategy=DebateStrategy.CONSENSUS,
            max_rounds=1,
            dispatch_fn=_disagreeing_dispatch,
        )
        record = registry.get_recent(1)[0]
        assert record.failure_type is FailureType.RUNTIME
        assert record.severity is Severity.MEDIUM
        assert record.resolution == "pending"

    def test_tags_include_debate_and_strategy(
        self, registry: FailureRegistry,
    ) -> None:
        """Los tags deben incluir 'debate' y la estrategia usada."""
        orch = _make_orchestrator(registry)
        orch.debate(
            task="Elegir framework para la API",
            agents=["builder", "scientist", "guardian"],
            strategy=DebateStrategy.CONSENSUS,
            max_rounds=1,
            dispatch_fn=_disagreeing_dispatch,
        )
        record = registry.get_recent(1)[0]
        assert "debate" in record.tags
        assert DebateStrategy.CONSENSUS.value in record.tags

    def test_error_and_root_cause_cite_strategy_and_agents(
        self, registry: FailureRegistry,
    ) -> None:
        """error_msg y root_cause deben citar estrategia y agentes."""
        orch = _make_orchestrator(registry)
        orch.debate(
            task="Elegir framework para la API",
            agents=["builder", "scientist", "guardian"],
            strategy=DebateStrategy.CONSENSUS,
            max_rounds=1,
            dispatch_fn=_disagreeing_dispatch,
        )
        record = registry.get_recent(1)[0]
        for text in (record.error_msg, record.root_cause):
            assert DebateStrategy.CONSENSUS.value in text
            assert "builder" in text

    def test_task_reflects_debated_task(self, registry: FailureRegistry) -> None:
        """La tarea del fallo debe ser la tarea debatida."""
        orch = _make_orchestrator(registry)
        orch.debate(
            task="decidir motor de base de datos",
            agents=["builder", "scientist", "guardian"],
            strategy=DebateStrategy.CONSENSUS,
            max_rounds=1,
            dispatch_fn=_disagreeing_dispatch,
        )
        record = registry.get_recent(1)[0]
        assert "decidir motor de base de datos" in record.task


class TestDebateConsensusDoesNotRecord:
    """Con consenso el debate NO debe drenar nada."""

    def test_consensus_does_not_record(self, registry: FailureRegistry) -> None:
        """Un debate con acuerdo alto no deja registros."""
        orch = _make_orchestrator(registry)
        result = orch.debate(
            task="Elegir framework para la API",
            agents=["builder", "scientist", "guardian"],
            strategy=DebateStrategy.CONSENSUS,
            max_rounds=1,
            dispatch_fn=_agreeing_dispatch,
        )
        assert result.agent_agreement >= 0.5
        assert len(registry) == 0


class TestDebateDrainResilience:
    """El drain del debate no debe propagar fallos de persistencia."""

    def test_oserror_does_not_break_debate(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Un OSError del registry solo genera warning, no excepcion."""
        orch = DebateOrchestrator(
            vector_store=None, failure_registry=_ExplodingRegistry(),
        )
        with caplog.at_level(logging.WARNING, logger=DEBATE_LOGGER):
            result = orch.debate(
                task="Elegir framework para la API",
                agents=["builder", "scientist", "guardian"],
                strategy=DebateStrategy.CONSENSUS,
                max_rounds=1,
                dispatch_fn=_disagreeing_dispatch,
            )
        assert result.agent_agreement < 0.5
        assert "FailureRegistry" in caplog.text


class TestDebateDependencyInjection:
    """La inyeccion debe respetar el registry provisto y el default."""

    def test_injected_registry_is_used(self, registry: FailureRegistry) -> None:
        """El orquestador debe usar el registry inyectado, no el singleton."""
        orch = _make_orchestrator(registry)
        assert orch._failure_registry is registry

    def test_default_is_module_singleton(self) -> None:
        """Sin inyeccion, el default es el singleton del paquete."""
        from harness.failure_registry import registry as module_registry

        orch = DebateOrchestrator(vector_store=None)
        assert orch._failure_registry is module_registry
