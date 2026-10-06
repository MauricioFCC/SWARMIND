"""routing_mutation.py — Mutacion sana de routing con Quality-Diversity (QD).

WHAT: Genoma de routing (skills, agentes, temperatura, persona, topologia,
presupuesto), descriptor de comportamiento discretizado, archivo QD
MAP-Elites/CVT que conserva la mejor variante por nicho, novedad por distancia
semantica, mutacion de 1-2 genes hacia vecinos semanticos, gate de seguridad
(allowlist + reversibilidad) y fitness compuesto calidad - coste - latencia +
novedad.
WHY: Frontera 2026 — los MAS sufren Diversity Collapse (ACL Findings 2026);
explorar vecinos del routing descubre variantes nuevas sin caer por debajo del
baseline (Mouret & Clune 2015; Lehman & Stanley 2011; Heuresis 2026).
WHERE: Delante de ``agent_selector``/``skill_bundler``; produce variantes
candidatas a canary/shadow con rollback (SBX/GATE/ADV).

Uso:
    allow = default_allowlist()
    archive = QDArchive()
    ctx = EvaluationContext(
        allowlist=allow, cost_bucket=cost_bucket_for(4000),
        depth_bucket=depth_bucket_for("sequential"), baseline_fitness=0.5,
    )
    mutant = mutate(genome, neighbors=build_semantic_neighbors(), rng=random.Random(7))
    decision = evaluate_and_archive(mutant, archive, quality=0.8, cost=0.1,
                                    latency=0.2, context=ctx)
"""

from __future__ import annotations

import logging
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

from harness.orchestrator.agent_selector import AGENT_KEYWORDS
from harness.orchestrator.skill_bundler import DOMAIN_SKILLS, SKILL_TO_AGENT

logger = logging.getLogger("harness.orchestrator.routing_mutation")

# --- Topologias (eje del descriptor) ---------------------------------------
TOPOLOGY_SEQUENTIAL = "sequential"
TOPOLOGY_FANOUT = "fanout"
TOPOLOGY_DEBATE = "debate"
TOPOLOGIES: tuple[str, ...] = (TOPOLOGY_SEQUENTIAL, TOPOLOGY_FANOUT, TOPOLOGY_DEBATE)

# --- Buckets de coste y profundidad (ejes del descriptor) ------------------
COST_LOW = "low"
COST_MID = "mid"
COST_HIGH = "high"
COST_BUCKETS: tuple[str, ...] = (COST_LOW, COST_MID, COST_HIGH)

DEPTH_SHALLOW = "shallow"
DEPTH_DEEP = "deep"
DEPTH_BUCKETS: tuple[str, ...] = (DEPTH_SHALLOW, DEPTH_DEEP)

FAMILY_GENERAL = "general"

#: Umbrales de presupuesto (tokens) para el bucket de coste.
COST_LOW_MAX_TOKENS = 8_000
COST_MID_MAX_TOKENS = 32_000

#: Profundidad de razonamiento inducida por topologia.
TOPOLOGY_DEPTH: dict[str, str] = {
    TOPOLOGY_SEQUENTIAL: DEPTH_SHALLOW,
    TOPOLOGY_FANOUT: DEPTH_SHALLOW,
    TOPOLOGY_DEBATE: DEPTH_DEEP,
}

# --- Temperatura / presupuesto / personas ----------------------------------
TEMPERATURE_MIN = 0.0
TEMPERATURE_MAX = 2.0
TEMPERATURE_SPAN = TEMPERATURE_MAX - TEMPERATURE_MIN
TEMPERATURE_JITTER_STEPS: tuple[float, ...] = (-0.2, -0.1, 0.1, 0.2)

PERSONA_POOL: tuple[str, ...] = (
    "pragmatic_engineer",
    "rigorous_scientist",
    "adversarial_reviewer",
    "creative_explorer",
    "risk_averse_guardian",
    "efficiency_optimizer",
)

BUDGET_MIN_TOKENS = 1
BUDGET_MAX_TOKENS = 200_000
BUDGET_JITTER_FACTOR = 0.25

