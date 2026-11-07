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
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

#: Sufijo de las variantes minificadas de agente: artefacto OCULTO de OpenCode
#: (``hidden: true``) que el propio harness lee como prompt pre-compilado.
#: Nunca se exporta a otros runtimes (los duplicaria).
MIN_AGENT_SUFFIX = ".agent.min.md"

#: Manifesto de una skill. Layout del estandar Agent Skills de la Linux
#: Foundation, compartido por OpenCode, Claude Code y Codex: ``<skill>/SKILL.md``.
SKILL_MANIFEST = "SKILL.md"


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
        """Retorna los perfiles BASE de agentes en ``.opencode/agents/``.

        Excluye las variantes ``*.agent.min.md``: son artefactos ocultos
        especificos de OpenCode que no deben duplicarse en el runtime destino.
        El filtro coincide con el del resto del harness
        (``agent_discovery.discovery``, ``routing_mutation``,
        ``compile_agents``); este modulo era la excepcion.

        Returns:
            Lista de Path a los archivos .md base (sin variantes min).
        """
        agents_dir: Path = self._opencode_root / "agents"
        if not agents_dir.is_dir():
            return []
        return sorted(
            p for p in agents_dir.glob("*.md") if not p.name.endswith(MIN_AGENT_SUFFIX)
        )

    def _get_opencode_skills(self) -> list[Path]:
        """Retorna el manifesto ``SKILL.md`` de cada skill de ``.opencode/skills/``.

        Layout real (estandar Agent Skills): ``<skill>/SKILL.md``. Se aceptan
        tambien ``.md`` planos en la raiz por compatibilidad con instalaciones
        antiguas (el discovery plano devolvia ``[]`` en un repo real y
        ``export_skills`` no exportaba nada).

        Returns:
            Lista de Path: ``SKILL.md`` de cada carpeta + ``.md`` planos legados.
        """
        skills_dir: Path = self._opencode_root / "skills"
        if not skills_dir.is_dir():
            return []
        nested = sorted(skills_dir.glob(f"*/{SKILL_MANIFEST}"))
        flat = sorted(p for p in skills_dir.glob("*.md") if p.is_file())
        return [*nested, *flat]

    def _copy_agents(self, target_dir: Path, label: str) -> tuple[int, list[str]]:
        """Copia los perfiles base de agentes a ``target_dir`` (layout plano).

        Args:
            target_dir: Directorio destino (ya creado por el caller).
            label: Etiqueta del runtime, para logs y errores.

        Returns:
            Tupla ``(n_exportados, errores)``.
        """
        errors: list[str] = []
        count: int = 0
        for agent_file in self._get_opencode_agents():
            dest: Path = target_dir / agent_file.name
            try:
                shutil.copy2(str(agent_file), str(dest))
                count += 1
                logger.debug("[%s] Exportado agente: %s", label, agent_file.name)
            except OSError as exc:
                errors.append(f"Error copiando {agent_file.name}: {exc}")
                logger.error("[%s] Error exportando %s: %s", label, agent_file.name, exc)
        return count, errors

    def _copy_skills(self, target_dir: Path, label: str) -> tuple[int, list[str]]:
        """Copia skills a ``target_dir`` preservando el layout ``<skill>/SKILL.md``.

        Cada skill va en su propia carpeta: copiar todos los ``SKILL.md`` en
        la raiz del destino los pisaria entre si. Los ``.md`` planos legados
        se copian en la raiz (su nombre es unico, no colisionan).

        Args:
            target_dir: Directorio destino (ya creado por el caller).
            label: Etiqueta del runtime, para logs y errores.

        Returns:
            Tupla ``(n_exportados, errores)``.
        """
        errors: list[str] = []
        count: int = 0
        for skill_file in self._get_opencode_skills():
            if skill_file.name == SKILL_MANIFEST:
                dest: Path = target_dir / skill_file.parent.name / skill_file.name
            else:
                dest = target_dir / skill_file.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(str(skill_file), str(dest))
                count += 1
                logger.debug("[%s] Exportado skill: %s", label, skill_file.name)
            except OSError as exc:
                errors.append(f"Error copiando {skill_file.name}: {exc}")
                logger.error("[%s] Error exportando %s: %s", label, skill_file.name, exc)
        return count, errors

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
