"""On-Demand Agent Factory — generacion de agentes opencode nativos (ADR-0041 H4).

Modulo independiente del AIFactory de 7 capas (harness/aifactory/factory.py).
Implementa el pipeline del paper arXiv 2604.27882 (Building Persona-Based
Agents On Demand, Arbore et al., 2026) adaptado a SWARMIND:

    QueryAnalysis   -> AgentRecommender.recommend(task, registry)
    PersonaCraft    -> composicion de role_mandate + razonamiento +
                       contrato de salida + guardrails del template
    AgentFactory    -> SpawnConfig + render del Markdown opencode nativo
    Ejecucion       -> el consumidor carga el .md generado en opencode
    Agregacion      -> GeneratedAgent encapsula la definicion completa

El catalogo de plantillas vive en agent_templates.yaml junto a este modulo
(8 plantillas base) y se carga con PyYAML via pathlib.

Exports:
    AgentTemplate          -> Dataclass frozen de una plantilla.
    SpawnConfig            -> Configuracion de spawn del agente.
    GeneratedAgent         -> Definicion final generada on-demand.
    AgentTemplateRegistry  -> Catalogo YAML de plantillas.
    AgentRecommender       -> Motor de recomendacion por keywords.
    OnDemandAgentFactory   -> Orquestador del pipeline de generacion.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

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


# ===========================================================================
# Registry — catalogo YAML de plantillas
# ===========================================================================


class AgentTemplateRegistry:
    """Catalogo de plantillas de agentes cargado desde un archivo YAML.

    Usa pathlib para resolver rutas y PyYAML (yaml.safe_load) para
    parsear el catalogo. Si no se indica ruta, usa agent_templates.yaml
    junto a este modulo.
    """

    def __init__(self, templates_path: str | Path | None = None) -> None:
        """Inicializa el registro cargando las plantillas desde YAML.

        Args:
            templates_path: Ruta al catalogo YAML. Si es None, usa
                agent_templates.yaml junto al modulo.

        Raises:
            ImportError: Si PyYAML no esta instalado.
            FileNotFoundError: Si el archivo no existe.
            ValueError: Si el YAML es invalido o no trae plantillas.
        """
        self._templates: tuple[AgentTemplate, ...] = self._load(templates_path)

    @staticmethod
    def _resolve_path(templates_path: str | Path | None) -> Path:
        """Resuelve la ruta del catalogo de plantillas.

        Args:
            templates_path: Ruta explicita o None.

        Returns:
            Path del catalogo YAML.

        Raises:
            ValueError: Si la ruta apunta a un directorio.
        """
        if templates_path is None:
            return Path(__file__).parent / "agent_templates.yaml"
        path = Path(templates_path)
        if path.is_dir():
            raise ValueError(
                f"WHAT=la ruta '{path}' es un directorio "
                "WHY=se requiere un archivo YAML de plantillas "
                "WHERE=AgentTemplateRegistry._resolve_path"
            )
        return path

    def _load(self, templates_path: str | Path | None) -> tuple[AgentTemplate, ...]:
        """Carga y valida el catalogo de plantillas YAML.

        Args:
            templates_path: Ruta al YAML o None para usar el default.

        Returns:
            Tupla ordenada de AgentTemplate.

        Raises:
            ImportError: Si PyYAML no esta instalado.
            FileNotFoundError: Si el archivo no existe.
            ValueError: Si el YAML es invalido o no define plantillas.
        """
        path = self._resolve_path(templates_path)
        try:
            import yaml
        except ImportError as exc:
            raise ImportError(
                "WHAT=no se pudo importar 'yaml' (PyYAML) "
                "WHY=el registro de plantillas requiere PyYAML para leer "
                f"'{path.name}' "
                "WHERE=AgentTemplateRegistry._load"
            ) from exc
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"WHAT=no se encontro el catalogo de plantillas '{path}' "
                "WHY=la ruta no existe o el paquete esta incompleto "
                "WHERE=AgentTemplateRegistry._load"
            ) from exc
        except yaml.YAMLError as exc:
            raise ValueError(
                f"WHAT=el catalogo '{path.name}' no es YAML valido "
                f"WHY={exc} "
                "WHERE=AgentTemplateRegistry._load"
            ) from exc

        items = (data or {}).get("templates", [])
        if not isinstance(items, list) or not items:
            raise ValueError(
                f"WHAT=el catalogo '{path.name}' no define plantillas "
                "WHY=se esperaba una lista 'templates' no vacia "
                "WHERE=AgentTemplateRegistry._load"
            )
        return tuple(self._parse_item(item) for item in items)

    @staticmethod
    def _parse_item(item: dict[str, Any]) -> AgentTemplate:
        """Convierte un dict del YAML en AgentTemplate validado.

        Args:
            item: Entrada individual del catalogo YAML.

        Returns:
            AgentTemplate con sets congelados (frozenset/tuple).
        """
        return AgentTemplate(
            template_id=str(item.get("template_id", "")),
            name=str(item.get("name", "")),
            domain_tags=frozenset(str(t) for t in item.get("domain_tags", [])),
            description=str(item.get("description", "")),
            required_tools=frozenset(
                str(t) for t in item.get("required_tools", [])
            ),
            composable=bool(item.get("composable", True)),
            max_iterations=int(
                item.get("max_iterations", MAX_ITERATIONS_DEFAULT)
            ),
            cost_estimate=str(item.get("cost_estimate", DEFAULT_COST_ESTIMATE)),
            role_mandate=str(item.get("role_mandate", "")),
            reasoning_style=str(item.get("reasoning_style", "")),
            output_contract=str(item.get("output_contract", "")),
            guardrails=tuple(str(g) for g in item.get("guardrails", [])),
        )

    def templates(self) -> tuple[AgentTemplate, ...]:
        """Retorna las plantillas en orden de registro.

        Returns:
            Tupla inmutable de AgentTemplate.
        """
        return self._templates

    def get(self, template_id: str) -> AgentTemplate | None:
        """Busca una plantilla por su identificador.

        Args:
            template_id: Identificador unico del template.

        Returns:
            AgentTemplate si existe, None si no.
        """
        for template in self._templates:
            if template.template_id == template_id:
                return template
        return None

    def domains(self) -> frozenset[str]:
        """Retorna la union de todos los domain_tags del catalogo.

        Returns:
            frozenset con todos los dominios cubiertos.
        """
        all_domains: set[str] = set()
        for template in self._templates:
            all_domains.update(template.domain_tags)
        return frozenset(all_domains)


# ===========================================================================
# Recommender — QueryAnalysis (matcheo por keywords)
# ===========================================================================


class AgentRecommender:
    """Motor de recomendacion de plantillas por keywords (QueryAnalysis).

    Tokeniza la tarea en minusculas y puntua cada template contando los
    tokens de la tarea presentes en sus keywords (domain_tags + nombre +
    descripcion). Gana el de mayor score; en empate, el primero en orden
    de registro. Sin coincidencias, usa el template de fallback
    (research-synthesis) o, si no existe, el primero del catalogo.
    """

    def __init__(self, fallback_template_id: str = FALLBACK_TEMPLATE_ID) -> None:
        """Inicializa el recommender con template de fallback.

        Args:
            fallback_template_id: Template usado sin coincidencias.
                Default: 'research-synthesis' (sintesis generalista).
        """
        self._fallback_template_id = fallback_template_id

    def recommend(
        self, task: str, registry: AgentTemplateRegistry
    ) -> AgentTemplate:
        """Recomienda el template mas similar a la tarea.

        Args:
            task: Descripcion de la tarea del usuario.
            registry: Catalogo de plantillas a consultar.

        Returns:
            AgentTemplate recomendado (o fallback si no hay coincidencias).
        """
        tokens = self._tokenize(task)
        best_template: AgentTemplate | None = None
        best_score = 0
        for template in registry.templates():
            score = self._score(tokens, template)
            if score > best_score:
                best_template = template
                best_score = score
        if best_template is not None:
            return best_template
        fallback = registry.get(self._fallback_template_id)
        if fallback is not None:
            return fallback
        return registry.templates()[0]

    @staticmethod
    def _tokenize(task: str) -> set[str]:
        """Tokeniza la tarea en palabras en minusculas.

        Args:
            task: Texto de la tarea.

        Returns:
            Conjunto de tokens sin vacios.
        """
        return {token for token in task.lower().split() if token}

    @staticmethod
    def _template_keywords(template: AgentTemplate) -> set[str]:
        """Construye el set de keywords de un template.

        Args:
            template: Plantilla a analizar.

        Returns:
            Conjunto de keywords (domain_tags + nombre + descripcion).
        """
        keywords: set[str] = set(template.domain_tags)
        keywords.update(template.name.lower().split())
        keywords.update(template.description.lower().split())
        return keywords

    def _score(self, task_tokens: set[str], template: AgentTemplate) -> int:
        """Puntua un template contra los tokens de la tarea.

        Args:
            task_tokens: Tokens normalizados de la tarea.
            template: Plantilla a puntuar.

        Returns:
            Numero de tokens de la tarea presentes en las keywords.
        """
        keywords = self._template_keywords(template)
        return sum(1 for token in task_tokens if token in keywords)


# ===========================================================================
# OnDemandAgentFactory — orquestador del pipeline
# ===========================================================================


class OnDemandAgentFactory:
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

    def render_markdown(
        self, template: AgentTemplate, spawn: SpawnConfig, task: str
    ) -> str:
        """Renderiza el Markdown del agente opencode nativo.

        Compone frontmatter YAML (name, description, mode, model, steps,
        permissions) y body de 5 capas: Identity+Mandate → Tools →
        Reasoning → Output Contract → Guardrails.

        Args:
            template: Plantilla base del agente.
            spawn: Configuracion de spawn del agente.
            task: Tarea original (para description en 1 linea).

        Returns:
            String Markdown completo del agente.
        """
        description = self._one_line_description(task)
        frontmatter = self._render_frontmatter(spawn, description)
        body = self._render_body(template, spawn)
        return f"{frontmatter}\n\n{body}\n"

    @staticmethod
    def _one_line_description(task: str) -> str:
        """Normaliza la tarea a una descripcion de una linea.

        Args:
            task: Texto de la tarea.

        Returns:
            Descripcion truncada a DESCRIPTION_MAX_LEN caracteres.
        """
        normalized = " ".join(task.split())
        if len(normalized) > DESCRIPTION_MAX_LEN:
            return f"{normalized[:DESCRIPTION_MAX_LEN - 1]}..."
        return normalized

    def _render_frontmatter(self, spawn: SpawnConfig, description: str) -> str:
        """Renderiza el frontmatter YAML del agente.

        Args:
            spawn: Configuracion del spawn.
            description: Descripcion en una linea (escapada para YAML).

        Returns:
            Bloque YAML delimitado por lineas '---'.
        """
        escaped_desc = description.replace('"', '\\"')
        lines = [
            "---",
            f"name: {spawn.agent_name}",
            f'description: "{escaped_desc}"',
            "mode: subagent",
        ]
        if spawn.model:
            lines.append(f"model: {spawn.model}")
        lines.append(f"steps: {spawn.max_iterations}")
        lines.append("permissions:")
        lines.append("  allow:")
        lines.extend(f"    - {permission}" for permission in DEFAULT_PERMISSIONS)
        lines.append("---")
        return "\n".join(lines)

    def _render_body(self, template: AgentTemplate, spawn: SpawnConfig) -> str:
        """Renderiza el body del agente (patron 5-capas del paper).

        Args:
            template: Plantilla con persona/razonamiento/contrato/guardrails.
            spawn: Configuracion del spawn.

        Returns:
            String con las secciones del prompt del agente.
        """
        tools = sorted(template.required_tools) if template.required_tools else ["read"]
        sections = [
            f"# {spawn.agent_name}",
            "",
            "## Mandate",
            template.role_mandate,
            "",
            "## Tools",
        ]
        sections.extend(f"- {tool}" for tool in tools)
        sections.extend(
            [
                "",
                "## Reasoning",
                template.reasoning_style,
                "",
                "## Output Contract",
                template.output_contract,
                "",
                "## Guardrails",
            ]
        )
        sections.extend(f"- {guardrail}" for guardrail in template.guardrails)
        return "\n".join(sections)


__all__ = [
    "BUDGET_DEFAULT",
    "FALLBACK_TEMPLATE_ID",
    "MAX_ITERATIONS_DEFAULT",
    "AgentRecommender",
    "AgentTemplate",
    "AgentTemplateRegistry",
    "GeneratedAgent",
    "OnDemandAgentFactory",
    "SpawnConfig",
]
