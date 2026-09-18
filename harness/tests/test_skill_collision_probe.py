"""Tests para skill_collision_probe — adversarial delta debugging (ADR-0090).

SkillReducer (arXiv:2603.29919): solo skills semanticamente cercanas
confunden al router; Single Rewrite: colisiones por wording se arreglan
con 1 reescritura, scopes genuinos requieren intervencion arquitectonica.
El probe verifica con queries discriminantes que pares conocidos
colisionados rutean al skill correcto (shadow test).
"""

import pytest

from harness.orchestrator.skill_collision_probe import (
    CollisionCase,
    probe_collisions,
)


def _router_fn_factory(mapping: dict[str, str]):
    """Router fake query -> skill."""

    def _fn(query: str) -> str:
        return mapping.get(query, "unknown")

    return _fn


def test_quant_cluster_routes_correctly() -> None:
    """quant x4: cada query va a su skill (Alcance: desambiguacion)."""
    cases = [
        CollisionCase("validar factor momentum con walk-forward", "alpha-research"),
        CollisionCase("implementar motor CQE de baja latencia", "quant-trading"),
        CollisionCase("position sizing para la cuenta", "risk-execution"),
        CollisionCase("asignar capital del fondo por mandato", "hedgefund"),
    ]
    mapping = {c.query: c.expected_skill for c in cases}
    report = probe_collisions(cases, _router_fn_factory(mapping))
    assert report.passed is True
    assert report.misrouted == ()


def test_misroute_detected() -> None:
    """Un misroute se reporta con query/esperado/obtenido."""
    cases = [CollisionCase("validar factor", "alpha-research")]
    report = probe_collisions(cases, _router_fn_factory({"validar factor": "quant-trading"}))
    assert report.passed is False
    assert len(report.misrouted) == 1
    assert report.misrouted[0].expected == "alpha-research"


def test_psych_pair_routes_correctly() -> None:
    """psychology vs behavioral-economics por ambito."""
    cases = [
        CollisionCase("dinamica de equipo y aprendizaje", "psychology"),
        CollisionCase("nudges e incentivos economicos", "behavioral-economics"),
    ]
    mapping = {c.query: c.expected_skill for c in cases}
    report = probe_collisions(cases, _router_fn_factory(mapping))
    assert report.passed is True


def test_empty_cases_passes_vacuous() -> None:
    """Sin casos: pass vacuo documentado."""
    report = probe_collisions([], lambda q: "x")
    assert report.passed is True
    assert report.total == 0


def test_case_requires_expected() -> None:
    """CollisionCase sin expected falla accionable."""
    with pytest.raises(ValueError, match="WHAT"):
        CollisionCase("q", "")
