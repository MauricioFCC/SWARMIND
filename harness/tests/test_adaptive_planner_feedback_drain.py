"""Tests del drenaje de feedback del AdaptivePlanner al FailureRegistry.

Cubre el cableado FR (failure distillation, arXiv 2607.29468 SESA): cuando
el ``success_rate`` de un ``PlanFeedback`` cae por debajo de
``REPLAN_FAILURE_RATE``, el planner debe persistir un ``FailureRecord`` en
el ``FailureRegistry`` para su destilacion posterior en skills.

Casos:
  (a) success_rate bajo -> registra 1 fallo con los campos esperados;
  (b) success_rate alto (>= umbral) -> NO registra;
  (c) registry inyectado que lanza OSError -> el planner NO lanza (warning);
  (d) inyeccion por DI (registry aislado) no toca el singleton real.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from harness.failure_registry import FailureRegistry, FailureType, Severity
from harness.orchestrator.adaptive_planner import (
    REPLAN_FAILURE_RATE,
    AdaptivePlanner,
    PlanFeedback,
    PlanStrategy,
)

LOGGER_NAME = "harness.orchestrator.adaptive_planner.core"

# ---------------------------------------------------------------------------
# Fixtures y helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def registry(tmp_path: Path) -> FailureRegistry:
    """FailureRegistry aislado en directorio temporal (no toca el real)."""
    return FailureRegistry(path=tmp_path / "failures.jsonl")


def _make_feedback(
    success_rate: float,
    task_type: str = "deploy",
    strategy: PlanStrategy = PlanStrategy.SEQUENTIAL,
    session_id: str = "sess_drain",
) -> PlanFeedback:
    """Construye un PlanFeedback con el success_rate indicado."""
    subtask_count = 4
    success_count = round(success_rate * subtask_count)
    return PlanFeedback(
        session_id=session_id,
        task_hash="hash_drain",
        task_type=task_type,
        strategy_used=strategy,
        subtask_count=subtask_count,
        level_count=2,
        success_count=success_count,
        failure_count=subtask_count - success_count,
        total_duration_ms=3000.0,
        success_rate=success_rate,
    )


class _ExplodingRegistry:
    """Registry fake que siempre falla al persistir (simula OSError)."""

    def record(self, **kwargs: object) -> None:
        """Simula un fallo de persistencia del registry real."""
        raise OSError("disco lleno (simulado)")


# ---------------------------------------------------------------------------
# (a) success_rate bajo -> registra fallo
# ---------------------------------------------------------------------------


class TestLowSuccessRateRecordsFailure:
    """Con success_rate < umbral debe persistir un FailureRecord."""

    def test_records_single_failure(self, registry: FailureRegistry) -> None:
        """Un feedback bajo debe dejar exactamente 1 registro."""
        planner = AdaptivePlanner(failure_registry=registry)
        planner.record_feedback(_make_feedback(0.2))
        assert len(registry) == 1

    def test_failure_type_and_severity(self, registry: FailureRegistry) -> None:
        """El fallo debe ser RUNTIME con severidad HIGH y resolution pending."""
        planner = AdaptivePlanner(failure_registry=registry)
        planner.record_feedback(_make_feedback(0.2))
        record = registry.get_recent(1)[0]
        assert record.failure_type is FailureType.RUNTIME
        assert record.severity is Severity.HIGH
        assert record.resolution == "pending"
        assert record.skill_derived == ""

    def test_error_and_root_cause_carry_rate_and_strategy(
        self, registry: FailureRegistry,
    ) -> None:
        """error_msg y root_cause deben citar success_rate y estrategia."""
        planner = AdaptivePlanner(failure_registry=registry)
        planner.record_feedback(_make_feedback(0.2))
        record = registry.get_recent(1)[0]
        for text in (record.error_msg, record.root_cause):
            assert "0.20" in text or "0.2" in text
            assert "sequential" in text

    def test_task_describes_task_type(self, registry: FailureRegistry) -> None:
        """La tarea del fallo debe mencionar el task_type."""
        planner = AdaptivePlanner(failure_registry=registry)
        planner.record_feedback(_make_feedback(0.3, task_type="research"))
        record = registry.get_recent(1)[0]
        assert "research" in record.task

    def test_tags_carry_task_type_and_strategy(
        self, registry: FailureRegistry,
    ) -> None:
        """Los tags deben incluir task_type y estrategia usada."""
        planner = AdaptivePlanner(failure_registry=registry)
        planner.record_feedback(_make_feedback(0.2, task_type="implement"))
        record = registry.get_recent(1)[0]
        assert "implement" in record.tags
        assert "sequential" in record.tags

    def test_multiple_low_feedback_records_multiple(
        self, registry: FailureRegistry,
    ) -> None:
        """Cada feedback bajo debe generar su propio registro (append-only)."""
        planner = AdaptivePlanner(failure_registry=registry)
        planner.record_feedback(_make_feedback(0.1, session_id="a"))
        planner.record_feedback(_make_feedback(0.2, session_id="b"))
        assert len(registry) == 2
        assert len(registry.get_unresolved()) == 2


# ---------------------------------------------------------------------------
# (b) success_rate alto -> NO registra
# ---------------------------------------------------------------------------


class TestHighSuccessRateDoesNotRecord:
    """Con success_rate >= umbral no debe persistir fallo alguno."""

    def test_high_rate_does_not_record(self, registry: FailureRegistry) -> None:
        """Un feedback exitoso no debe crear registros."""
        planner = AdaptivePlanner(failure_registry=registry)
        planner.record_feedback(_make_feedback(0.8))
        assert len(registry) == 0

    def test_equal_to_threshold_does_not_record(
        self, registry: FailureRegistry,
    ) -> None:
        """En el umbral exacto (no estrictamente menor) no registra."""
        planner = AdaptivePlanner(failure_registry=registry)
        planner.record_feedback(_make_feedback(REPLAN_FAILURE_RATE))
        assert len(registry) == 0


# ---------------------------------------------------------------------------
# (c) registry que lanza OSError -> no rompe el planner
# ---------------------------------------------------------------------------


class TestDrainResilience:
    """El drain no debe propagar fallos de persistencia del registry."""

    def test_oserror_does_not_break_planner(self, caplog: pytest.LogCaptureFixture) -> None:
        """Un OSError del registry solo genera warning, no excepcion."""
        planner = AdaptivePlanner(failure_registry=_ExplodingRegistry())
        with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
            planner.record_feedback(_make_feedback(0.1))
        assert "FailureRegistry" in caplog.text

    def test_feedback_still_registered_in_planner(self) -> None:
        """Aunque el drain falle, el planner conserva el feedback."""
        planner = AdaptivePlanner(failure_registry=_ExplodingRegistry())
        planner.record_feedback(_make_feedback(0.1))
        assert planner._strategy_stats["sequential"].total_uses == 1
        assert len(planner._feedback_history) == 1


# ---------------------------------------------------------------------------
# (d) DI: registry inyectado vs singleton real
# ---------------------------------------------------------------------------


class TestDependencyInjection:
    """La inyeccion debe respetar el registry provisto y el default."""

    def test_injected_registry_is_used(self, registry: FailureRegistry) -> None:
        """El planner debe usar el registry inyectado, no el singleton."""
        planner = AdaptivePlanner(failure_registry=registry)
        assert planner._failure_registry is registry

    def test_default_is_module_singleton(self) -> None:
        """Sin inyeccion, el default es el singleton del paquete."""
        from harness.failure_registry import registry as module_registry

        planner = AdaptivePlanner()
        assert planner._failure_registry is module_registry

    def test_injected_empty_registry_is_not_replaced(self, registry: FailureRegistry) -> None:
        """Un registry vacio (falsy por __len__) NO debe ser reemplazado."""
        assert len(registry) == 0
        planner = AdaptivePlanner(failure_registry=registry)
        planner.record_feedback(_make_feedback(0.2))
        assert len(registry) == 1
