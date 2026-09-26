"""Tests para coordinator_dispatch — dispatch obligatorio con guards (ADR-0100).

Frontera (RedHat/Camunda 2026): pasos deterministicos para lo reglado,
LLM solo donde hay interpretacion; schemas JSON enfocados; costos bajo
control (limitar input, constreñir output). El coordinador OBLIGA por
tarea: agente especializado + skills topadas por presupuesto + backend
local-first + contrato de salida.
"""

import pytest

from harness.orchestrator.coordinator_dispatch import (
    DispatchPlan,
    dispatch,
)


def test_closed_task_deterministic_no_llm() -> None:
    """Tarea cerrada => path deterministico (sin LLM), agente runner."""
    plan = dispatch("resume esto en 2 lineas")
    assert isinstance(plan, DispatchPlan)
    assert plan.deterministic is True
    assert plan.backend == "local"
    assert plan.cloud_tokens == 0


def test_open_task_specialized_agent() -> None:
    """Tarea abierta => agente especializado + skills topadas."""
    plan = dispatch("implementa endpoint con pytest")
    assert plan.deterministic is False
    assert plan.agent in ("builder", "guardian", "scientist", "coordinator")
    assert 1 <= len(plan.skills) <= 3
    assert plan.output_contract != ""


def test_skills_capped_by_budget() -> None:
    """El presupuesto topa skills (max_skills respeta)."""
    plan = dispatch("investiga papers y disena arquitectura", max_skills=1)
    assert len(plan.skills) <= 1


def test_frontier_task_goes_cloud_with_reason() -> None:
    """Frontier-only => cloud con motivo justificado."""
    plan = dispatch("disena la arquitectura hexagonal completa")
    assert plan.backend == "cloud"
    assert "frontier" in plan.reason.lower()


def test_empty_task_raises() -> None:
    """Tarea vacia falla accionable."""
    with pytest.raises(ValueError, match="WHAT"):
        dispatch("   ")


def test_plan_is_frozen() -> None:
    """DispatchPlan es inmutable."""
    plan = dispatch("resume esto")
    with pytest.raises(AttributeError):
        plan.agent = "x"  # type: ignore[misc]


def test_oracle_sampling_flag() -> None:
    """El plan marca si toca oraculo cloud (1%) segun sample."""
    plan = dispatch("resume esto", oracle_sample=True)
    assert plan.oracle is True
    plan2 = dispatch("resume esto", oracle_sample=False)
    assert plan2.oracle is False
