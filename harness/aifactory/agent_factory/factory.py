"""OnDemandAgentFactory — orquestador del pipeline de generacion.

Submodulo interno del paquete :mod:`harness.aifactory.agent_factory`.

Extraido de forma mecanica desde ``agent_factory.py`` (regla AGR: archivos
< 500 lineas). Define ``OnDemandAgentFactory`` (core del pipeline) que
hereda ``_MarkdownRenderMixin`` para la composicion del Markdown. Los
cuerpos son identicos al original; solo cambia la ubicacion fisica del
codigo.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from .models import (
    BUDGET_DEFAULT,
    UUID_SUFFIX_LEN,
    AgentTemplate,
    GeneratedAgent,
    SpawnConfig,
)
from .recommender import AgentRecommender
from .registry import AgentTemplateRegistry
from .render_mixin import _MarkdownRenderMixin


class OnDemandAgentFactory(_MarkdownRenderMixin):
    """Genera definiciones de agentes opencode nativas on-demand.

    Orquesta el pipeline adaptado del paper: QueryAnalysis (recommender)
    → PersonaCraft (composicion de persona del template) → AgentFactory
    (SpawnConfig + render Markdown). La ejecucion y agregacion quedan
    para el consumidor, que carga el .md generado en opencode.
    """

    def __init__(
        self,
        registry: AgentTemplateRegistry | None = None,
        recommender: AgentRecommender | None = None,
    ) -> None:
        """Inicializa el factory con registry y recommender.

        Args:
            registry: Catalogo de plantillas. Default: agent_templates.yaml.
            recommender: Motor de recomendacion. Default: AgentRecommender.
        """
        self._registry = registry or AgentTemplateRegistry()
        self._recommender = recommender or AgentRecommender()

    def generate(
        self,
        task: str,
        *,
        registry: AgentTemplateRegistry | None = None,
        agent_name: str | None = None,
        model: str | None = None,
        budget: int | None = None,
        parent_agent_id: str | None = None,
    ) -> GeneratedAgent:
        """Genera un agente opencode nativo para la tarea dada.

        Pipeline: recomienda template (QueryAnalysis), compone la persona
        (PersonaCraft), construye SpawnConfig (AgentFactory) y renderiza
        el Markdown con frontmatter YAML y body de 5 capas.

        Args:
            task: Descripcion de la tarea del usuario.
            registry: Registry a usar (default: el del factory).
            agent_name: Nombre del agente. Default: '<template_id>-<uuid6>'.
            model: Modelo LLM opcional.
            budget: Presupuesto de tokens. Default: BUDGET_DEFAULT.
            parent_agent_id: Agente padre opcional.

        Returns:
            GeneratedAgent con la definicion Markdown completa.

        Raises:
            ValueError: Si task esta vacia o el spawn no es valido.
        """
        if not task or not task.strip():
            raise ValueError(
                "WHAT=task vacia en generate "
                "WHY=se requiere una descripcion de tarea no vacia "
                "WHERE=OnDemandAgentFactory.generate"
            )
        active_registry = registry or self._registry
        template = self._recommender.recommend(task, active_registry)
        spawn = self._build_spawn_config(
            template,
            agent_name=agent_name,
            model=model,
            budget=budget,
            parent_agent_id=parent_agent_id,
        )
        markdown = self.render_markdown(template, spawn, task)
        return GeneratedAgent(
            spawn_config=spawn,
            markdown=markdown,
            recommended_by=template.template_id,
            generated_at=datetime.now(UTC).isoformat(),
        )

    def _build_spawn_config(
        self,
        template: AgentTemplate,
        *,
        agent_name: str | None,
        model: str | None,
        budget: int | None,
        parent_agent_id: str | None,
    ) -> SpawnConfig:
        """Construye el SpawnConfig (capa AgentFactory del pipeline).

        Args:
            template: Template base recomendado.
            agent_name: Nombre custom o None para generar con uuid corto.
            model: Modelo LLM opcional.
            budget: Presupuesto o None para BUDGET_DEFAULT.
            parent_agent_id: Agente padre opcional.

        Returns:
            SpawnConfig validado.
        """
        resolved_name = agent_name or (
            f"{template.template_id}-{uuid.uuid4().hex[:UUID_SUFFIX_LEN]}"
        )
        resolved_budget = budget if budget is not None else BUDGET_DEFAULT
        return SpawnConfig(
            template_id=template.template_id,
            agent_name=resolved_name,
            model=model,
            max_iterations=template.max_iterations,
            budget=resolved_budget,
            tool_overrides=template.required_tools or None,
            parent_agent_id=parent_agent_id,
        )
