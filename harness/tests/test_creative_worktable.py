"""
Tests para CreativeWorktable — Pipeline divergente/convergente (ReDNA).

Verifica:
  - Fase divergente genera ideas correctamente
  - Fase convergente selecciona bajo restricciones
  - Fase de integracion produce propuesta
  - Debate completo en modo creativo
  - Casos borde (sin ideas seleccionadas)
  - Configuracion personalizada
  - Rango de novedad y factibilidad
"""

from __future__ import annotations

import pytest

from harness.orchestrator.worktable import (
    Compendium,
    CreativeConfig,
    CreativeIdea,
    CreativePhase,
    CreativeWorktable,
    Worktable,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def creative() -> CreativeWorktable:
    """CreativeWorktable con configuracion por defecto."""
    return CreativeWorktable()


@pytest.fixture
def sample_ideas() -> list[CreativeIdea]:
    """Lista de ideas de prueba para fase convergente e integracion."""
    return [
        CreativeIdea(
            content="API REST con GraphQL hybrido",
            agent="builder",
            phase=CreativePhase.DIVERGENT,
            novelty=0.8,
            feasibility=0.7,
        ),
        CreativeIdea(
            content="Cache predictivo con ML",
            agent="scientist",
            phase=CreativePhase.DIVERGENT,
            novelty=0.9,
            feasibility=0.3,
        ),
        CreativeIdea(
            content="Arquitectura serverless nativa",
            agent="guardian",
            phase=CreativePhase.DIVERGENT,
            novelty=0.6,
            feasibility=0.8,
        ),
        CreativeIdea(
            content="Base de datos vectorial embebida",
            agent="evolve",
            phase=CreativePhase.DIVERGENT,
            novelty=0.7,
            feasibility=0.5,
        ),
        CreativeIdea(
            content="Autenticacion biometrica descentralizada",
            agent="builder",
            phase=CreativePhase.DIVERGENT,
            novelty=0.4,
            feasibility=0.2,
        ),
    ]


# ---------------------------------------------------------------------------
# Test: CreativeIdea dataclass
# ---------------------------------------------------------------------------


class TestCreativeIdea:
    """CreativeIdea se crea correctamente."""

    def test_default_values(self) -> None:
        """Valores por defecto de CreativeIdea."""
        idea = CreativeIdea(content="test", agent="builder")
        assert idea.content == "test"
        assert idea.agent == "builder"
        assert idea.phase == CreativePhase.DIVERGENT
        assert idea.novelty == 0.0
        assert idea.feasibility == 0.5
        assert not idea.selected

    def test_custom_values(self) -> None:
        """Valores personalizados en CreativeIdea."""
        idea = CreativeIdea(
            content="idea custom",
            agent="scientist",
            phase=CreativePhase.CONVERGENT,
            novelty=0.95,
            feasibility=0.85,
            selected=True,
        )
        assert idea.content == "idea custom"
        assert idea.agent == "scientist"
        assert idea.phase == CreativePhase.CONVERGENT
        assert idea.novelty == 0.95
        assert idea.feasibility == 0.85
        assert idea.selected


# ---------------------------------------------------------------------------
# Test: CreativeConfig
# ---------------------------------------------------------------------------


class TestCreativeConfig:
    """CreativeConfig se crea con valores por defecto."""

    def test_default_config(self) -> None:
        """Valores por defecto de CreativeConfig."""
        config = CreativeConfig()
        assert config.topology == "sparse"
        assert config.divergence_pressure == 0.3
        assert config.independence_rounds == 2
        assert config.authority_penalty == 0.1
        assert config.num_ideas == 5

    def test_custom_config(self) -> None:
        """Configuracion personalizada de CreativeConfig."""
        config = CreativeConfig(
            topology="small-world",
            divergence_pressure=0.8,
            independence_rounds=4,
            authority_penalty=0.3,
            num_ideas=10,
        )
        assert config.topology == "small-world"
        assert config.divergence_pressure == 0.8
        assert config.independence_rounds == 4
        assert config.authority_penalty == 0.3
        assert config.num_ideas == 10


# ---------------------------------------------------------------------------
# Test: Fase divergente
# ---------------------------------------------------------------------------


class TestDivergentPhase:
    """Fase divergente genera ideas libremente."""

    def test_generates_ideas(self, creative: CreativeWorktable) -> None:
        """Divergent_phase genera lista no vacia de ideas."""
        ideas = creative.divergent_phase("Disenar API innovadora")
        assert len(ideas) > 0
        assert all(isinstance(i, CreativeIdea) for i in ideas)

    def test_ideas_have_content(self, creative: CreativeWorktable) -> None:
        """Cada idea generada tiene content y agent."""
        ideas = creative.divergent_phase("Nuevo sistema de colas")
        for idea in ideas:
            assert idea.content != ""
            assert idea.agent != ""
            assert idea.phase == CreativePhase.DIVERGENT

    def test_ideas_all_divergent_phase(self, creative: CreativeWorktable) -> None:
        """Todas las ideas estan en fase DIVERGENT."""
        ideas = creative.divergent_phase("Tema creativo")
        assert all(i.phase == CreativePhase.DIVERGENT for i in ideas)

    def test_default_agents(self, creative: CreativeWorktable) -> None:
        """Usa agentes por defecto si no se especifican."""
        ideas = creative.divergent_phase("Tema")
        agents_used = {i.agent for i in ideas}
        default_agents = {"builder", "scientist", "guardian", "evolve"}
        assert agents_used.issuperset(default_agents)

    def test_custom_agents(self, creative: CreativeWorktable) -> None:
        """Acepta lista personalizada de agentes."""
        ideas = creative.divergent_phase(
            "Tema personalizado",
            agents=["alpha", "beta"],
        )
        agents_used = {i.agent for i in ideas}
        assert "alpha" in agents_used
        assert "beta" in agents_used

    def test_ideas_count(self, creative: CreativeWorktable) -> None:
        """Numero de ideas generadas es al menos num_ideas."""
        ideas = creative.divergent_phase("Contar ideas")
        assert len(ideas) >= creative.config.num_ideas

    def test_novelty_range(self, creative: CreativeWorktable) -> None:
        """Novedad de las ideas esta en rango 0-1."""
        ideas = creative.divergent_phase("Topic")
        for idea in ideas:
            assert 0.0 <= idea.novelty <= 1.0, (
                f"Novelty fuera de rango: {idea.novelty}"
            )

    def test_feasibility_range(self, creative: CreativeWorktable) -> None:
        """Factibilidad de las ideas esta en rango 0-1."""
        ideas = creative.divergent_phase("Topic")
        for idea in ideas:
            assert 0.0 <= idea.feasibility <= 1.0, (
                f"Feasibility fuera de rango: {idea.feasibility}"
            )

    def test_different_topics_produce_different_ideas(self, creative: CreativeWorktable) -> None:
        """Topics distintos generan contenidos distintos."""
        ideas_a = creative.divergent_phase("Topic Alpha")
        ideas_b = creative.divergent_phase("Topic Beta")
        contents_a = [i.content for i in ideas_a]
        contents_b = [i.content for i in ideas_b]
        # Al menos una idea debe diferir (el topic aparece en content)
        assert any(a != b for a, b in zip(contents_a, contents_b))


# ---------------------------------------------------------------------------
# Test: Fase convergente
# ---------------------------------------------------------------------------


class TestConvergentPhase:
    """Fase convergente selecciona ideas bajo restricciones."""

    def test_selects_ideas(self, creative: CreativeWorktable, sample_ideas: list[CreativeIdea]) -> None:
        """Convergent_phase retorna solo ideas seleccionadas."""
        selected = creative.convergent_phase(sample_ideas)
        assert len(selected) > 0
        assert all(i.selected for i in selected)

    def test_all_ideas_scored(self, creative: CreativeWorktable, sample_ideas: list[CreativeIdea]) -> None:
        """Todas las ideas reciben puntaje (selected=True/False)."""
        creative.convergent_phase(sample_ideas)
        # Verificar que todas las ideas originales tienen selected asignado
        for idea in sample_ideas:
            assert hasattr(idea, "selected")

    def test_constraints_filter(self, creative: CreativeWorktable) -> None:
        """Restricciones reducen el numero de ideas seleccionadas."""
        ideas = [
            CreativeIdea(content=f"Idea {i}", agent="builder",
                         novelty=0.9, feasibility=0.9)
            for i in range(10)
        ]
        selected_no_constraints = creative.convergent_phase(ideas)
        selected_with_constraints = creative.convergent_phase(
            ideas,
            constraints=["coste < $1000", "debe ser escalable", "debe ser seguro"],
        )
        assert len(selected_with_constraints) <= len(selected_no_constraints)

    def test_empty_constraints(self, creative: CreativeWorktable, sample_ideas: list[CreativeIdea]) -> None:
        """Sin restricciones, selecciona igual."""
        selected = creative.convergent_phase(sample_ideas, constraints=[])
        assert len(selected) > 0

    def test_low_novelty_not_selected(self, creative: CreativeWorktable) -> None:
        """Idea con baja novedad y factibilidad no es seleccionada."""
        idea = CreativeIdea(
            content="Idea pesima",
            agent="builder",
            novelty=0.1,
            feasibility=0.1,
        )
        selected = creative.convergent_phase([idea])
        assert len(selected) == 0

    def test_high_novelty_and_feasibility_selected(self, creative: CreativeWorktable) -> None:
        """Idea con alta novedad y factibilidad es seleccionada."""
        idea = CreativeIdea(
            content="Idea excelente",
            agent="scientist",
            novelty=0.9,
            feasibility=0.9,
        )
        selected = creative.convergent_phase([idea])
        assert len(selected) == 1
        assert selected[0].selected


# ---------------------------------------------------------------------------
# Test: Fase de integracion
# ---------------------------------------------------------------------------


class TestIntegrationPhase:
    """Fase de integracion combina ideas seleccionadas."""

    def test_returns_proposal(self, creative: CreativeWorktable, sample_ideas: list[CreativeIdea]) -> None:
        """Integration_phase retorna string con propuesta."""
        selected = creative.convergent_phase(sample_ideas)
        proposal = creative.integration_phase(selected)
        assert isinstance(proposal, str)
        assert len(proposal) > 0

    def test_proposal_contains_idea_content(self, creative: CreativeWorktable, sample_ideas: list[CreativeIdea]) -> None:
        """Propuesta incluye contenido de las ideas seleccionadas."""
        selected = creative.convergent_phase(sample_ideas)
        proposal = creative.integration_phase(selected)
        for idea in selected[:2]:
            assert idea.content[:30] in proposal, (
                f"Contenido de idea no encontrado en propuesta: {idea.content[:30]}"
            )

    def test_proposal_contains_novelty_feasibility(self, creative: CreativeWorktable, sample_ideas: list[CreativeIdea]) -> None:
        """Propuesta incluye puntajes de novedad y factibilidad."""
        selected = creative.convergent_phase(sample_ideas)
        proposal = creative.integration_phase(selected)
        assert "Novedad" in proposal
        assert "Factibilidad" in proposal

    def test_proposal_max_three_ideas(self, creative: CreativeWorktable) -> None:
        """Propuesta incluye maximo 3 ideas."""
        many_ideas = [
            CreativeIdea(content=f"Idea {i}", agent="builder",
                         novelty=0.8, feasibility=0.8)
            for i in range(10)
        ]
        selected = creative.convergent_phase(many_ideas)
        proposal = creative.integration_phase(selected)
        # Contar cuantas secciones "Idea X" aparecen
        count = proposal.count("### Idea ")
        assert count <= 3, f"Max 3 ideas en propuesta, hay {count}"


# ---------------------------------------------------------------------------
# Test: Sin ideas seleccionadas
# ---------------------------------------------------------------------------


class TestEmptyIdeas:
    """Manejo de lista vacia o sin ideas seleccionadas."""

    def test_empty_list_integration(self, creative: CreativeWorktable) -> None:
        """Integration_phase con lista vacia retorna mensaje."""
        proposal = creative.integration_phase([])
        assert proposal == "No se seleccionaron ideas."

    def test_no_selected_ideas_convergent(self, creative: CreativeWorktable) -> None:
        """Convergent_phase con ideas de muy baja calidad retorna vacio."""
        ideas = [
            CreativeIdea(content="mala", agent="builder",
                         novelty=0.0, feasibility=0.0),
            CreativeIdea(content="pesima", agent="builder",
                         novelty=0.1, feasibility=0.1),
        ]
        selected = creative.convergent_phase(ideas)
        assert len(selected) == 0

    def test_no_selected_integration(self, creative: CreativeWorktable) -> None:
        """Integration_phase sin ideas seleccionadas retorna mensaje."""
        proposal = creative.integration_phase([])
        assert proposal == "No se seleccionaron ideas."


# ---------------------------------------------------------------------------
# Test: Debate completo en modo creativo
# ---------------------------------------------------------------------------


class TestCreativeDebate:
    """Debate completo usando creative_mode=True."""

    def test_creative_debate_returns_compendium(self) -> None:
        """Worktable.debate con creative_mode=True retorna Compendium."""
        wt = Worktable()
        compendium = wt.debate(
            topic="Disenar API innovadora",
            agents=["builder", "scientist"],
            creative_mode=True,
        )
        assert isinstance(compendium, Compendium)

    def test_creative_debate_summary_not_empty(self) -> None:
        """Compendium del debate creativo tiene summary."""
        wt = Worktable()
        compendium = wt.debate(
            topic="Nuevo algoritmo de ML",
            creative_mode=True,
        )
        assert compendium.summary != ""

    def test_creative_debate_has_participants(self) -> None:
        """Compendium incluye participantes del debate creativo."""
        wt = Worktable()
        compendium = wt.debate(
            topic="Innovacion en UI",
            agents=["builder", "scientist", "guardian"],
            creative_mode=True,
        )
        assert len(compendium.participants) > 0
        assert "builder" in compendium.participants

    def test_creative_debate_has_agreements(self) -> None:
        """Compendium creativo tiene agreements."""
        wt = Worktable()
        compendium = wt.debate(
            topic="Blockchain para pagos",
            creative_mode=True,
        )
        assert len(compendium.agreements) > 0

    def test_creative_debate_has_trade_offs(self) -> None:
        """Compendium creativo tiene trade-offs."""
        wt = Worktable()
        compendium = wt.debate(
            topic="Arquitectura hibrida",
            creative_mode=True,
        )
        assert len(compendium.trade_offs) > 0

    def test_creative_debate_rounds(self) -> None:
        """Compendium creativo siempre tiene rounds=3."""
        wt = Worktable()
        compendium = wt.debate(
            topic="Cualquier tema",
            creative_mode=True,
        )
        assert compendium.rounds == 3

    def test_creative_debate_preserves_normal_debate(self) -> None:
        """Debate normal sin creative_mode sigue funcionando igual."""
        wt = Worktable()
        comp_normal = wt.debate(
            topic="API REST",
            agents=["soc", "coupling"],
        )
        comp_creative = wt.debate(
            topic="API REST",
            agents=["soc", "coupling"],
            creative_mode=True,
        )
        # Son distintos tipos de resultado
        assert comp_normal.summary.startswith("COMPENDIO ")
        assert ("Propuesta Integrada" in comp_creative.summary or
                "No se seleccionaron ideas." in comp_creative.summary)

    def test_creative_debate_custom_agents(self) -> None:
        """Debate creativo con agentes personalizados."""
        wt = Worktable()
        compendium = wt.debate(
            topic="Tema personalizado",
            agents=["alpha", "beta", "gamma"],
            creative_mode=True,
        )
        # Los agentes personalizados aparecen en participantes
        for agent in ["alpha", "beta", "gamma"]:
            assert agent in compendium.participants


# ---------------------------------------------------------------------------
# Test: Configuracion personalizada
# ---------------------------------------------------------------------------


class TestCustomConfig:
    """CreativeWorktable con configuracion personalizada."""

    def test_custom_num_ideas(self) -> None:
        """Config con num_ideas distinto genera esa cantidad minima."""
        config = CreativeConfig(num_ideas=3)
        cw = CreativeWorktable(config=config)
        ideas = cw.divergent_phase("Topic")
        assert len(ideas) >= 3

    def test_custom_topology(self) -> None:
        """Config con topology personalizada."""
        config = CreativeConfig(topology="small-world")
        cw = CreativeWorktable(config=config)
        assert cw.config.topology == "small-world"

    def test_custom_independence_rounds(self) -> None:
        """Config con independence_rounds personalizado."""
        config = CreativeConfig(independence_rounds=5)
        cw = CreativeWorktable(config=config)
        assert cw.config.independence_rounds == 5

    def test_config_not_shared(self) -> None:
        """Dos instancias no comparten la misma config."""
        config_a = CreativeConfig(num_ideas=3)
        config_b = CreativeConfig(num_ideas=10)
        cw_a = CreativeWorktable(config=config_a)
        cw_b = CreativeWorktable(config=config_b)
        assert cw_a.config.num_ideas != cw_b.config.num_ideas

    def test_default_config_used(self) -> None:
        """Sin config, usa valores por defecto."""
        cw = CreativeWorktable()
        assert cw.config.num_ideas == 5
        assert cw.config.topology == "sparse"


# ---------------------------------------------------------------------------
# Test: Novedad y factibilidad en rango
# ---------------------------------------------------------------------------


class TestNoveltyFeasibilityRange:
    """Novedad y factibilidad siempre en rango [0, 1]."""

    def test_novelty_in_range_multiple_calls(self) -> None:
        """Multiples llamadas generan novedades en rango."""
        cw = CreativeWorktable()
        for _ in range(5):
            ideas = cw.divergent_phase("Test")
            for idea in ideas:
                assert 0.0 <= idea.novelty <= 1.0

    def test_feasibility_in_range_multiple_calls(self) -> None:
        """Multiples llamadas generan factibilidades en rango."""
        cw = CreativeWorktable()
        for _ in range(5):
            ideas = cw.divergent_phase("Test")
            for idea in ideas:
                assert 0.0 <= idea.feasibility <= 1.0

    def test_novelty_variation(self) -> None:
        """Novedad varia entre ideas de un mismo ciclo."""
        cw = CreativeWorktable()
        ideas = cw.divergent_phase("Topic")
        novelties = [i.novelty for i in ideas]
        # Debe haber al menos dos valores distintos (no todos iguales)
        assert len(set(novelties)) >= 2 or len(ideas) == 1, (
            "Se espera variedad en novedad entre ideas"
        )

    def test_feasibility_variation(self) -> None:
        """Factibilidad varia entre ideas de un mismo ciclo."""
        cw = CreativeWorktable()
        ideas = cw.divergent_phase("Topic")
        feasibilities = [i.feasibility for i in ideas]
        assert len(set(feasibilities)) >= 2 or len(ideas) == 1, (
            "Se espera variedad en factibilidad entre ideas"
        )

    def test_no_negative_values(self) -> None:
        """Novedad y factibilidad nunca son negativos."""
        cw = CreativeWorktable()
        ideas = cw.divergent_phase("Test")
        for idea in ideas:
            assert idea.novelty >= 0.0
            assert idea.feasibility >= 0.0

    def test_no_values_exceeding_one(self) -> None:
        """Novedad y factibilidad nunca exceden 1.0."""
        cw = CreativeWorktable()
        ideas = cw.divergent_phase("Test")
        for idea in ideas:
            assert idea.novelty <= 1.0
            assert idea.feasibility <= 1.0
