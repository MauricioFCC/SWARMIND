"""Renderizado Markdown de agentes opencode nativos.

Submodulo interno del paquete :mod:`harness.aifactory.agent_factory`.

Extraido de forma mecanica desde ``agent_factory.py`` (regla AGR: archivos
< 500 lineas). Define ``_MarkdownRenderMixin`` con la composicion del
Markdown opencode nativo (frontmatter YAML + body de 5 capas). Los cuerpos
son identicos al original; solo cambia la ubicacion fisica del codigo.
"""

from __future__ import annotations

from .models import (
    DEFAULT_PERMISSIONS,
    DESCRIPTION_MAX_LEN,
    AgentTemplate,
    SpawnConfig,
)


class _MarkdownRenderMixin:
    """Renderiza el Markdown de un agente opencode nativo.

    Compone frontmatter YAML (name, description, mode, model, steps,
    permissions) y body de 5 capas: Identity+Mandate → Tools → Reasoning →
    Output Contract → Guardrails.
    """

    def render_markdown(
        self, template: AgentTemplate, spawn: SpawnConfig, task: str
    ) -> str:
        """Renderiza el Markdown del agente opencode nativo.

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
