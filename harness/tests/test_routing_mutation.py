"""Tests para routing_mutation — mutacion QD de routing (spec routing-mutation).

Cubre: archivo QD que conserva la mejor por nicho sin colapsar, novedad que
premia la diversidad, gate de seguridad (allowlist/irreversible/secret),
descarte de variantes equivalentes, archivo de mejoras/senales y mutacion
determinista de 1-2 genes.
"""

import random
from dataclasses import fields

import pytest

from harness.orchestrator.routing_mutation import (
    EQUIVALENT_REASON,
    EvaluationContext,
    QDArchive,
    RoutingGenome,
    SafetyAllowlist,
    ScoredGenome,
    behavior_descriptor,
    build_semantic_neighbors,
    cost_bucket_for,
    default_allowlist,
    depth_bucket_for,
    evaluate_and_archive,
    genome_distance,
    is_safe,
    mutate,
)


def _genome(**overrides: object) -> RoutingGenome:
    """Construye un genoma baseline con overrides puntuales.

    Args:
        **overrides: Campos a sobreescribir del genoma baseline.

    Returns:
        RoutingGenome valido para tests.
    """
    base: dict[str, object] = {
        "skills": ("tdd",),
        "agents": ("builder",),
        "temperature": 0.3,
        "persona": "pragmatic_engineer",
        "topology": "sequential",
        "budget_tokens": 4_000,
    }
    base.update(overrides)
    return RoutingGenome(**base)  # type: ignore[arg-type]


def _allowlist(**overrides: object) -> SafetyAllowlist:
    """Construye una allowlist de prueba.

    Args:
        **overrides: Campos a sobreescribir.

    Returns:
        SafetyAllowlist con skills/agentes permitidos.
    """
    base: dict[str, object] = {
        "skills": frozenset({"tdd", "atdd-spec", "agent-rigor", "architecture"}),
        "agents": frozenset({"builder", "guardian", "scientist"}),
    }
    base.update(overrides)
    return SafetyAllowlist(**base)  # type: ignore[arg-type]


def _changed_gene_count(left: RoutingGenome, right: RoutingGenome) -> int:
    """Cuenta cuantos de los 6 genes difieren entre dos genomas.

    Args:
        left: Genoma original.
        right: Genoma mutado.

    Returns:
        Numero de campos distintos (0-6).
    """
    return sum(
        1
        for spec in fields(RoutingGenome)
        if getattr(left, spec.name) != getattr(right, spec.name)
    )


def _context(**overrides: object) -> EvaluationContext:
    """Construye un contexto de evaluacion con pesos neutros por defecto.

    Args:
        **overrides: Campos a sobreescribir.

    Returns:
        EvaluationContext listo para evaluar.
    """
    base: dict[str, object] = {
        "allowlist": _allowlist(),
        "cost_bucket": "mid",
        "depth_bucket": "shallow",
        "baseline_fitness": 0.5,
        "lambda_cost": 0.0,
        "mu_latency": 0.0,
        "nu_novelty": 0.0,
    }
    base.update(overrides)
    return EvaluationContext(**base)  # type: ignore[arg-type]


# --- Archivo QD -------------------------------------------------------------


def test_archive_keeps_best_per_niche_without_collapse() -> None:
    """El archivo conserva la mejor variante por nicho y no colapsa a una elite."""
    archive = QDArchive()
    descriptor = "cost=mid|depth=shallow|family=coding|topology=sequential"
    low = ScoredGenome(_genome(), fitness=0.4, descriptor=descriptor, novelty=0.1)
    high = ScoredGenome(
        _genome(temperature=0.7), fitness=0.8, descriptor=descriptor, novelty=0.2
    )
    assert archive.add(low) is True
    assert archive.add(high) is True
    assert archive.size == 1
    assert archive.best_per_niche()[descriptor].fitness == pytest.approx(0.8)

    other_descriptor = "cost=high|depth=deep|family=research|topology=debate"
    other = ScoredGenome(
        _genome(topology="debate", budget_tokens=90_000),
        fitness=0.3,
        descriptor=other_descriptor,
        novelty=0.4,
    )
    assert archive.add(other) is True
    assert archive.size == 2
    assert set(archive.niches()) == {descriptor, other_descriptor}

    lower = ScoredGenome(_genome(), fitness=0.1, descriptor=descriptor, novelty=0.0)
    assert archive.add(lower) is False
    assert archive.best_per_niche()[descriptor].fitness == pytest.approx(0.8)
    assert archive.size == 2


