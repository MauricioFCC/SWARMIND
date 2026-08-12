"""Modelos de datos del On-Demand Agent Factory.

Submodulo interno del paquete :mod:`harness.aifactory.agent_factory`.

Extraido de forma mecanica desde ``agent_factory.py`` (regla AGR: archivos
< 500 lineas). Define las constantes nombradas y las dataclasses inmutables
``AgentTemplate``, ``SpawnConfig`` y ``GeneratedAgent``. Los cuerpos son
identicos al original; solo cambia la ubicacion fisica del codigo.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Constantes nombradas (sin magic numbers)
# ---------------------------------------------------------------------------

MAX_ITERATIONS_DEFAULT = 8
BUDGET_DEFAULT = 2048
FALLBACK_TEMPLATE_ID = "research-synthesis"
UUID_SUFFIX_LEN = 6
DESCRIPTION_MAX_LEN = 200
DEFAULT_COST_ESTIMATE = "medium"
DEFAULT_PERMISSIONS: tuple[str, ...] = ("read", "edit", "bash(git *)")


# ===========================================================================
# Dataclasses (inmutables, frozen=True)
# ===========================================================================


@dataclass(frozen=True)
class AgentTemplate:
    """Plantilla base de un agente opencode.

    Define la persona (mandato), estilo de razonamiento, contrato de
    salida, herramientas requeridas y guardrails. Es la materia prima
    de la capa PersonaCraft del pipeline.

    Args:
        template_id: Identificador unico del template (ej: 'programming-agent').
        name: Nombre legible del agente.
        domain_tags: Dominios/skills que cubre el template.
        description: Descripcion de una linea del proposito.
        required_tools: Herramientas opencode que necesita el agente.
        composable: Si es combinable con otros agentes en un swarm.
        max_iterations: Maximo de iteraciones del agente.
        cost_estimate: Costo estimado ('low', 'medium', 'high').
        role_mandate: Mandato/persona del agente (seccion Mandate).
        reasoning_style: Protocolo de razonamiento del agente.
        output_contract: Contrato de salida esperado.
        guardrails: Restricciones de comportamiento del agente.
    """

    template_id: str
    name: str
    domain_tags: frozenset[str] = frozenset()
    description: str = ""
    required_tools: frozenset[str] = frozenset()
    composable: bool = True
    max_iterations: int = MAX_ITERATIONS_DEFAULT
    cost_estimate: str = DEFAULT_COST_ESTIMATE
    role_mandate: str = ""
    reasoning_style: str = ""
    output_contract: str = ""
    guardrails: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Valida campos obligatorios y rangos de la plantilla.

        Raises:
            ValueError: Si template_id/name estan vacios o max_iterations < 1.
        """
        if not self.template_id or not self.template_id.strip():
            raise ValueError(
                "WHAT=template_id vacio en AgentTemplate "
                "WHY=se requiere un identificador unico no vacio "
                "WHERE=AgentTemplate.__post_init__"
            )
        if not self.name or not self.name.strip():
            raise ValueError(
                "WHAT=name vacio en AgentTemplate "
                "WHY=se requiere un nombre legible no vacio "
                "WHERE=AgentTemplate.__post_init__"
            )
        if self.max_iterations < 1:
            raise ValueError(
                f"WHAT=max_iterations={self.max_iterations} invalido "
                f"WHY=debe ser >= 1 (default {MAX_ITERATIONS_DEFAULT}) "
                "WHERE=AgentTemplate.__post_init__"
            )


@dataclass(frozen=True)
class SpawnConfig:
    """Configuracion de spawn de un agente generado.

    Args:
        template_id: Template base que origina el agente.
        agent_name: Nombre unico del agente generado.
        model: Modelo LLM opcional (None = default del harness).
        max_iterations: Maximo de iteraciones del agente.
        budget: Presupuesto de tokens del agente.
        tool_overrides: Override de herramientas (None = usa las del template).
        parent_agent_id: Agente padre opcional (composicion de swarm).
    """

    template_id: str
    agent_name: str
    model: str | None = None
    max_iterations: int = MAX_ITERATIONS_DEFAULT
    budget: int = BUDGET_DEFAULT
    tool_overrides: frozenset[str] | None = None
    parent_agent_id: str | None = None

    def __post_init__(self) -> None:
        """Valida los campos obligatorios y rangos del spawn.

        Raises:
            ValueError: Si template_id/agent_name vacios o rangos invalidos.
        """
        if not self.template_id or not self.template_id.strip():
            raise ValueError(
                "WHAT=template_id vacio en SpawnConfig "
                "WHY=se requiere un template base "
                "WHERE=SpawnConfig.__post_init__"
            )
        if not self.agent_name or not self.agent_name.strip():
            raise ValueError(
                "WHAT=agent_name vacio en SpawnConfig "
                "WHY=se requiere un nombre de agente no vacio "
                "WHERE=SpawnConfig.__post_init__"
            )
        if self.max_iterations < 1:
            raise ValueError(
                f"WHAT=max_iterations={self.max_iterations} invalido "
                f"WHY=debe ser >= 1 (default {MAX_ITERATIONS_DEFAULT}) "
                "WHERE=SpawnConfig.__post_init__"
            )
        if self.budget < 1:
            raise ValueError(
                f"WHAT=budget={self.budget} invalido "
                f"WHY=debe ser >= 1 (default {BUDGET_DEFAULT}) "
                "WHERE=SpawnConfig.__post_init__"
            )


@dataclass(frozen=True)
class GeneratedAgent:
    """Definicion final de un agente generado on-demand.

    Args:
        spawn_config: Configuracion de spawn utilizada.
        markdown: Markdown opencode nativo (frontmatter YAML + body 5 capas).
        recommended_by: template_id que origino la generacion.
        generated_at: Timestamp ISO-8601 UTC de generacion.
    """

    spawn_config: SpawnConfig
    markdown: str
    recommended_by: str
    generated_at: str

    def __post_init__(self) -> None:
        """Valida que la definicion generada no este vacia.

        Raises:
            ValueError: Si markdown/recommended_by/generated_at vacios.
        """
        if not self.markdown.strip():
            raise ValueError(
                "WHAT=markdown vacio en GeneratedAgent "
                "WHY=se requiere la definicion renderizada del agente "
                "WHERE=GeneratedAgent.__post_init__"
            )
        if not self.recommended_by or not self.recommended_by.strip():
            raise ValueError(
                "WHAT=recommended_by vacio en GeneratedAgent "
                "WHY=se requiere el template origen "
                "WHERE=GeneratedAgent.__post_init__"
            )
        if not self.generated_at or not self.generated_at.strip():
            raise ValueError(
                "WHAT=generated_at vacio en GeneratedAgent "
                "WHY=se requiere el timestamp de generacion "
                "WHERE=GeneratedAgent.__post_init__"
            )