# --- Mutacion ---------------------------------------------------------------
#: Genes mutados por generacion: siempre >= 1, a veces 2 (rate configurable).
GENES_MIN_PER_MUTATION = 1
GENES_MAX_PER_MUTATION = 2
EXTRA_GENE_MUTATION_RATE = 0.35
REORDER_PROBABILITY = 0.25
_GENE_KINDS: tuple[str, ...] = (
    "skills",
    "agents",
    "temperature",
    "persona",
    "topology",
    "budget_tokens",
)

# --- Fitness compuesto ------------------------------------------------------
DEFAULT_LAMBDA_COST = 0.5
DEFAULT_MU_LATENCY = 0.1
DEFAULT_NU_NOVELTY = 0.3

# --- Distancia semantica (Jaccard + estructura) ----------------------------
DISTANCE_WEIGHT_SKILLS = 0.35
DISTANCE_WEIGHT_AGENTS = 0.35
DISTANCE_WEIGHT_TEMPERATURE = 0.10
DISTANCE_WEIGHT_PERSONA = 0.10
DISTANCE_WEIGHT_TOPOLOGY = 0.10

#: Marcadores de acciones irreversibles o exposicion de secretos (SEG/SBX).
FORBIDDEN_MARKERS: tuple[str, ...] = (
    "rm -rf",
    "drop table",
    "truncate table",
    "delete_all",
    "force push",
    "force-push",
    "--no-verify",
    "secret",
    "api_key",
    "apikey",
    "password",
    "private_key",
    "credential",
    "exfiltrat",
    "disable_safety",
    "disable-safety",
)

SAFE_REASON = "OK: genoma seguro (allowlist + reversible, sin secretos)"
EQUIVALENT_REASON = (
    "DESCARTADA: variante equivalente; no mejora el baseline, no cubre un "
    "nicho nuevo ni expone un fallo (analogia mutation testing)."
)
ARCHIVED_REASON = "ARCHIVADA: variante sana (nueva, mejor o senal de fallo)."

_AGENTS_DIR = Path(__file__).resolve().parents[2] / ".opencode" / "agents"


def _build_skill_domains() -> dict[str, str]:
    """Invierte ``DOMAIN_SKILLS`` a skill -> dominio (familia dominante).

    Returns:
        Mapa skill -> primer dominio que la contiene (determinista).
    """
    mapping: dict[str, str] = {}
    for domain, skills in DOMAIN_SKILLS.items():
        for skill in skills:
            mapping.setdefault(skill, domain)
    return mapping


_SKILL_DOMAIN: dict[str, str] = _build_skill_domains()


@dataclass(frozen=True)
class RoutingGenome:
    """Genoma de routing inmutable (genes mutables por ``mutate``).

    Attributes:
        skills: Skill por paso del plan.
        agents: Agente por paso (paralelo a ``skills``).
        temperature: Creatividad del modelo (``TEMPERATURE_MIN..MAX``).
        persona: Anclaje anti-hivemind.
        topology: ``sequential``, ``fanout`` o ``debate``.
        budget_tokens: Presupuesto de tokens (> 0).
    """

    skills: tuple[str, ...]
    agents: tuple[str, ...]
    temperature: float
    persona: str
    topology: str
    budget_tokens: int

    def __post_init__(self) -> None:
        """Valida invariantes del genoma (WHAT+WHY+WHERE si fallan)."""
        if self.topology not in TOPOLOGIES:
            raise ValueError(
                f"WHAT: topologia invalida {self.topology!r}. "
                f"WHY: solo se admiten {list(TOPOLOGIES)}. "
                "WHERE: RoutingGenome.__post_init__"
            )
        if not TEMPERATURE_MIN <= self.temperature <= TEMPERATURE_MAX:
            raise ValueError(
                f"WHAT: temperature fuera de rango {self.temperature!r}. "
                f"WHY: rango valido [{TEMPERATURE_MIN}, {TEMPERATURE_MAX}]. "
                "WHERE: RoutingGenome.__post_init__"
            )
        if self.budget_tokens <= 0:
            raise ValueError(
                f"WHAT: budget_tokens no positivo {self.budget_tokens!r}. "
                "WHY: el presupuesto debe ser > 0 para acotar el coste. "
                "WHERE: RoutingGenome.__post_init__"
            )


