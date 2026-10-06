"""Tests de la mutacion de routing en el dispatch del coordinador (FND/EVO).

Verifican que el routing mutado (Quality-Diversity) es opt-in por feature flag,
seguro y determinista; y que sin flag se conserva el champion.
"""

from __future__ import annotations

from harness.orchestrator.coordinator_dispatch import dispatch

_TASK = "refactoriza la capa de persistencia con tests"


def _enable_mutation(monkeypatch) -> None:
    """Activa el flag de mutacion de routing en el entorno.

    Args:
        monkeypatch: Fixture de pytest para el entorno.
    """
    monkeypatch.setenv("SWARMIND_FF_ROUTING_MUTATION", "1")


def test_dispatch_sin_flag_conserva_champion(monkeypatch) -> None:
    """Sin flag, el dispatch NO muta el routing (default seguro)."""
    monkeypatch.delenv("SWARMIND_FF_ROUTING_MUTATION", raising=False)
    plan = dispatch(_TASK)
    assert plan.mutated is False
    assert plan.mutation == ""


def test_dispatch_con_flag_muta_routing_seguro(monkeypatch) -> None:
    """Con flag, muta el routing y conserva agente/skills validos."""
    _enable_mutation(monkeypatch)
    plan = dispatch(_TASK)
    assert plan.mutated is True
    assert plan.agent
    assert len(plan.skills) >= 1
    assert "routing mutado" in plan.mutation


def test_dispatch_mutacion_es_determinista(monkeypatch) -> None:
    """La misma tarea produce la misma variante (seed crc32 estable)."""
    _enable_mutation(monkeypatch)
    first = dispatch(_TASK)
    second = dispatch(_TASK)
    assert (first.agent, first.skills) == (second.agent, second.skills)


def test_dispatch_flag_off_no_muta(monkeypatch) -> None:
    """Flag ausente -> champion (no mutado) aunque la tarea no sea cerrada."""
    monkeypatch.delenv("SWARMIND_FF_ROUTING_MUTATION", raising=False)
    plan = dispatch("implementa un parser de consultas con pruebas")
    assert plan.mutated is False
