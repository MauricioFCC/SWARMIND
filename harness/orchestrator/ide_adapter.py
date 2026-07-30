"""IDEAdapter — Fachada de compatibilidad multi-harness.

Refactorizado para delegar en Multi-Harness Adapter Layer manteniendo
compatibilidad hacia atras. Todos los metodos originales se conservan.

La logica ahora reside en `harness/orchestrator/multi_harness/`.
Este modulo es una fachada que mantiene la API publica original.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from harness.orchestrator.multi_harness.cli.multi_harness_cli import (
    cmd_detect,
    cmd_export,
    cmd_status,
    cmd_validate,
)
from harness.orchestrator.multi_harness.runtime_detector import (
    RuntimeInfo,
    detect_runtime,
    get_detected_runtimes,
)

logger = logging.getLogger(__name__)


@dataclass
class IDESupport:
    """Describe el soporte de configuracion para un IDE especifico.

    Attributes:
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


# Lista canonica de IDEs soportados (SSOT) - mantenida para compatibilidad.
SUPPORTED_IDES: List[IDESupport] = [
    IDESupport("Claude Code", ".claude/settings.json", "AGENTS.md", ".claude/skills/"),
    IDESupport("Codex CLI", ".codex/config.toml", "AGENTS.md", ".codex/prompts/"),
    IDESupport("Cursor", ".cursorrules", ".cursor/agents/", ".cursor/skills/"),
    IDESupport("OpenCode", ".opencode/", "agents/", "skills/"),
    IDESupport("Gemini CLI", ".gemini/instructions.md", ".gemini/agents/", ".gemini/skills/"),
]


class IDEAdapter:
    """Adaptador multi-harness — Fachada que delega en Multi-Harness Layer.

    Mantiene compatibilidad hacia atras con el codigo existente mientras
    utiliza la nueva arquitectura de Multi-Harness Adapter Layer.

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

        Delega en get_detected_runtimes() del Multi-Harness Layer.

        Returns:
            Lista con los nombres comerciales de los IDEs detectados.
        """
        runtimes: List[RuntimeInfo] = get_detected_runtimes(self._root)
        self._detected_ides = [rt.display_name for rt in runtimes if rt.detected]
        return list(self._detected_ides)

    def export_agents(self, target_ide: str, dry_run: bool = False) -> bool:
        """Exporta los agentes Swarmind al formato del IDE destino.

        Delega en cmd_export() del Multi-Harness Layer.

        Args:
            target_ide: Nombre del IDE destino (debe estar en SUPPORTED_IDES).
            dry_run: Si es True, solo simula la operacion sin copiar.

        Returns:
            True si se exporto al menos un agente.

        Raises:
            OSError: Si hay errores de permisos al escribir en el destino.
        """
        # Mapear nombre comercial a nombre interno de runtime
        name_to_runtime: Dict[str, str] = {
            "Claude Code": "claude",
            "Codex CLI": "codex",
            "Cursor": "cursor",
            "OpenCode": "opencode",
            "Gemini CLI": "gemini",
        }
        runtime_name: Optional[str] = name_to_runtime.get(target_ide)

        if not runtime_name:
            logger.warning("IDE destino no soportado: %s", target_ide)
            return False

        try:
            return cmd_export(runtime_name, dry_run=dry_run, project_root=self._root)
        except OSError:
            raise
        except Exception as exc:
            logger.error("Error exportando a %s: %s", target_ide, exc)
            return False

    def export_all(self, dry_run: bool = False) -> Dict[str, bool]:
        """Exporta la configuracion a todos los runtimes soportados.

        Args:
            dry_run: Si es True, solo simula las operaciones.

        Returns:
            Dict con nombre de runtime -> resultado (True/False).
        """
        results: Dict[str, bool] = {}
        name_to_runtime: Dict[str, str] = {
            "Claude Code": "claude",
            "Codex CLI": "codex",
            "Cursor": "cursor",
            "OpenCode": "opencode",
            "Gemini CLI": "gemini",
        }
        for display_name, runtime_name in name_to_runtime.items():
            results[display_name] = cmd_export(
                runtime_name, dry_run=dry_run, project_root=self._root,
            )
        return results

    def get_supported_ides(self) -> List[IDESupport]:
        """Retorna la lista completa de IDEs soportados.

        Returns:
            Copia de la lista SUPPORTED_IDES con todos los IDEs.
        """
        return list(SUPPORTED_IDES)

    def detect_runtime(self) -> RuntimeInfo:
        """Detecta el runtime activo actualmente.

        Returns:
            RuntimeInfo con la informacion del runtime detectado.
        """
        return detect_runtime(self._root)

    def validate(self) -> bool:
        """Valida la estructura del proyecto para todos los runtimes.

        Returns:
            True si todo es valido.
        """
        return cmd_validate(self._root)
