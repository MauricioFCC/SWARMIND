"""Tests para competence_model — Beta posterior por agente x skill (ADR-0075).

Frontera (SkillOrchestra, Wang 2026): posterior Beta(alpha, beta) por par
(agente, skill) actualizado con execution traces; seleccion con Thompson
sampling o utilidad max(competencia - lambda*costo); evita routing collapse
(uno-solo-gana-todo) y transfiere el handbook entre agentes/modelos.
"""

import pytest

from harness.orchestrator.competence_model import (
    CompetenceModel,
)


def test_select_new_pair_explores() -> None:
    """Pares sin datos se seleccionan (exploracion Thompson)."""
    model = CompetenceModel(agents=("builder", "guardian"), skills=("tdd", "pec"))
    pick = model.select(skill="tdd")
    assert pick in ("builder", "guardian")


def test_update_and_exploit_best() -> None:
    """Con evidencia fuerte, el modelo explota el par ganador."""
    model = CompetenceModel(agents=("a", "b"), skills=("s",))
    for _ in range(12):
        model.update("a", "s", success=True)
    for _ in range(12):
        model.update("b", "s", success=False)
    picks = {model.select(skill="s") for _ in range(20)}
    assert picks == {"a"}


def test_no_routing_collapse() -> None:
    """El modelo sigue explorando el agente debil (no colapso total).

    Desbalance moderado (5 vs 1): Thompson explora al perdedor con
    probabilidad ~2-5%, suficiente para aparecer en 200 picks.
    """
    model = CompetenceModel(agents=("a", "b"), skills=("s",))
    for _ in range(5):
        model.update("a", "s", success=True)
    for _ in range(1):
        model.update("b", "s", success=False)
    picks = {model.select(skill="s") for _ in range(200)}
    assert picks == {"a", "b"}  # Thompson mantiene exploracion eps


def test_cost_penalty_shifts_selection() -> None:
    """Con penalizacion de costo alta, el par caro pierde en empate."""
    model = CompetenceModel(agents=("cheap", "pricey"), skills=("s",))
    for _ in range(10):
        model.update("cheap", "s", success=True)
        model.update("pricey", "s", success=True)
    pick = model.select(skill="s", cost_weight=10.0, costs={"cheap": 0.1, "pricey": 5.0})
    assert pick == "cheap"


def test_mean_competence_and_counts() -> None:
    """La media posterior y los conteos reflejan los updates."""
    model = CompetenceModel(agents=("a",), skills=("s",))
    for _ in range(8):
        model.update("a", "s", success=True)
    for _ in range(2):
        model.update("a", "s", success=False)
    posterior = model.posterior("a", "s")
    # 8 datos + 1 prior alpha = 9; 2 datos + 1 prior beta = 3
    assert posterior.successes == 9
    assert posterior.failures == 3
    assert 0.6 <= posterior.mean <= 0.85


def test_invalid_pair_raises() -> None:
    """Update/select sobre pares desconocidos falla accionable."""
    model = CompetenceModel(agents=("a",), skills=("s",))
    with pytest.raises(ValueError, match="WHAT"):
        model.update("a", "otra", success=True)
    with pytest.raises(ValueError, match="WHAT"):
        model.select(skill="otra")


def test_imp_at_k_metric() -> None:
    """imp@k = delta de metrica entre snapshots / k experimentos (HyperAgents)."""
    model = CompetenceModel(agents=("a",), skills=("s",), snapshot_every=2)
    for _ in range(4):
        model.update("a", "s", success=True)  # snapshots en update 2 y 4
    imp = model.imp_at_k(metric_fn=lambda m: m.posterior("a", "s").mean, k=2)
    assert imp > 0.0
