"""Tests de sincronizacion del routing de skills/agentes con el registry real.

WHAT: fija (TDD RED->GREEN) los tres gaps de sincronizacion verificados en la
auditoria de routing:

(a) ``harness/memory_rag/skill_router.SKILL_REGISTRY`` estaba HARDCODEADO a ~10
    skills (stale) mientras ``.opencode/skills/skills_registry.yaml`` (SSOT)
    declara el registry real; el router debe DERIVAR su registry del YAML.
(b) en ``harness/orchestrator/skill_bundler`` los ``DOMAIN_KEYWORDS``/
    ``DOMAIN_SKILLS`` dejaban inalcanzables por keyword a ~20 skills del
    registry; cada skill del SSOT debe ser alcanzable por al menos un dominio
    con keywords (o figurar en una allowlist justificada).
(c) ``delegation.agents`` de ``.opencode/agents/coordinator_policy.yaml``
    auto-detectaba solo 4 roles; debe cubrir los 24 agentes reales de
    ``.opencode/agents/*.md``.
(d) ``SKILL_TO_AGENT`` del bundler debe cubrir TODAS las skills del registry con
    valores que sean agentes reales (coherencia SIGMA).

WHY: un agente nunca afirma, verifica (VER). El routing desincronizado degrada
la seleccion de skills/agentes (SSOT vs copia stale) y hace inalcanzables
capacidades ya registradas.

WHERE: ``harness/tests`` — suite de solo lectura sobre produccion (no la edita).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from harness.memory_rag import skill_router
from harness.orchestrator.skill_bundler import (
    DOMAIN_KEYWORDS,
    DOMAIN_SKILLS,
    SKILL_TO_AGENT,
)

# ---------------------------------------------------------------------------
# Rutas y constantes (MAG: sin literales repetidos)
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / ".opencode" / "skills" / "skills_registry.yaml"
AGENTS_DIR = ROOT / ".opencode" / "agents"
POLICY_PATH = AGENTS_DIR / "coordinator_policy.yaml"

#: Sufijo de los artefactos precompilados que NO son definiciones de agente.
_MIN_AGENT_SUFFIX = ".agent.min.md"

#: Minimo de skills que el router debe cubrir (piso historico del gap; el
#: resto se exige por igualdad con el SSOT, que puede crecer).
MIN_REGISTRY_SKILLS = 37

#: Skills exentas de ser alcanzables por keyword (allowlist justificada).
#: Vacia a proposito: hoy TODAS las skills del SSOT deben ser alcanzables.
UNREACHABLE_ALLOWLIST: frozenset[str] = frozenset()

#: Dominio de respaldo (no se detecta por keyword; es el fallback).
_FALLBACK_DOMAIN = "general"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_registry() -> list[dict]:
    """Carga las entradas del registry SSOT de skills.

    Returns:
        Lista de mappings ``{name, domain, description, ...}`` del YAML.

    Raises:
        FileNotFoundError: Si el registry no existe en la ruta esperada.
    """
    data = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    return list(data["skills"])


def _registry_names() -> set[str]:
    """Nombres canonicos de las skills del SSOT.

    Returns:
        Conjunto de nombres de skill.
    """
    return {str(item["name"]) for item in _load_registry()}


def _real_agent_names() -> set[str]:
    """Nombres de los agentes reales del repo.

    WHAT: lee ``.opencode/agents/*.md`` excluyendo los artefactos
    precompilados ``*.agent.min.md``. WHERE: auditoria de ``delegation.agents``.

    Returns:
        Conjunto de nombres de agente; vacio si el directorio no existe.
    """
    if not AGENTS_DIR.is_dir():
        return set()
    return {
        path.stem
        for path in AGENTS_DIR.glob("*.md")
        if not path.name.endswith(_MIN_AGENT_SUFFIX)
    }


def _reachable_skills() -> set[str]:
    """Skills alcanzables por keyword via dominios con triggers declarados.

    WHAT: une ``DOMAIN_SKILLS`` solo para dominios presentes en
    ``DOMAIN_KEYWORDS`` con al menos una keyword no vacia. WHY: un dominio sin
    keywords nunca se detecta, asi que sus skills son inalcanzables. WHERE:
    gap (b) del routing.

    Returns:
        Conjunto de skills alcanzables.
    """
    reachable: set[str] = set()
    for domain, keywords in DOMAIN_KEYWORDS.items():
        if not any(str(kw).strip() for kw in keywords):
            continue
        reachable.update(DOMAIN_SKILLS.get(domain, ()))
    return reachable


# ---------------------------------------------------------------------------
# (a) El router DERIVA su registry del SSOT YAML
# ---------------------------------------------------------------------------


class TestRouterRegistrySync:
    """El ``SKILL_REGISTRY`` del router refleja el SSOT (no una copia stale)."""

    def test_router_registry_is_derived_from_yaml(self) -> None:
        """``SKILL_REGISTRY`` cubre exactamente los nombres del SSOT."""
        routed = {entry["name"] for entry in skill_router.SKILL_REGISTRY}
        assert routed == _registry_names(), (
            "SKILL_REGISTRY debe derivarse del skills_registry.yaml; "
            f"faltan={sorted(_registry_names() - routed)} "
            f"sobran={sorted(routed - _registry_names())}"
        )

    def test_router_registry_meets_minimum_floor(self) -> None:
        """El router cubre al menos :data:`MIN_REGISTRY_SKILLS` skills."""
        assert len(skill_router.SKILL_REGISTRY) >= MIN_REGISTRY_SKILLS

    def test_every_router_entry_has_domain_and_keywords(self) -> None:
        """Cada entrada derivada tiene dominio y keywords no vacios."""
        for entry in skill_router.SKILL_REGISTRY:
            assert entry["domain"], f"{entry['name']}: dominio vacio"
            assert entry["keywords"].strip(), f"{entry['name']}: keywords vacias"

    def test_router_exposes_loader_for_lazy_rebuild(self) -> None:
        """El router expone un loader reutilizable (cache) del SSOT."""
        assert callable(skill_router.load_skill_registry)
        loaded = skill_router.load_skill_registry()
        assert {e["name"] for e in loaded} == _registry_names()


# ---------------------------------------------------------------------------
# (b) Cada skill del registry es alcanzable por keyword
# ---------------------------------------------------------------------------


class TestSkillReachability:
    """Todas las skills del SSOT se alcanzan por algun dominio con keywords."""

    def test_every_registry_skill_is_reachable(self) -> None:
        """Sin skills huerfanas: registry - allowlist <= alcanzables."""
        expected = _registry_names() - UNREACHABLE_ALLOWLIST
        reachable = _reachable_skills()
        missing = sorted(expected - reachable)
        assert not missing, (
            "skills inalcanzables por keyword (sin dominio con triggers): "
            f"{missing}"
        )

    def test_reachable_domains_have_keywords(self) -> None:
        """Todo dominio detectable de ``DOMAIN_SKILLS`` tiene keywords.

        WHAT: excluye :data:`_FALLBACK_DOMAIN` ("general"), que es el respaldo
        de ``detect_domain`` y nunca se dispara por keyword. WHY: un dominio
        detectable sin triggers jamas se elige, dejando sus skills inalcanzables
        (dead routing). WHERE: gap (b).
        """
        without = sorted(
            domain
            for domain in DOMAIN_SKILLS
            if domain != _FALLBACK_DOMAIN
            and not any(str(kw).strip() for kw in DOMAIN_KEYWORDS.get(domain, ()))
        )
        assert not without, f"dominios sin keywords de trigger: {without}"

    def test_each_new_skill_has_trigger_keywords(self) -> None:
        """Cada skill del SSOT aparece en algun dominio listado con keywords."""
        reachable = _reachable_skills()
        for name in sorted(_registry_names()):
            assert name in reachable, f"{name} no es alcanzable por keyword"


# ---------------------------------------------------------------------------
# (c) delegation.agents cubre los 24 agentes reales
# ---------------------------------------------------------------------------


class TestDelegationAgentsSync:
    """La politica del coordinator conoce a todos los agentes reales."""

    def _delegation_agents(self) -> dict:
        """Carga ``delegation.agents`` del YAML SSOT de politica.

        Returns:
            Mapping ``agente -> lista de triggers``.

        Raises:
            KeyError: Si falta la seccion ``delegation.agents``.
        """
        policy = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))
        return dict(policy["delegation"]["agents"])

    def test_delegation_agents_cover_all_real_agents(self) -> None:
        """Cada agente real de ``.opencode/agents`` figura en la politica."""
        agents = self._delegation_agents()
        missing = sorted(_real_agent_names() - set(agents))
        assert not missing, (
            "delegation.agents no cubre agentes reales del repo: "
            f"{missing}"
        )

    def test_delegation_agents_have_triggers(self) -> None:
        """Cada agente de la politica declara al menos un trigger."""
        agents = self._delegation_agents()
        empty = sorted(name for name, kws in agents.items() if not kws)
        assert not empty, f"agentes sin triggers en delegation.agents: {empty}"


# ---------------------------------------------------------------------------
# (d) SKILL_TO_AGENT cubre el registry con agentes reales
# ---------------------------------------------------------------------------


class TestSkillToAgentSync:
    """La matriz SIGMA skills->agente cubre el registry y usa agentes reales."""

    def test_skill_to_agent_covers_registry(self) -> None:
        """Toda skill del SSOT tiene agente primario declarado."""
        missing = sorted(_registry_names() - set(SKILL_TO_AGENT))
        assert not missing, f"skills sin SKILL_TO_AGENT: {missing}"

    def test_skill_to_agent_values_are_real_agents(self) -> None:
        """Los agentes destino existen en ``.opencode/agents``."""
        unknown = sorted(set(SKILL_TO_AGENT.values()) - _real_agent_names())
        assert not unknown, f"SKILL_TO_AGENT apunta a agentes inexistentes: {unknown}"
