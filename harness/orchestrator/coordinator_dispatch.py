"""coordinator_dispatch.py — Dispatch obligatorio del coordinador (ADR-0100).

WHAT: Por cada tarea produce un DispatchPlan inmutable: agente
especializado + skills (topadas por presupuesto) + backend (local-first,
cloud solo justificado) + path deterministico vs LLM + contrato JSON de
salida + flag de oraculo cloud (1%).
WHY: Frontera (RedHat/Camunda 2026): lo reglado va a pasos
deterministicos (0 tokens), el LLM solo donde hay interpretacion;
schemas enfocados; costos controlados (input limitado, output
constreñido). El coordinador no improvisa: resuelve y registra.
WHERE: Entrada del coordinator ante cada tarea (antes de delegar).

Uso:
    plan = dispatch("implementa endpoint con pytest")
    # plan.agent, plan.skills, plan.backend, plan.output_contract
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from harness.model_router.local_executor import is_closed_task
from harness.orchestrator.agent_selector import AgentSelector
from harness.orchestrator.skill_bundler import SkillBundler

logger = logging.getLogger("harness.orchestrator.coordinator_dispatch")

#: Skills maximas por defecto (presupuesto).
DEFAULT_MAX_SKILLS = 3
#: Dominios conocidos para mapeo rapido (keyword -> dominio).
_DOMAIN_KEYWORDS: dict[str, str] = {
    "endpoint": "web",
    "pytest": "web",
    "arquitectura": "architecture",
    "seguridad": "security",
    "paper": "research",
    "trading": "trading",
}


@dataclass(frozen=True)
class DispatchPlan:
    """Plan de despacho inmutable por tarea.

    Attributes:
        agent: Agente especializado asignado.
        skills: Skills cargadas (<= presupuesto).
        backend: "local" o "cloud".
        deterministic: True si va por path sin LLM.
        output_contract: Contrato JSON de salida (enfocado).
        oracle: True si toca muestreo del oraculo cloud (1%).
        cloud_tokens: Estimado (0 si deterministico/local).
        reason: Motivo legible.
    """

    agent: str
    skills: tuple[str, ...] = ()
    backend: str = "local"
    deterministic: bool = False
    output_contract: str = '{"result": "string"}'
    oracle: bool = False
    cloud_tokens: int = 0
    reason: str = ""


def _domain_for(task: str) -> str:
    """Mapea la tarea a un dominio del bundler (keyword rapido).

    Args:
        task: Descripcion en minusculas ya.

    Returns:
        Dominio o "general".
    """
    for keyword, domain in _DOMAIN_KEYWORDS.items():
        if keyword in task:
            return domain
    return "general"


def dispatch(
    task: str,
    max_skills: int = DEFAULT_MAX_SKILLS,
    oracle_sample: bool = False,
    selector: AgentSelector | None = None,
    bundler: SkillBundler | None = None,
) -> DispatchPlan:
    """Resuelve el despacho obligatorio de una tarea.

    Orden: vacia? -> cerrada (deterministico local)? -> agente + skills
    topadas + backend (frontier-only => cloud justificado).

    Args:
        task: Descripcion (no vacia).
        max_skills: Tope de skills (>= 1).
        oracle_sample: True si toco muestreo del oraculo 1%.
        selector: AgentSelector inyectable (tests).
        bundler: SkillBundler inyectable (tests).

    Returns:
        DispatchPlan frozen.

    Raises:
        ValueError: Si la tarea esta vacia o max_skills < 1.
    """
    if not task.strip():
        raise ValueError(
            "WHAT: tarea vacia. "
            "WHY: sin tarea no hay despacho. "
            "WHERE: dispatch"
        )
    if max_skills < 1:
        raise ValueError(
            f"WHAT: max_skills invalido: {max_skills}. "
            "WHY: se necesita al menos 1 skill. "
            "WHERE: dispatch"
        )
    lowered = task.strip().lower()
    active_selector = selector or AgentSelector()
    active_bundler = bundler or SkillBundler()
    if is_closed_task(task):
        agents = active_selector.select(task, skill="general")
        agent = agents[0] if agents else "coordinator"
        logger.info("dispatch: tarea cerrada -> deterministico (%s)", agent)
        return DispatchPlan(
            agent=agent, skills=(),
            backend="local", deterministic=True,
            output_contract='{"result": "string"}',
            oracle=oracle_sample, cloud_tokens=0,
            reason="tarea cerrada: path deterministico sin LLM",
        )
    agents = active_selector.select(task, skill="general")
    agent = agents[0] if agents else "coordinator"
    domain = _domain_for(lowered)
    skills = tuple(active_bundler.select_skills(domain, task)[:max_skills])
    if not skills:
        skills = ("general",)
    backend = "local"
    reason = f"agente {agent} + {len(skills)} skills (local-first)"
    if _is_frontier_task(lowered):
        backend = "cloud"
        reason = "tarea frontier-only: cloud justificado (TKN)"
    logger.info("dispatch: %s -> %s/%s", task[:60], agent, backend)
    return DispatchPlan(
        agent=agent, skills=skills, backend=backend,
        deterministic=False,
        output_contract='{"result": "string", "evidence": ["string"]}',
        oracle=oracle_sample, cloud_tokens=0 if backend == "local" else -1,
        reason=reason,
    )


def _is_frontier_task(lowered: str) -> bool:
    """True si la tarea requiere frontier (diseno/arquitectura profunda).

    Args:
        lowered: Tarea en minusculas.

    Returns:
        True para diseno/arquitectura completa.
    """
    markers = ("arquitectura hexagonal completa", "disena la arquitectura")
    return any(m in lowered for m in markers)