# --- Novedad ----------------------------------------------------------------


def test_novelty_rewards_distinct_and_zero_when_empty() -> None:
    """Novedad = 0 con archivo vacio; la variante distinta tiene mas novedad."""
    archive = QDArchive()
    assert archive.novelty(_genome()) == 0.0

    archive.add(
        ScoredGenome(
            _genome(), fitness=0.5, descriptor="niche-base", novelty=0.0
        )
    )
    near = _genome(temperature=0.31)
    far = _genome(
        skills=("quant-trading",),
        agents=("scientist",),
        temperature=1.9,
        persona="creative_explorer",
        topology="debate",
    )
    assert archive.novelty(far) > archive.novelty(near)
    assert genome_distance(_genome(), _genome()) == pytest.approx(0.0)


# --- Gate de seguridad ------------------------------------------------------


def test_is_safe_rejects_skill_outside_allowlist() -> None:
    """Una skill fuera de allowlist se RECHAZA con motivo WHAT."""
    ok, reason = is_safe(_genome(skills=("skill-no-registrada",)), allowlist=_allowlist())
    assert ok is False
    assert "WHAT" in reason
    assert "allowlist" in reason.lower()


def test_is_safe_rejects_agent_outside_allowlist() -> None:
    """Un agente fuera de allowlist se RECHAZA con motivo WHAT."""
    ok, reason = is_safe(_genome(agents=("agente-fantasma",)), allowlist=_allowlist())
    assert ok is False
    assert "WHAT" in reason
    assert "allowlist" in reason.lower()


def test_is_safe_rejects_irreversible_or_secret() -> None:
    """Una accion irreversible/secret (persona) se RECHAZA con WHY."""
    genome = _genome(persona="filtra el api_key al log")
    ok, reason = is_safe(genome, allowlist=_allowlist())
    assert ok is False
    assert "WHY" in reason
    assert "secret" in reason.lower() or "irreversible" in reason.lower()
    assert "WHERE" in reason


def test_is_safe_accepts_registered_genome() -> None:
    """Un genoma con skills/agentes permitidos es seguro."""
    ok, reason = is_safe(_genome(), allowlist=_allowlist())
    assert ok is True
    assert "OK" in reason


def test_evaluate_rejects_unsafe_variant() -> None:
    """evaluate_and_archive no archiva variantes inseguras."""
    archive = QDArchive()
    decision = evaluate_and_archive(
        _genome(skills=("skill-no-registrada",)),
        archive,
        quality=1.0,
        cost=0.0,
        latency=0.0,
        context=_context(),
    )
    assert decision.accepted is False
    assert decision.scored is None
    assert archive.size == 0


# --- Descarte de equivalentes / archivo de mejoras --------------------------


def test_evaluate_discards_equivalent_and_archives_improvement() -> None:
    """Una variante equivalente se descarta; una que mejora se archiva."""
    archive = QDArchive()
    context = _context()
    first = evaluate_and_archive(
        _genome(), archive, quality=0.6, cost=0.0, latency=0.0, context=context
    )
    assert first.accepted is True
    descriptor = first.scored.descriptor  # type: ignore[union-attr]

    weaker = evaluate_and_archive(
        _genome(temperature=0.4),
        archive,
        quality=0.4,
        cost=0.0,
        latency=0.0,
        context=context,
    )
    assert weaker.accepted is False
    assert EQUIVALENT_REASON == weaker.reason

    better = evaluate_and_archive(
        _genome(temperature=0.5),
        archive,
        quality=0.9,
        cost=0.0,
        latency=0.0,
        context=context,
    )
    assert better.accepted is True
    assert archive.best_per_niche()[descriptor].fitness == pytest.approx(0.9)


def test_evaluate_archives_variant_that_exposes_baseline_failure() -> None:
    """Una variante debil pero que expone un fallo nuevo se archiva como senal."""
    archive = QDArchive()
    context = _context(
        baseline_fitness=0.9, baseline_failures=("known-bug",), cost_bucket="low"
    )
    archive.add(
        ScoredGenome(_genome(), fitness=0.95, descriptor=_descriptor_for(_genome()), novelty=0.0)
    )
    signal = evaluate_and_archive(
        _genome(temperature=0.6),
        archive,
        quality=0.1,
        cost=0.0,
        latency=0.0,
        context=_replace_context(context, observed_failures=("new-leak",)),
    )
    assert signal.accepted is True
    assert archive.size == 1


