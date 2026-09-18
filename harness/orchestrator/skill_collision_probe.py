"""skill_collision_probe.py — Shadow test anti-colision de skills (ADR-0090).

WHAT: Ejecuta queries discriminantes contra un router y verifica que cada
una llega a su skill (casos de pares conocidos colisionados: quant x4,
psych x2, frontend x2).
WHY: SkillReducer (arXiv:2603.29919): solo skills cercanas confunden;
Single Rewrite: 1 reescritura basta para wording, scopes genuinos piden
arquitectura. El probe detecta la colision antes que el usuario.
WHERE: CI (regression de routing) y tras editar descriptions (gate).

Uso:
    report = probe_collisions(cases, router_fn)  # router_fn(query) -> skill
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger("harness.orchestrator.skill_collision_probe")


@dataclass(frozen=True)
class CollisionCase:
    """Caso discriminante: query que debe rutear a un skill exacto.

    Attributes:
        query: Pregunta discriminante (no vacia).
        expected_skill: Skill esperado (no vacio).

    Raises:
        ValueError: Si query o expected estan vacios.
    """

    query: str
    expected_skill: str

    def __post_init__(self) -> None:
        """Valida query y expected no vacios (WHAT+WHY+WHERE)."""
        if not self.query.strip() or not self.expected_skill.strip():
            raise ValueError(
                "WHAT: CollisionCase con query o expected vacio. "
                "WHY: sin ambos no hay discriminacion que probar. "
                "WHERE: CollisionCase.__post_init__"
            )


@dataclass(frozen=True)
class Misroute:
    """Un misroute detectado.

    Attributes:
        query: Query que fallo.
        expected: Skill esperado.
        got: Skill obtenido.
    """

    query: str
    expected: str
    got: str


@dataclass(frozen=True)
class ProbeReport:
    """Reporte del probe anti-colision.

    Attributes:
        passed: True si 0 misroutes.
        misrouted: Tupla de Misroute.
        total: Casos evaluados.
    """

    passed: bool
    misrouted: tuple[Misroute, ...]
    total: int


def probe_collisions(
    cases: list[CollisionCase], router_fn: Callable[[str], str]
) -> ProbeReport:
    """Ejecuta el shadow test sobre los casos.

    Args:
        cases: Casos discriminantes.
        router_fn: (query) -> skill ruteado.

    Returns:
        ProbeReport con misroutes (vacio = sin colision).
    """
    bad: list[Misroute] = []
    for case in cases:
        got = router_fn(case.query)
        if got != case.expected_skill:
            logger.warning(
                "skill_collision_probe: '%s' -> '%s' (esperado '%s')",
                case.query, got, case.expected_skill,
            )
            bad.append(Misroute(query=case.query, expected=case.expected_skill, got=got))
    return ProbeReport(passed=not bad, misrouted=tuple(bad), total=len(cases))
