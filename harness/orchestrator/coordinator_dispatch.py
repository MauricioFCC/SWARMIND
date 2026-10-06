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
import random
import zlib
from dataclasses import dataclass
from functools import lru_cache

from harness.model_router.local_executor import is_closed_task
from harness.orchestrator import feature_flags
from harness.orchestrator.agent_selector import AgentSelector
from harness.orchestrator.routing_mutation import (
    TOPOLOGY_SEQUENTIAL,
    RoutingGenome,
    SafetyAllowlist,
    build_semantic_neighbors,
    default_allowlist,
    is_safe,
    mutate,
)
from harness.orchestrator.skill_bundler import SkillBundler

logger = logging.getLogger("harness.orchestrator.coordinator_dispatch")

#: Skills maximas por defecto (presupuesto).
DEFAULT_MAX_SKILLS = 3

#: Feature flag del routing mutado (QD). Off por defecto (trunk-based, ADR-0083).
_MUTATION_FLAG = "routing-mutation"

#: Intentos de mutacion segura antes de conservar el champion.
MUTATION_ATTEMPTS = 4

#: Defaults del genoma baseline (champion).
DEFAULT_TEMPERATURE = 0.2
DEFAULT_PERSONA = "pragmatic_engineer"
DEFAULT_BUDGET_TOKENS = 8192
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
        mutated: True si el routing fue mutado por Quality-Diversity.
        mutation: Detalle legible de la mutacion aplicada.
    """

    agent: str
    skills: tuple[str, ...] = ()
    backend: str = "local"
    deterministic: bool = False
    output_contract: str = '{"result": "string"}'
    oracle: bool = False
    cloud_tokens: int = 0
    reason: str = ""
    mutated: bool = False
    mutation: str = ""


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


@lru_cache(maxsize=1)
def _routing_registry() -> tuple[SafetyAllowlist, dict[str, tuple[str, ...]]]:
    """Allowlist y vecinos semanticos cacheados (una carga por proceso).

    Returns:
        `(allowlist, neighbors)` reutilizados por cada mutacion.
    """
    return default_allowlist(), build_semantic_neighbors()


def _seed_for(task: str) -> int:
    """Seed determinista derivado de la tarea (reproducible entre corridas).

    Args:
        task: Descripcion de la tarea.

    Returns:
        Entero de 32 bits estable (crc32), no el `hash()` aleatorizado.
    """
    return zlib.crc32(task.strip().lower().encode("utf-8"))


def _baseline_genome(agent: str, skills: tuple[str, ...]) -> RoutingGenome:
    """Construye el genoma baseline (champion) del plan determinista.

    Args:
        agent: Agente elegido por el selector.
        skills: Skills elegidas por el bundler.

    Returns:
        Genoma secuencial con los defaults de la flota.
    """
    return RoutingGenome(
        skills=skills,
        agents=(agent,) * len(skills),
        temperature=DEFAULT_TEMPERATURE,
        persona=DEFAULT_PERSONA,
        topology=TOPOLOGY_SEQUENTIAL,
        budget_tokens=DEFAULT_BUDGET_TOKENS,
    )


def _mutate_routing(
    agent: str, skills: tuple[str, ...], task: str
) -> RoutingGenome | None:
    """Propone una variante de routing mutada y SEGURA (feature-flagged).

    WHAT: muta el genoma baseline y valida contra la allowlist.
    WHY: explorar vecinos puede descubrir variantes mejores, pero solo si el
    gate de seguridad pasa; sin flag, se conserva el champion (trunk-based).
    WHERE: `dispatch` antes de emitir el DispatchPlan.

    Args:
        agent: Agente baseline.
        skills: Skills baseline.
        task: Tarea (para el seed determinista).

    Returns:
        Genoma mutado seguro, o None si el flag esta off o nada es seguro.
    """
    if not feature_flags.is_enabled(_MUTATION_FLAG):
        return None
    allowlist, neighbors = _routing_registry()
    genome = _baseline_genome(agent, skills)
    rng = random.Random(_seed_for(task))
    for _ in range(MUTATION_ATTEMPTS):
        candidate = mutate(genome, neighbors=neighbors, rng=rng)
        if is_safe(candidate, allowlist=allowlist)[0]:
            return candidate
    logger.warning("dispatch: sin variante segura tras %d intentos", MUTATION_ATTEMPTS)
    return None


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
    mutant = _mutate_routing(agent, skills, task)
    mutation = ""
    if mutant is not None:
        agent = mutant.agents[0] if mutant.agents else agent
        skills = tuple(mutant.skills) or skills
        mutation = (
            f"routing mutado (QD): persona={mutant.persona}, "
            f"topo={mutant.topology}, temp={mutant.temperature}"
        )
    backend = "local"
    reason = f"agente {agent} + {len(skills)} skills (local-first)"
    if _is_frontier_task(lowered):
        backend = "cloud"
        reason = "tarea frontier-only: cloud justificado (TKN)"
    if mutation:
        reason = f"{reason}; {mutation}"
    logger.info("dispatch: %s -> %s/%s", task[:60], agent, backend)
    return DispatchPlan(
        agent=agent, skills=skills, backend=backend,
        deterministic=False,
        output_contract='{"result": "string", "evidence": ["string"]}',
        oracle=oracle_sample, cloud_tokens=0 if backend == "local" else -1,
        reason=reason, mutated=mutant is not None, mutation=mutation,
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
