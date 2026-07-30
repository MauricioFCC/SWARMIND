"""ClaudeAdapter — Adaptador para Claude Code por Anthropic.

Convierte agentes Swarmind (.opencode/agents/) al formato nativo de Claude Code:

- AGENTS.md: Lista de agentes disponibles con descripcion y comandos.
- .claude/settings.json: Configuracion de tiempo de ejecucion.
- .claude/skills/: Skills convertidos a prompts de sistema.

Referencia: docs.anthropic.com/en/docs/claude-code/overview
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from harness.orchestrator.multi_harness.converter_base import (
    ExportResult,
    HarnessConverter,
)

logger = logging.getLogger(__name__)


class ClaudeAdapter(HarnessConverter):
    """Adaptador para exportar agentes Swarmind a Claude Code.

    Genera archivos en .claude/ compatibles con Claude Code CLI.
    """

    @property
    def runtime_name(self) -> str:
        return "claude"

    @property
    def display_name(self) -> str:
        return "Claude Code"

    @property
    def target_config_dir(self) -> str:
        return ".claude"

    def export_agents(self, dry_run: bool = False) -> ExportResult:
        """Exporta agentes Swarmind a AGENTS.md + directorio .claude/agents/.

        Cada agente se convierte a una entrada en AGENTS.md y se copia
        el archivo .md individual a .claude/agents/.

        Args:
            dry_run: Si es True, solo simula la operacion.

        Returns:
            ExportResult con el resultado de la exportacion.
        """
        agents: list[Path] = self._get_opencode_agents()
        errors: list[str] = []
        warnings: list[str] = []

        if not agents:
            warnings.append("No se encontraron agentes en .opencode/agents/")
            return ExportResult(success=True, files_exported=0, warnings=warnings)

        if dry_run:
            logger.info("[Claude] DRY-RUN: %d agentes a exportar", len(agents))
            return ExportResult(success=True, files_exported=len(agents), target_dir=self._target_path("agents"))

        # Crear directorio destino
        target_agents_dir: Path = self._ensure_target_dir("agents")

        # Generar AGENTS.md (indice de agentes)
        agents_md_lines: list[str] = [
            "# AGENTES DISPONIBLES — Exportados desde Swarmind\n",
            "",
            "> Generado automaticamente por Multi-Harness Adapter Layer.",
            "> Fuente: .opencode/agents/",
            "",
        ]

        count: int = 0
        for agent_file in agents:
            dest: Path = target_agents_dir / agent_file.name
            try:
                shutil.copy2(str(agent_file), str(dest))
                count += 1
                # Extraer nombre del agente (primer heading del archivo)
                content: str = agent_file.read_text(encoding="utf-8")
                agent_name: str = agent_file.stem.replace("-", " ").title()
                for line in content.splitlines():
                    if line.startswith("# "):
                        agent_name = line.lstrip("# ").strip()
                        break
                agents_md_lines.append(f"- **{agent_name}**: `{dest.name}`")
                logger.debug("[Claude] Exportado agente: %s", agent_file.name)
            except OSError as exc:
                errors.append(f"Error copiando {agent_file.name}: {exc}")
                logger.error("[Claude] Error exportando %s: %s", agent_file.name, exc)

        agents_md_lines.append("")
        agents_md_lines.append(f"---\n*Total: {count} agentes exportados el {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}*")

        # Escribir AGENTS.md
        agents_md_path: Path = self._target_path("AGENTS.md")
        agents_md_path.write_text("\n".join(agents_md_lines), encoding="utf-8")
        logger.info("[Claude] AGENTS.md generado: %s", agents_md_path)

        return ExportResult(
            success=len(errors) == 0,
            files_exported=count,
            errors=errors,
            target_dir=target_agents_dir,
        )

    def export_skills(self, dry_run: bool = False) -> ExportResult:
        """Exporta skills Swarmind a .claude/skills/.

        Cada skill .md se copia al directorio de skills de Claude Code.

        Args:
            dry_run: Si es True, solo simula la operacion.

        Returns:
            ExportResult con el resultado de la exportacion.
        """
        skills: list[Path] = self._get_opencode_skills()
        errors: list[str] = []

        if not skills:
            logger.info("[Claude] No hay skills para exportar")
            return ExportResult(success=True, files_exported=0)

        if dry_run:
            logger.info("[Claude] DRY-RUN: %d skills a exportar", len(skills))
            return ExportResult(success=True, files_exported=len(skills))

        target_skills_dir: Path = self._ensure_target_dir("skills")
        count: int = 0
        for skill_file in skills:
            dest: Path = target_skills_dir / skill_file.name
            try:
                shutil.copy2(str(skill_file), str(dest))
                count += 1
                logger.debug("[Claude] Exportado skill: %s", skill_file.name)
            except OSError as exc:
                errors.append(f"Error copiando {skill_file.name}: {exc}")

        return ExportResult(
            success=len(errors) == 0,
            files_exported=count,
            errors=errors,
            target_dir=target_skills_dir,
        )

    def export_config(self, dry_run: bool = False) -> ExportResult:
        """Genera .claude/settings.json con configuracion de Claude Code.

        Args:
            dry_run: Si es True, solo simula la operacion.

        Returns:
            ExportResult con el resultado.
        """
        settings: dict = {
            "project": "Swarmind",
            "version": "3.0.0",
            "agents_path": ".claude/agents/AGENTS.md",
            "skills_path": ".claude/skills/",
            "settings": {
                "model": "claude-sonnet-4-20260506",
                "max_tokens": 64000,
                "dangerously_skip_permissions": False,
                "ignore_patterns": [
                    "**/node_modules/**",
                    "**/__pycache__/**",
                    "**/.git/**",
                    "**/*.cover",
                    "**/__pycache__/**",
                ],
            },
        }

        if dry_run:
            logger.info("[Claude] DRY-RUN: settings.json generado")
            return ExportResult(success=True, files_exported=1)

        settings_path: Path = self._target_path("settings.json")
        try:
            settings_path.write_text(
                json.dumps(settings, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            logger.info("[Claude] settings.json generado: %s", settings_path)
            return ExportResult(success=True, files_exported=1, target_dir=settings_path.parent)
        except OSError as exc:
            logger.error("[Claude] Error generando settings.json: %s", exc)
            return ExportResult(success=False, files_exported=0, errors=[str(exc)])
