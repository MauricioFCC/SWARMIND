"""
IDEAdapter — Integracion de AGENTIC con multiples IDEs y harness.

Soporta: Claude Code, Codex CLI, Cursor, OpenCode, Gemini CLI.
Basado en el patron de ECC que soporta 7+ harnesses diferentes.

Cada IDE tiene su propio formato de configuracion:
- Claude Code: .claude/settings.json + AGENTS.md
- Codex CLI: .codex/config.toml + AGENTS.md
- Cursor: .cursorrules
- OpenCode: .opencode/ (nativo AGENTIC)
- Gemini CLI: .gemini/instructions.md
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class IDESupport:
    """Describe el soporte de configuracion para un IDE especifico.

    Args:
        name: Nombre comercial del IDE (ej: "Claude Code").
        config_file: Ruta relativa al archivo de configuracion del IDE
            desde la raiz del proyecto.
        agents_format: Formato o ruta donde el IDE espera los agentes.
        skills_path: Ruta relativa donde el IDE almacena sus skills/prompts.
    """
    name: str
    config_file: str
    agents_format: str
    skills_path: str


# Lista canonica de IDEs soportados (SSOT).
SUPPORTED_IDES: List[IDESupport] = [
    IDESupport("Claude Code", ".claude/settings.json", "AGENTS.md", ".claude/skills/"),
    IDESupport("Codex CLI", ".codex/config.toml", "AGENTS.md", ".codex/prompts/"),
    IDESupport("Cursor", ".cursorrules", ".cursor/agents/", ".cursor/skills/"),
    IDESupport("OpenCode", ".opencode/", "agents/", "skills/"),
    IDESupport("Gemini CLI", ".gemini/instructions.md", ".gemini/agents/", ".gemini/skills/"),
]


class IDEAdapter:
    """Adaptador multi-harness para detectar y exportar configuracion entre IDEs.

    Permite detectar que IDEs estan configurados en un proyecto, exportar
    agentes AGENTIC al formato nativo de cada IDE, y consultar la lista
    completa de IDES soportados.

    Args:
        project_root: Ruta raiz del proyecto. Si es None, se usa CWD.
    """

    def __init__(self, project_root: Optional[Path] = None) -> None:
        """Inicializa el adaptador con la raiz del proyecto.

        Args:
            project_root: Directorio raiz del proyecto. Si no se especifica,
                se usa Path.cwd().
        """
        self._root: Path = project_root or Path.cwd()
        self._detected_ides: List[str] = []

    def detect_ides(self) -> List[str]:
        """Detecta que IDEs tienen configuracion presente en el proyecto.

        Recorre SUPPORTED_IDES y verifica si el archivo de configuracion
        de cada IDE existe dentro de project_root.

        Returns:
            Lista con los nombres de los IDEs detectados (orden de
            SUPPORTED_IDES). Lista vacia si no se detecta ninguno.
        """
        self._detected_ides = []
        for ide in SUPPORTED_IDES:
            config = self._root / ide.config_file
            if config.exists():
                self._detected_ides.append(ide.name)
                logger.debug("IDE detectado: %s (config: %s)", ide.name, config)
        return list(self._detected_ides)

    def export_agents(self, target_ide: str, dry_run: bool = False) -> bool:
        """Exporta los agentes AGENTIC al formato del IDE destino.

        Lee los agentes desde ``.opencode/agents/`` y los copia al directorio
        que el IDE destino espera. Si dry_run es True, solo simula la
        operacion sin copiar archivos.

        Args:
            target_ide: Nombre del IDE destino (debe estar en
                SUPPORTED_IDES).
            dry_run: Si es True, solo simula la exportacion sin copiar.

        Returns:
            True si se exporto al menos un agente, False si no habia
            agentes origen o el IDE destino no es soportado.

        Raises:
            OSError: Si hay errores de permisos al escribir en el destino.
        """
        source_agents = self._root / ".opencode" / "agents"
        if not source_agents.exists():
            logger.warning(
                "No se encontraron agentes origen en %s",
                source_agents,
            )
            return False

        ide = next((i for i in SUPPORTED_IDES if i.name == target_ide), None)
        if ide is None:
            logger.warning("IDE destino no soportado: %s", target_ide)
            return False

        # Mapeo de IDE -> directorio destino
        target_map: Dict[str, Path] = {
            "Claude Code": Path.home() / ".claude" / "agents",
            "Codex CLI": Path.home() / ".codex" / "prompts",
        }
        target = target_map.get(target_ide, source_agents)

        if dry_run:
            logger.info(
                "[DRY-RUN] Se exportarian %d agentes a %s",
                len(list(source_agents.glob("*.md"))),
                target,
            )
            return len(list(source_agents.glob("*.md"))) > 0

        target.mkdir(parents=True, exist_ok=True)
        count = 0
        for agent_file in source_agents.glob("*.md"):
            dest = target / agent_file.name
            try:
                import shutil
                shutil.copy2(str(agent_file), str(dest))
                count += 1
                logger.debug("Exportado: %s -> %s", agent_file.name, dest)
            except OSError as exc:
                logger.error(
                    "Error al copiar %s a %s: %s",
                    agent_file.name, dest, exc,
                )
                raise

        logger.info("Exportados %d agentes a %s", count, target)
        return count > 0

    def get_supported_ides(self) -> List[IDESupport]:
        """Retorna la lista completa de IDEs soportados.

        Returns:
            Copia de la lista SUPPORTED_IDES con todos los IDEs
            que el adaptador puede manejar.
        """
        return list(SUPPORTED_IDES)
