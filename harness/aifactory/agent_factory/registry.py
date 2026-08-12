"""Catalogo YAML de plantillas del On-Demand Agent Factory.

Submodulo interno del paquete :mod:`harness.aifactory.agent_factory`.

Extraido de forma mecanica desde ``agent_factory.py`` (regla AGR: archivos
< 500 lineas). Define ``AgentTemplateRegistry``, el registro que carga y
valida el catalogo ``agent_templates.yaml``. Los cuerpos son identicos al
original; solo cambia la ubicacion fisica del codigo.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import (
    DEFAULT_COST_ESTIMATE,
    MAX_ITERATIONS_DEFAULT,
    AgentTemplate,
)


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
            return Path(__file__).parent.parent / "agent_templates.yaml"
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