@dataclass(frozen=True)
class ScoredGenome:
    """Genoma evaluado y ubicado en un nicho del archivo QD.

    Attributes:
        genome: Genoma evaluado.
        fitness: Fitness compuesto (calidad - coste - latencia + novedad).
        descriptor: Clave de nicho (ejes discretizados).
        novelty: Distancia semantica media al resto del archivo.
    """

    genome: RoutingGenome
    fitness: float
    descriptor: str
    novelty: float


@dataclass(frozen=True)
class ArchiveDecision:
    """Resultado de evaluar una variante contra el archivo QD.

    Attributes:
        accepted: True si la variante se archivo.
        reason: Motivo legible (que se hizo y por que).
        scored: Variante puntuada (None si la rechazo el gate de seguridad).
    """

    accepted: bool
    reason: str
    scored: ScoredGenome | None


@dataclass(frozen=True)
class SafetyAllowlist:
    """Allowlist de seguridad para variantes de routing (SEG/SBX).

    Attributes:
        skills: Skills permitidas.
        agents: Agentes permitidos.
        forbidden_markers: Tokens de acciones irreversibles/secretos.
    """

    skills: frozenset[str]
    agents: frozenset[str]
    forbidden_markers: frozenset[str] = field(
        default_factory=lambda: frozenset(FORBIDDEN_MARKERS)
    )


@dataclass(frozen=True)
class EvaluationContext:
    """Parametros de evaluacion de una variante (SDD: input explicito).

    Attributes:
        allowlist: Gate de seguridad (skills/agentes/marcadores).
        cost_bucket: Bucket de coste del nicho.
        depth_bucket: Bucket de profundidad del nicho.
        baseline_fitness: Fitness del champion actual.
        baseline_failures: Fallos conocidos del baseline.
        observed_failures: Fallos observados en la variante (senal).
        lambda_cost: Peso de la penalizacion de coste.
        mu_latency: Peso de la penalizacion de latencia.
        nu_novelty: Peso del bonus de novedad.
    """

    allowlist: SafetyAllowlist
    cost_bucket: str
    depth_bucket: str
    baseline_fitness: float
    baseline_failures: tuple[str, ...] = ()
    observed_failures: tuple[str, ...] = ()
    lambda_cost: float = DEFAULT_LAMBDA_COST
    mu_latency: float = DEFAULT_MU_LATENCY
    nu_novelty: float = DEFAULT_NU_NOVELTY


def _jaccard(left: Sequence[str], right: Sequence[str]) -> float:
    """Similitud de Jaccard entre dos secuencias (0.0 = disjuntas).

    Args:
        left: Primera secuencia.
        right: Segunda secuencia.

    Returns:
        Interseccion / union; 1.0 si ambas estan vacias (identicas).
    """
    set_left, set_right = set(left), set(right)
    union = set_left | set_right
    if not union:
        return 1.0
    return len(set_left & set_right) / len(union)


def genome_distance(left: RoutingGenome, right: RoutingGenome) -> float:
    """Distancia semantica ponderada entre dos genomas (0.0 = identicos).

    Combina Jaccard de skills y agentes con diferencias normalizadas de
    temperatura, persona y topologia.

    Args:
        left: Primer genoma.
        right: Segundo genoma.

    Returns:
        Distancia en [0.0, 1.0].
    """
    skill_d = 1.0 - _jaccard(left.skills, right.skills)
    agent_d = 1.0 - _jaccard(left.agents, right.agents)
    temp_d = min(1.0, abs(left.temperature - right.temperature) / TEMPERATURE_SPAN)
    persona_d = 0.0 if left.persona == right.persona else 1.0
    topology_d = 0.0 if left.topology == right.topology else 1.0
    return (
        DISTANCE_WEIGHT_SKILLS * skill_d
        + DISTANCE_WEIGHT_AGENTS * agent_d
        + DISTANCE_WEIGHT_TEMPERATURE * temp_d
        + DISTANCE_WEIGHT_PERSONA * persona_d
        + DISTANCE_WEIGHT_TOPOLOGY * topology_d
    )