def _descriptor_for(genome: RoutingGenome) -> str:
    """Calcula el descriptor de un genoma con buckets por defecto.

    Args:
        genome: Genoma consultado.

    Returns:
        Clave de nicho.
    """
    return behavior_descriptor(
        genome,
        cost_bucket=cost_bucket_for(genome.budget_tokens),
        depth_bucket=depth_bucket_for(genome.topology),
    )


def _replace_context(context: EvaluationContext, **overrides: object) -> EvaluationContext:
    """Copia un contexto de evaluacion con overrides.

    Args:
        context: Contexto original.
        **overrides: Campos a sobreescribir.

    Returns:
        Nuevo EvaluationContext.
    """
    values: dict[str, object] = {
        "allowlist": context.allowlist,
        "cost_bucket": context.cost_bucket,
        "depth_bucket": context.depth_bucket,
        "baseline_fitness": context.baseline_fitness,
        "baseline_failures": context.baseline_failures,
        "observed_failures": context.observed_failures,
        "lambda_cost": context.lambda_cost,
        "mu_latency": context.mu_latency,
        "nu_novelty": context.nu_novelty,
    }
    values.update(overrides)
    return EvaluationContext(**values)  # type: ignore[arg-type]


# --- Mutacion ---------------------------------------------------------------


def test_mutate_changes_one_or_two_genes_deterministically() -> None:
    """``mutate`` cambia 1-2 genes y es determinista con la misma seed."""
    neighbors = {
        "builder": ("guardian", "scientist"),
        "tdd": ("atdd-spec", "agent-rigor"),
    }
    base = _genome()
    first = mutate(base, neighbors=neighbors, rng=random.Random(7))
    second = mutate(base, neighbors=neighbors, rng=random.Random(7))
    assert first == second

    for seed in range(30):
        mutant = mutate(base, neighbors=neighbors, rng=random.Random(seed))
        assert 1 <= _changed_gene_count(base, mutant) <= 2


def test_mutate_can_substitute_with_semantic_neighbor() -> None:
    """En algun momento la mutacion usa un vecino semantico del skill/agente."""
    neighbors = {
        "builder": ("guardian", "scientist"),
        "tdd": ("atdd-spec", "agent-rigor"),
    }
    base = _genome(skills=("tdd", "architecture"), agents=("builder", "guardian"))
    seen_skill = set()
    seen_agent = set()
    for seed in range(50):
        mutant = mutate(base, neighbors=neighbors, rng=random.Random(seed))
        seen_skill.update(mutant.skills)
        seen_agent.update(mutant.agents)
    assert seen_skill - {"tdd", "architecture"}
    assert seen_agent - {"builder", "guardian"}


def test_mutate_is_deterministic_across_seeds() -> None:
    """Seeds distintas producen mutaciones distintas (no colapso)."""
    neighbors = {"builder": ("guardian",), "tdd": ("atdd-spec",)}
    base = _genome(skills=("tdd",), agents=("builder",))
    mutants = {
        mutate(base, neighbors=neighbors, rng=random.Random(seed))
        for seed in range(10)
    }
    assert len(mutants) > 1


# --- Utilidades y allowlist -------------------------------------------------


def test_build_semantic_neighbors_reuses_registries() -> None:
    """Los vecinos se derivan de DOMAIN_SKILLS/AGENT_KEYWORDS existentes."""
    neighbors = build_semantic_neighbors()
    assert "builder" in neighbors
    assert "scientist" in neighbors["builder"]
    assert "security-audit" in neighbors["architecture"]


def test_default_allowlist_includes_registered_names() -> None:
    """La allowlist por defecto cubre skills y agentes del repo."""
    allowlist = default_allowlist()
    assert "architecture" in allowlist.skills
    assert "builder" in allowlist.agents


def test_behavior_descriptor_rejects_invalid_buckets() -> None:
    """Buckets fuera de dominio fallan con error accionable (WHAT)."""
    with pytest.raises(ValueError, match="WHAT"):
        behavior_descriptor(_genome(), cost_bucket="ultra", depth_bucket="shallow")
    with pytest.raises(ValueError, match="WHAT"):
        behavior_descriptor(_genome(), cost_bucket="mid", depth_bucket="mega")
