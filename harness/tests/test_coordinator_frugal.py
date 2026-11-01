"""Integration del routing frugal en `dispatch` (spec N9 + AC del ciclo).

Adversarial: tarea small -> plan.model = beam-free; tarea frontier -> model
unset; env off -> unset; determinismo e inmutabilidad del plan.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from harness.model_router.edit_constants import DEFAULT_EDITS_MODEL
from harness.orchestrator.coordinator_dispatch import (
    FRUGAL_MODEL_UNSET,
    dispatch,
)


class TestFrugalDispatch:
    """El plan solo lleva modelo frugal cuando la tarea es `small`."""

    def test_small_task_gets_free_model(self, monkeypatch):
        """Una tarea de bajo esfuerzo (sin razonamiento) va con beam-free."""
        monkeypatch.delenv("SWARMIND_EDITS_MODEL", raising=False)
        plan = dispatch("arregla el typo de la variable x")
        assert plan.model == DEFAULT_EDITS_MODEL
        assert "modelo frugal" in plan.reason

    def test_frontier_task_keeps_model_unset(self):
        """Tarea profunda: plan.model queda como unset (sin frugal)."""
        plan = dispatch(
            "implementa una arquitectura compleja de patrones de diseno, "
            "investiga papers, hypothesis de machine learning y algoritmos "
            "para un sistema multientrenamiento con analisis"
        )
        assert plan.model == FRUGAL_MODEL_UNSET

    def test_env_off_removes_model_from_plan(self, monkeypatch):
        """`SWARMIND_FRUGAL_ROUTING=0` apaga el tier para toda tarea."""
        monkeypatch.setenv("SWARMIND_FRUGAL_ROUTING", "0")
        plan = dispatch("arregla el typo de la variable x")
        assert plan.model == FRUGAL_MODEL_UNSET

    def test_env_override_pins_plan_model(self, monkeypatch):
        """Env override del id frugal llega al plan (N5)."""
        monkeypatch.setenv("SWARMIND_EDITS_MODEL", "opencode/beam-free")
        monkeypatch.delenv("SWARMIND_FRUGAL_ROUTING", raising=False)
        plan = dispatch("arregla el typo de la variable x")
        assert plan.model == "opencode/beam-free"

    def test_plan_is_frozen(self, monkeypatch):
        """El plan de despacho es inmutable (no se parchea a postiori)."""
        monkeypatch.delenv("SWARMIND_EDITS_MODEL", raising=False)
        plan = dispatch("arregla el typo de la variable x")
        with pytest.raises(FrozenInstanceError):
            plan.model = "x"  # type: ignore[misc]

    def test_determinism(self):
        """Misma tarea => mismo plan (incluido el modelo frugal)."""
        first = dispatch("arregla el typo de la variable x")
        second = dispatch("arregla el typo de la variable x")
        assert first == second

    def test_closed_task_has_no_model(self):
        """Tareas cerradas (deterministic, sin LLM) no usan modelo frugal."""
        plan = dispatch("resume esto en 2 lineas")
        assert plan.deterministic is True
        assert plan.model == FRUGAL_MODEL_UNSET