def cost_bucket_for(budget_tokens: int) -> str:
    """Discretiza el presupuesto de tokens en un bucket de coste.

    Args:
        budget_tokens: Presupuesto de tokens (> 0).

    Returns:
        ``low``, ``mid`` o ``high``.
    """
    if budget_tokens <= COST_LOW_MAX_TOKENS:
        return COST_LOW
    if budget_tokens <= COST_MID_MAX_TOKENS:
        return COST_MID
    return COST_HIGH


def depth_bucket_for(topology: str) -> str:
    """Deriva el bucket de profundidad a partir de la topologia.

    Args:
        topology: Topologia del genoma.

    Returns:
        ``shallow`` o ``deep`` (shallow por defecto si es desconocida).
    """
    return TOPOLOGY_DEPTH.get(topology, DEPTH_SHALLOW)


def _dominant_skill_family(genome: RoutingGenome) -> str:
    """Devuelve la familia (dominio) de la skill dominante del genoma.

    Args:
        genome: Genoma consultado.

    Returns:
        Dominio de la primera skill, o ``general`` si no hay/desconoce.
    """
    if not genome.skills:
        return FAMILY_GENERAL
    return _SKILL_DOMAIN.get(genome.skills[0], FAMILY_GENERAL)


def behavior_descriptor(
    genome: RoutingGenome,
    *,
    cost_bucket: str,
    depth_bucket: str,
) -> str:
    """Construye la clave de nicho con 4 ejes discretizados y estables.

    Args:
        genome: Genoma a describir.
        cost_bucket: Bucket de coste (``COST_BUCKETS``).
        depth_bucket: Bucket de profundidad (``DEPTH_BUCKETS``).

    Returns:
        Clave de nicho ``cost=..|depth=..|family=..|topology=..``.

    Raises:
        ValueError: Si los buckets no pertenecen a sus dominios (WHAT+WHY+WHERE).
    """
    if cost_bucket not in COST_BUCKETS:
        raise ValueError(
            f"WHAT: cost_bucket invalido {cost_bucket!r}. "
            f"WHY: valores admitidos {list(COST_BUCKETS)}. "
            "WHERE: routing_mutation.behavior_descriptor"
        )
    if depth_bucket not in DEPTH_BUCKETS:
        raise ValueError(
            f"WHAT: depth_bucket invalido {depth_bucket!r}. "
            f"WHY: valores admitidos {list(DEPTH_BUCKETS)}. "
            "WHERE: routing_mutation.behavior_descriptor"
        )
    family = _dominant_skill_family(genome)
    return f"cost={cost_bucket}|depth={depth_bucket}|family={family}|topology={genome.topology}"


