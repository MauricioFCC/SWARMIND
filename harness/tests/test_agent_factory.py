"""Tests TDD para agent_factory — On-Demand Agent Factory + recommendation engine.

Implementa el patron del paper arXiv 2604.27882 (Building Persona-Based
Agents On Demand) adaptado al harness SWARMIND. Verifica:
- Carga del catalogo YAML con 8 plantillas base.
- Registry: templates/get/domains y rutas personalizadas.
- Recommender: matcheo por keywords con fallback documentado.
- OnDemandAgentFactory: generacion de agentes opencode nativos
  (Markdown con frontmatter YAML y body de 5 capas).
- Dataclasses frozen con validacion (sin magic numbers).
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest

from harness.aifactory.agent_factory import (
    BUDGET_DEFAULT,
    MAX_ITERATIONS_DEFAULT,
    AgentRecommender,
    AgentTemplate,
    AgentTemplateRegistry,
    GeneratedAgent,
    OnDemandAgentFactory,
    SpawnConfig,
)

DEFAULT_CATALOG = (
    Path(__file__).resolve().parent.parent / "aifactory" / "agent_templates.yaml"
)

EXPECTED_TEMPLATE_IDS = frozenset({
    "programming-agent",
    "science-review",
    "legal-review",
    "data-analysis",
    "security-audit",
    "documentation",
    "frontend-ui",
    "research-synthesis",
})


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def registry() -> AgentTemplateRegistry:
    """Registry con el catalogo por defecto (agent_templates.yaml)."""
    return AgentTemplateRegistry()


@pytest.fixture()
def recommender() -> AgentRecommender:
    """Recommender por defecto con fallback research-synthesis."""
    return AgentRecommender()


@pytest.fixture()
def factory() -> OnDemandAgentFactory:
    """Factory on-demand con registry y recommender por defecto."""
    return OnDemandAgentFactory()


# ===========================================================================
# AgentTemplateRegistry
# ===========================================================================


class TestAgentTemplateRegistry:
    """Tests de carga y consulta del catalogo de plantillas."""

    def test_loads_eight_templates(self, registry: AgentTemplateRegistry) -> None:
        """El registro carga exactamente las 8 plantillas base del catalogo."""
        templates = registry.templates()
        assert len(templates) == 8
        assert {t.template_id for t in templates} == EXPECTED_TEMPLATE_IDS

    def test_templates_is_tuple(self, registry: AgentTemplateRegistry) -> None:
        """templates() retorna una tupla inmutable."""
        assert isinstance(registry.templates(), tuple)

    def test_get_known_template(self, registry: AgentTemplateRegistry) -> None:
        """get('programming-agent') devuelve la plantilla correcta."""
        template = registry.get("programming-agent")
        assert template is not None
        assert template.name == "Programming Agent"
        assert "programming" in template.domain_tags
        assert template.composable is True
        assert template.max_iterations == MAX_ITERATIONS_DEFAULT

    def test_get_unknown_returns_none(self, registry: AgentTemplateRegistry) -> None:
        """get() con id inexistente devuelve None (no excepcion)."""
        assert registry.get("no-existe") is None

    def test_domains(self, registry: AgentTemplateRegistry) -> None:
        """domains() retorna frozenset con la union de todos los dominios."""
        domains = registry.domains()
        assert isinstance(domains, frozenset)
        assert {
            "programming",
            "coding",
            "legal",
            "jurisprudencia",
            "ciencia",
            "papers",
        } <= domains

    def test_custom_path(self) -> None:
        """Registry acepta una ruta explicita al catalogo YAML."""
        custom = AgentTemplateRegistry(templates_path=DEFAULT_CATALOG)
        assert len(custom.templates()) == 8

    def test_missing_path_raises(self) -> None:
        """Registry con ruta inexistente lanza FileNotFoundError claro."""
        missing = Path(__file__).parent / "no_existe_plantillas.yaml"
        with pytest.raises(FileNotFoundError):
            AgentTemplateRegistry(templates_path=missing)


# ===========================================================================
# AgentRecommender
# ===========================================================================


class TestAgentRecommender:
    """Tests del motor de recomendacion por keywords."""

    def test_programming_task(
        self, recommender: AgentRecommender, registry: AgentTemplateRegistry
    ) -> None:
        """Tarea de programacion recomienda programming-agent."""
        template = recommender.recommend(
            "Implementar codigo de programming con swe y refactor", registry
        )
        assert template.template_id == "programming-agent"

    def test_legal_task(
        self, recommender: AgentRecommender, registry: AgentTemplateRegistry
    ) -> None:
        """Tarea legal recomienda legal-review."""
        template = recommender.recommend(
            "Revisa la jurisprudencia y las normas del caso", registry
        )
        assert template.template_id == "legal-review"

    def test_science_task(
        self, recommender: AgentRecommender, registry: AgentTemplateRegistry
    ) -> None:
        """Tarea de ciencia/citas recomienda science-review."""
        template = recommender.recommend(
            "Busca papers cientificos y citas relevantes", registry
        )
        assert template.template_id == "science-review"

    def test_fallback_no_match(
        self, recommender: AgentRecommender, registry: AgentTemplateRegistry
    ) -> None:
        """Tarea sin coincidencias cae en research-synthesis (fallback)."""
        template = recommender.recommend("xyzzy quux frobnicate", registry)
        assert template.template_id == "research-synthesis"

    def test_fallback_empty_task(
        self, recommender: AgentRecommender, registry: AgentTemplateRegistry
    ) -> None:
        """Tarea vacia tambien usa el fallback documentado."""
        template = recommender.recommend("   ", registry)
        assert template.template_id == "research-synthesis"

    def test_score_helper(
        self, recommender: AgentRecommender, registry: AgentTemplateRegistry
    ) -> None:
        """_score cuenta tokens de la tarea presentes en las keywords."""
        programming = registry.get("programming-agent")
        assert programming is not None
        assert recommender._score({"programming", "swe"}, programming) >= 2


# ===========================================================================
# Dataclasses frozen y validacion
# ===========================================================================


class TestDataclasses:
    """Tests de inmutabilidad y validacion de las dataclasses."""

    def test_template_defaults(self) -> None:
        """AgentTemplate con defaults sensatos (sin magic numbers)."""
        template = AgentTemplate(template_id="t1", name="T1")
        assert template.max_iterations == MAX_ITERATIONS_DEFAULT
        assert template.max_iterations == 8
        assert template.domain_tags == frozenset()
        assert template.guardrails == ()
        assert template.composable is True
        assert template.cost_estimate == "medium"

    def test_spawn_config_defaults(self) -> None:
        """SpawnConfig usa BUDGET_DEFAULT y MAX_ITERATIONS_DEFAULT."""
        spawn = SpawnConfig(template_id="t1", agent_name="a")
        assert spawn.budget == BUDGET_DEFAULT
        assert spawn.budget == 2048
        assert spawn.model is None
        assert spawn.tool_overrides is None
        assert spawn.parent_agent_id is None

    def test_spawn_config_invalid_iterations(self) -> None:
        """max_iterations < 1 lanza ValueError accionable."""
        with pytest.raises(ValueError):
            SpawnConfig(template_id="t1", agent_name="a", max_iterations=0)
        with pytest.raises(ValueError):
            SpawnConfig(template_id="t1", agent_name="a", max_iterations=-3)

    def test_spawn_config_invalid_budget(self) -> None:
        """budget < 1 lanza ValueError accionable."""
        with pytest.raises(ValueError):
            SpawnConfig(template_id="t1", agent_name="a", budget=0)

    def test_spawn_config_empty_agent_name(self) -> None:
        """agent_name vacio o solo espacios lanza ValueError."""
        with pytest.raises(ValueError):
            SpawnConfig(template_id="t1", agent_name="")
        with pytest.raises(ValueError):
            SpawnConfig(template_id="t1", agent_name="   ")

    def test_dataclasses_are_frozen(self) -> None:
        """Las tres dataclasses son frozen=True (inmutables)."""
        assert dataclasses.is_dataclass(AgentTemplate)
        assert dataclasses.is_dataclass(SpawnConfig)
        assert dataclasses.is_dataclass(GeneratedAgent)

    def test_frozen_instances_reject_assignment(self) -> None:
        """Asignar a una instancia frozen lanza FrozenInstanceError."""
        template = AgentTemplate(template_id="t1", name="T1")
        spawn = SpawnConfig(template_id="t1", agent_name="a")
        agent = GeneratedAgent(
            spawn_config=spawn,
            markdown="---\n",
            recommended_by="t1",
            generated_at="2026-08-08T00:00:00",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            template.max_iterations = 99  # type: ignore[misc]
        with pytest.raises(dataclasses.FrozenInstanceError):
            spawn.agent_name = "otro"  # type: ignore[misc]
        with pytest.raises(dataclasses.FrozenInstanceError):
            agent.markdown = "x"  # type: ignore[misc]


# ===========================================================================
# OnDemandAgentFactory
# ===========================================================================


class TestOnDemandAgentFactory:
    """Tests de generacion de agentes opencode nativos."""

    def test_generate_markdown_structure(
        self, factory: OnDemandAgentFactory, registry: AgentTemplateRegistry
    ) -> None:
        """El Markdown contiene frontmatter YAML y secciones del body."""
        result = factory.generate(
            "Implementar codigo de programming",
            registry=registry,
            agent_name="prog-agent",
        )
        assert isinstance(result, GeneratedAgent)
        md = result.markdown
        assert md.startswith("---")
        assert "name: prog-agent" in md
        assert "mode: subagent" in md
        assert "steps:" in md
        assert "permissions:" in md
        assert "## Mandate" in md
        assert "## Reasoning" in md
        assert "## Output Contract" in md
        assert "## Guardrails" in md
        assert "## Tools" in md

    def test_generate_custom_agent_name(
        self, factory: OnDemandAgentFactory, registry: AgentTemplateRegistry
    ) -> None:
        """agent_name custom se propaga al SpawnConfig y al Markdown."""
        result = factory.generate(
            "tarea de programming", agent_name="mi-agente", registry=registry
        )
        assert result.spawn_config.agent_name == "mi-agente"
        assert "name: mi-agente" in result.markdown

    def test_generate_custom_budget(
        self, factory: OnDemandAgentFactory, registry: AgentTemplateRegistry
    ) -> None:
        """budget custom se propaga al SpawnConfig."""
        result = factory.generate(
            "tarea de programming", budget=4096, registry=registry
        )
        assert result.spawn_config.budget == 4096

    def test_generate_default_budget(
        self, factory: OnDemandAgentFactory, registry: AgentTemplateRegistry
    ) -> None:
        """Sin budget, se usa BUDGET_DEFAULT."""
        result = factory.generate("tarea de programming", registry=registry)
        assert result.spawn_config.budget == BUDGET_DEFAULT

    def test_generate_default_agent_name_uuid(
        self, factory: OnDemandAgentFactory, registry: AgentTemplateRegistry
    ) -> None:
        """Sin agent_name, se genera '<template_id>-<uuid6>'."""
        result = factory.generate(
            "Implementar codigo de programming", registry=registry
        )
        pattern = re.compile(r"^programming-agent-[0-9a-f]{6}$")
        assert pattern.fullmatch(result.spawn_config.agent_name) is not None

    def test_generate_model_passed(
        self, factory: OnDemandAgentFactory, registry: AgentTemplateRegistry
    ) -> None:
        """model custom aparece en SpawnConfig y en el frontmatter."""
        result = factory.generate(
            "tarea de programming", model="gpt-4o-mini", registry=registry
        )
        assert result.spawn_config.model == "gpt-4o-mini"
        assert "model: gpt-4o-mini" in result.markdown

    def test_generate_max_iterations_from_template(
        self, factory: OnDemandAgentFactory, registry: AgentTemplateRegistry
    ) -> None:
        """max_iterations hereda del template recomendado."""
        result = factory.generate("tarea de programming", registry=registry)
        assert result.spawn_config.max_iterations == MAX_ITERATIONS_DEFAULT

    def test_generate_recommended_by(
        self, factory: OnDemandAgentFactory, registry: AgentTemplateRegistry
    ) -> None:
        """recommended_by documenta el template origen y generated_at no vacio."""
        result = factory.generate("tarea de programming", registry=registry)
        assert result.recommended_by == "programming-agent"
        assert result.generated_at

    def test_generate_empty_task_raises(
        self, factory: OnDemandAgentFactory
    ) -> None:
        """generate con tarea vacia lanza ValueError accionable."""
        with pytest.raises(ValueError):
            factory.generate("   ")
