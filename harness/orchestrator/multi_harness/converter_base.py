"""HarnessConverter — Clase base abstracta para adaptadores de runtime.

Define el contrato que todos los adaptadores de runtime deben implementar.
Cada adaptador convierte agentes, skills y configuracion de Swarmind (.opencode/)
al formato nativo del runtime destino.

Principios:
- SSOT: .opencode/ nunca se modifica (solo lectura).
- Export-only: los adaptadores solo escriben en su directorio destino.
- Idempotencia: ejecutar N veces produce el mismo resultado.
- Dry-run: todos los adaptadores soportan --dry-run.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ExportResult:
    """Resultado de una operacion de exportacion.

    Attributes:
        success: True si la exportacion fue exitosa.
        files_exported: Numero de archivos exportados.
        errors: Lista de errores ocurridos durante la exportacion.
        warnings: Lista de advertencias.
        target_dir: Directorio destino de la exportacion.
    """
    success: bool
    files_exported: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    target_dir: Path | None = None


class HarnessConverter(ABC):
    """Clase base abstracta para convertidores de runtime.

    Cada runtime (Claude Code, Codex CLI, Cursor, Gemini CLI, OpenCode)
    debe implementar esta interfaz para exportar agentes, skills y
    configuracion desde el formato SSOT de Swarmind.

    Args:
        project_root: Raiz del proyecto Swarmind.
    """

    def __init__(self, project_root: Path | None = None) -> None:
        """Inicializa el convertidor con la raiz del proyecto.

        Args:
            project_root: Directorio raiz del proyecto. Si no se especifica,
                se usa Path.cwd().
        """
        self._root: Path = project_root or Path.cwd()
        self._opencode_root: Path = self._root / ".opencode"

    # --- Propiedades abstractas ---

    @property
    @abstractmethod
    def runtime_name(self) -> str:
        """Nombre del runtime (opencode, claude, codex, cursor, gemini)."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Nombre comercial del runtime (ej: 'Claude Code')."""
        ...

    @property
    @abstractmethod
    def target_config_dir(self) -> str:
        """Directorio de configuracion del runtime (ej: '.claude')."""
        ...

    # --- Metodos abstractos de exportacion ---

    @abstractmethod
    def export_agents(self, dry_run: bool = False) -> ExportResult:
        """Exporta los agentes Swarmind al formato nativo del runtime.

        Args:
            dry_run: Si es True, solo simula la operacion sin escribir.

        Returns:
            ExportResult con el resultado de la exportacion.
        """
        ...

    @abstractmethod
    def export_skills(self, dry_run: bool = False) -> ExportResult:
        """Exporta los skills Swarmind al formato nativo del runtime.

        Args:
            dry_run: Si es True, solo simula la operacion sin escribir.

        Returns:
            ExportResult con el resultado de la exportacion.
        """
        ...

    @abstractmethod
    def export_config(self, dry_run: bool = False) -> ExportResult:
        """Exporta la configuracion general de Swarmind al runtime.

        Args:
            dry_run: Si es True, solo simula la operacion sin escribir.

        Returns:
            ExportResult con el resultado de la exportacion.
        """
        ...

    # --- Metodos concretos ---

    def export_all(self, dry_run: bool = False) -> dict[str, ExportResult]:
        """Exporta agentes + skills + config al runtime destino.

        Args:
            dry_run: Si es True, solo simula sin escribir archivos.

        Returns:
            Diccionario con {'agents': ExportResult, 'skills': ExportResult,
            'config': ExportResult}.
        """
        results: dict[str, ExportResult] = {
            "agents": self.export_agents(dry_run=dry_run),
            "skills": self.export_skills(dry_run=dry_run),
            "config": self.export_config(dry_run=dry_run),
        }
        logger.info(
            "[%s] Exportacion completa: %d/%d/%d (agentes/skills/config)",
            self.display_name,
            results["agents"].files_exported,
            results["skills"].files_exported,
            results["config"].files_exported,
        )
        return results

    def validate(self) -> list[str]:
        """Valida que el proyecto Swarmind tenga los archivos minimos necesarios.

        Returns:
            Lista de errores de validacion. Lista vacia si todo esta correcto.
        """
        errors: list[str] = []
        if not self._opencode_root.is_dir():
            errors.append(f"Directorio .opencode/ no encontrado en {self._root}")
        if not (self._opencode_root / "agents").is_dir():
            errors.append("Directorio .opencode/agents/ no encontrado")
        if not (self._opencode_root / "skills").is_dir():
            errors.append("Directorio .opencode/skills/ no encontrado")
        return errors

    def _get_opencode_agents(self) -> list[Path]:
        """Retorna la lista de archivos de agentes en .opencode/agents/.

        Returns:
            Lista de Path a los archivos .md de agentes.
        """
        agents_dir: Path = self._opencode_root / "agents"
        if not agents_dir.is_dir():
            return []
        return sorted(agents_dir.glob("*.md"))

    def _get_opencode_skills(self) -> list[Path]:
        """Retorna la lista de archivos de skills en .opencode/skills/.

        Returns:
            Lista de Path a los archivos .md de skills.
        """
        skills_dir: Path = self._opencode_root / "skills"
        if not skills_dir.is_dir():
            return []
        return sorted(skills_dir.glob("*.md"))

    def _target_path(self, *parts: str) -> Path:
        """Construye una ruta dentro del directorio de configuracion del runtime.

        Args:
            *parts: Segmentos de ruta relativos al directorio del runtime.

        Returns:
            Path absoluto compuesto.
        """
        return self._root / self.target_config_dir / Path(*parts)

    def _ensure_target_dir(self, *parts: str) -> Path:
        """Asegura que un directorio destino existe y retorna su Path.

        Args:
            *parts: Segmentos de ruta relativos al directorio del runtime.

        Returns:
            Path absoluto del directorio (creado si no existe).
        """
        target: Path = self._target_path(*parts)
        target.mkdir(parents=True, exist_ok=True)
        return target