class QDArchive:
    """Archivo Quality-Diversity: mejor variante por nicho (MAP-Elites/CVT).

    Nunca colapsa a una unica elite: cada nicho conserva su mejor genoma.
    """

    def __init__(self) -> None:
        """Inicializa un archivo vacio."""
        self._niches: dict[str, ScoredGenome] = {}

    def add(self, scored: ScoredGenome) -> bool:
        """Incorpora una variante si mejora la mejor de su nicho.

        Args:
            scored: Variante puntuada con su descriptor.

        Returns:
            True si se archivo (nicho nuevo o mejora); False si se descarto.
        """
        existing = self._niches.get(scored.descriptor)
        if existing is not None and scored.fitness <= existing.fitness:
            logger.debug(
                "QDArchive: descartada en nicho %s (%.3f <= %.3f)",
                scored.descriptor, scored.fitness, existing.fitness,
            )
            return False
        self._niches[scored.descriptor] = scored
        logger.debug("QDArchive: archivada en nicho %s", scored.descriptor)
        return True

    def best_per_niche(self) -> dict[str, ScoredGenome]:
        """Copia del mejor genoma por nicho.

        Returns:
            Mapa descriptor -> ScoredGenome (copia defensiva).
        """
        return dict(self._niches)

    @property
    def size(self) -> int:
        """Numero de nichos ocupados del archivo."""
        return len(self._niches)

    def niches(self) -> tuple[str, ...]:
        """Descriptores de nicho ocupados, ordenados (determinista).

        Returns:
            Tupla ordenada de claves de nicho.
        """
        return tuple(sorted(self._niches))

    def novelty(self, genome: RoutingGenome) -> float:
        """Distancia semantica media del genoma al resto del archivo.

        Args:
            genome: Genoma consultado.

        Returns:
            Media de distancias en [0, 1]; 0.0 si el archivo esta vacio.
        """
        if not self._niches:
            return 0.0
        distances = [
            genome_distance(genome, scored.genome)
            for scored in self._niches.values()
        ]
        return sum(distances) / len(distances)


def build_semantic_neighbors() -> dict[str, tuple[str, ...]]:
    """Vecinos semanticos por skill/agente reutilizando registros existentes.

    Skills: co-ocurrencia en ``DOMAIN_SKILLS``. Agentes: solape de keywords en
    ``AGENT_KEYWORDS`` (DRY con skill_bundler/agent_selector, sin duplicar).

    Returns:
        Mapa nombre -> tupla ordenada de vecinos (determinista).
    """
    neighbors: dict[str, set[str]] = {}
    for skills in DOMAIN_SKILLS.values():
        members = set(skills)
        for skill in skills:
            neighbors.setdefault(skill, set()).update(members - {skill})
    agent_keywords = {agent: set(kws) for agent, kws in AGENT_KEYWORDS.items()}
    for agent, keywords in agent_keywords.items():
        related = {
            other
            for other, other_kw in agent_keywords.items()
            if other != agent and keywords & other_kw
        }
        neighbors.setdefault(agent, set()).update(related)
    return {name: tuple(sorted(vals)) for name, vals in sorted(neighbors.items())}


def _load_agent_names() -> frozenset[str]:
    """Carga los nombres de agentes registrados en ``.opencode/agents``.

    Returns:
        Nombres de agentes (excluye variantes ``*.agent.min.md``); vacio si
        el directorio no existe.
    """
    if not _AGENTS_DIR.is_dir():
        logger.debug("routing_mutation: sin directorio de agentes %s", _AGENTS_DIR)
        return frozenset()
    try:
        names = {
            path.name[: -len(".md")]
            for path in _AGENTS_DIR.glob("*.md")
            if not path.name.endswith(".agent.min.md")
        }
    except OSError as exc:
        logger.warning("routing_mutation: no se pudo listar agentes (%s)", exc)
        return frozenset()
    return frozenset(names)


def default_allowlist() -> SafetyAllowlist:
    """Allowlist por defecto desde los registros reales del repo.

    Returns:
        SafetyAllowlist con skills registradas (``SKILL_TO_AGENT`` +
        ``DOMAIN_SKILLS``) y agentes de ``.opencode/agents``.
    """
    skills = frozenset(SKILL_TO_AGENT) | frozenset(_SKILL_DOMAIN)
    agents = frozenset(AGENT_KEYWORDS) | _load_agent_names()
    return SafetyAllowlist(skills=frozenset(skills), agents=frozenset(agents))


def _first_allowlist_violation(
    genome: RoutingGenome, allowlist: SafetyAllowlist
) -> str | None:
    """Detecta la primera skill/agente fuera de la allowlist.

    Args:
        genome: Genoma a validar.
        allowlist: Skills y agentes permitidos.

    Returns:
        Mensaje WHAT+WHY+WHERE de la violacion, o None si todo esta permitido.
    """
    unknown_skills = tuple(s for s in genome.skills if s not in allowlist.skills)
    if unknown_skills:
        return (
            f"WHAT: skills fuera de allowlist {unknown_skills}. "
            "WHY: mutar hacia capacidades desconocidas saltaria los gates. "
            "WHERE: routing_mutation.is_safe"
        )
    unknown_agents = tuple(a for a in genome.agents if a not in allowlist.agents)
    if unknown_agents:
        return (
            f"WHAT: agentes fuera de allowlist {unknown_agents}. "
            "WHY: el routing solo admite agentes registrados/reversibles. "
            "WHERE: routing_mutation.is_safe"
        )
    return None


def _first_forbidden_marker(
    genome: RoutingGenome, markers: frozenset[str]
) -> str | None:
    """Detecta el primer token prohibido (irreversible/secret) del genoma.

    Args:
        genome: Genoma a inspeccionar.
        markers: Marcadores prohibidos.

    Returns:
        Primer marcador hallado (orden determinista), o None.
    """
    haystack = " ".join(
        (*genome.skills, *genome.agents, genome.persona, genome.topology)
    ).lower()
    for marker in sorted(markers):
        if marker in haystack:
            return marker
    return None


def is_safe(
    genome: RoutingGenome,
    *,
    allowlist: SafetyAllowlist,
) -> tuple[bool, str]:
    """Valida el genoma contra allowlist y marcadores prohibidos.

    Args:
        genome: Genoma a validar.
        allowlist: Skills/agentes permitidos y marcadores prohibidos.

    Returns:
        ``(True, SAFE_REASON)`` si es seguro; ``(False, motivo)`` con WHAT+WHY+
        WHERE si viola allowlist o toca acciones irreversibles/secretos.
    """
    violation = _first_allowlist_violation(genome, allowlist)
    if violation is not None:
        return False, violation
    marker = _first_forbidden_marker(genome, allowlist.forbidden_markers)
    if marker is not None:
        return False, (
            f"WHAT: token prohibido {marker!r} en el genoma. "
            "WHY: acciones irreversibles o acceso a secretos violan SEG/SBX. "
            "WHERE: routing_mutation.is_safe"
        )
    return True, SAFE_REASON


def _mutation_count(rng: random.Random) -> int:
    """Decide cuantos genes mutar (1 o 2) segun la rate configurable.

    Args:
        rng: Generador aleatorio inyectado.

    Returns:
        ``GENES_MIN_PER_MUTATION`` o ``GENES_MAX_PER_MUTATION``.
    """
    if rng.random() < EXTRA_GENE_MUTATION_RATE:
        return GENES_MAX_PER_MUTATION
    return GENES_MIN_PER_MUTATION


def _pick_neighbor(value: str, candidates: Sequence[str], rng: random.Random) -> str:
    """Elige un vecino semantico distinto del valor actual.

    Args:
        value: Valor actual.
        candidates: Vecinos candidatos.
        rng: Generador aleatorio inyectado.

    Returns:
        Vecino distinto, o el valor original si no hay alternativa.
    """
    options = tuple(candidate for candidate in candidates if candidate != value)
    return rng.choice(options) if options else value


def _reorder_if_needed(
    values: tuple[str, ...], rng: random.Random
) -> tuple[str, ...]:
    """Reordena aleatoriamente la secuencia con probabilidad configurable.

    Args:
        values: Secuencia de genes (skills o agentes).
        rng: Generador aleatorio inyectado.

    Returns:
        Secuencia posiblemente reordenada.
    """
    if len(values) < 2 or rng.random() >= REORDER_PROBABILITY:
        return values
    shuffled = list(values)
    rng.shuffle(shuffled)
    return tuple(shuffled)


def _mutate_sequence(
    values: tuple[str, ...],
    *,
    neighbors: Mapping[str, Sequence[str]],
    rng: random.Random,
) -> tuple[str, ...]:
    """Muta una secuencia: sustituye un gen por vecino y reordena.

    Args:
        values: Secuencia de genes.
        neighbors: Mapa valor -> vecinos semanticos.
        rng: Generador aleatorio inyectado.

    Returns:
        Secuencia mutada (o la misma si no hay genes).
    """
    if not values:
        return values
    index = rng.randrange(len(values))
    candidates = neighbors.get(values[index], ())
    mutated = list(values)
    mutated[index] = _pick_neighbor(values[index], candidates, rng)
    return _reorder_if_needed(tuple(mutated), rng)


def _jitter_temperature(current: float, rng: random.Random) -> float:
    """Aplica jitter de temperatura garantizando un cambio dentro de rango.

    Args:
        current: Temperatura actual.
        rng: Generador aleatorio inyectado.

    Returns:
        Temperatura distinta dentro de ``[TEMPERATURE_MIN, TEMPERATURE_MAX]``.
    """
    steps = list(TEMPERATURE_JITTER_STEPS)
    rng.shuffle(steps)
    for delta in steps:
        candidate = round(current + delta, 4)
        candidate = min(TEMPERATURE_MAX, max(TEMPERATURE_MIN, candidate))
        if candidate != current:
            return candidate
    return current


def _jitter_budget(current: int, rng: random.Random) -> int:
    """Aplica jitter multiplicativo al presupuesto de tokens.

    Args:
        current: Presupuesto actual.
        rng: Generador aleatorio inyectado.

    Returns:
        Presupuesto distinto y acotado a ``[BUDGET_MIN_TOKENS, BUDGET_MAX_TOKENS]``.
    """
    delta = rng.uniform(-BUDGET_JITTER_FACTOR, BUDGET_JITTER_FACTOR)
    candidate = int(current * (1.0 + delta))
    candidate = min(BUDGET_MAX_TOKENS, max(BUDGET_MIN_TOKENS, candidate))
    if candidate == current:
        candidate = current + 1 if current < BUDGET_MAX_TOKENS else current - 1
    return candidate


def _mutate_persona(current: str, rng: random.Random) -> str:
    """Sustituye la persona por otra del pool anti-hivemind.

    Args:
        current: Persona actual.
        rng: Generador aleatorio inyectado.

    Returns:
        Persona distinta, o la original si el pool no tiene alternativas.
    """
    options = tuple(persona for persona in PERSONA_POOL if persona != current)
    return rng.choice(options) if options else current


def _mutate_topology(current: str, rng: random.Random) -> str:
    """Sustituye la topologia por otra valida distinta.

    Args:
        current: Topologia actual.
        rng: Generador aleatorio inyectado.

    Returns:
        Topologia distinta.
    """
    options = tuple(topology for topology in TOPOLOGIES if topology != current)
    return rng.choice(options) if options else current


def _apply_gene_mutation(
    genome: RoutingGenome,
    kind: str,
    *,
    neighbors: Mapping[str, Sequence[str]],
    rng: random.Random,
) -> RoutingGenome:
    """Aplica la mutacion de un unico gen (tipo de campo) del genoma.

    Args:
        genome: Genoma de partida.
        kind: Campo a mutar (``_GENE_KINDS``).
        neighbors: Mapa valor -> vecinos semanticos.
        rng: Generador aleatorio inyectado.

    Returns:
        Genoma con el gen indicado mutado.
    """
    if kind == "skills":
        return replace(genome, skills=_mutate_sequence(
            genome.skills, neighbors=neighbors, rng=rng
        ))
    if kind == "agents":
        return replace(genome, agents=_mutate_sequence(
            genome.agents, neighbors=neighbors, rng=rng
        ))
    if kind == "temperature":
        return replace(genome, temperature=_jitter_temperature(genome.temperature, rng))
    if kind == "persona":
        return replace(genome, persona=_mutate_persona(genome.persona, rng))
    if kind == "topology":
        return replace(genome, topology=_mutate_topology(genome.topology, rng))
    return replace(genome, budget_tokens=_jitter_budget(genome.budget_tokens, rng))


def mutate(
    genome: RoutingGenome,
    *,
    neighbors: Mapping[str, Sequence[str]],
    rng: random.Random,
) -> RoutingGenome:
    """Muta 1-2 genes del genoma de forma determinista con ``rng``.

    Sustituye genes por vecinos semanticos, aplica jitter de temperatura y
    presupuesto, cambia persona/topologia y reordena secuencias. Garantiza al
    menos un cambio.

    Args:
        genome: Genoma baseline (champion).
        neighbors: Mapa valor -> vecinos semanticos.
        rng: Generador aleatorio inyectado (determinismo con seed).

    Returns:
        Genoma mutado (distinto del original).
    """
    count = _mutation_count(rng)
    kinds = rng.sample(_GENE_KINDS, k=count)
    mutated = genome
    for kind in kinds:
        mutated = _apply_gene_mutation(
            mutated, kind, neighbors=neighbors, rng=rng
        )
    if mutated == genome:
        mutated = _apply_gene_mutation(
            genome, "temperature", neighbors=neighbors, rng=rng
        )
    return mutated


def _composite_fitness(
    quality: float,
    cost: float,
    latency: float,
    novelty: float,
    context: EvaluationContext,
) -> float:
    """Fitness compuesto: calidad - lambda*coste - mu*latencia + nu*novelty.

    Args:
        quality: Calidad observada (gates T1/T2).
        cost: Coste normalizado.
        latency: Latencia normalizada.
        novelty: Bonus de novedad.
        context: Pesos del fitness.

    Returns:
        Fitness compuesto (mayor es mejor).
    Raises:
        ValueError: Si cost o latency son negativos (WHAT+WHY+WHERE).
    """
    if cost < 0.0 or latency < 0.0:
        raise ValueError(
            f"WHAT: cost/latency negativos (cost={cost}, latency={latency}). "
            "WHY: solo se penaliza coste/latencia no negativos. "
            "WHERE: routing_mutation._composite_fitness"
        )
    return (
        quality
        - context.lambda_cost * cost
        - context.mu_latency * latency
        + context.nu_novelty * novelty
    )


def _is_healthy_variant(
    archive: QDArchive,
    scored: ScoredGenome,
    context: EvaluationContext,
) -> bool:
    """Decide si la variante aporta (nicho nuevo, mejora o senal de fallo).

    Args:
        archive: Archivo QD actual.
        scored: Variante puntuada.
        context: Baseline y fallos de referencia.

    Returns:
        True si debe archivarse; False si es equivalente (descartable).
    """
    existing = archive.best_per_niche().get(scored.descriptor)
    if existing is None:
        return True
    if scored.fitness > existing.fitness:
        return True
    if scored.fitness > context.baseline_fitness:
        return True
    return any(
        failure not in context.baseline_failures
        for failure in context.observed_failures
    )


def evaluate_and_archive(
    genome: RoutingGenome,
    archive: QDArchive,
    *,
    quality: float,
    cost: float,
    latency: float,
    context: EvaluationContext,
) -> ArchiveDecision:
    """Evalua la variante y la archiva si es sana, nueva o mejora el baseline.

    Args:
        genome: Variante de routing; archive: archivo QD destino.
        quality: Calidad T1/T2; cost: coste; latency: latencia (>=0).
        context: Allowlist, buckets, baseline, fallos y pesos.

    Returns:
        ArchiveDecision (aceptada o motivo de descarte).
    """
    safe, reason = is_safe(genome, allowlist=context.allowlist)
    if not safe:
        logger.warning("routing_mutation: rechazada por seguridad (%s)", reason)
        return ArchiveDecision(accepted=False, reason=reason, scored=None)
    descriptor = behavior_descriptor(
        genome, cost_bucket=context.cost_bucket, depth_bucket=context.depth_bucket
    )
    novelty = archive.novelty(genome)
    fitness = _composite_fitness(quality, cost, latency, novelty, context)
    scored = ScoredGenome(genome, fitness, descriptor, novelty)
    if not _is_healthy_variant(archive, scored, context):
        return ArchiveDecision(accepted=False, reason=EQUIVALENT_REASON, scored=scored)
    archive.add(scored)
    return ArchiveDecision(accepted=True, reason=ARCHIVED_REASON, scored=scored)
