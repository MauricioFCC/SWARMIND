"""CodexAdapter — Adaptador para Codex CLI de OpenAI.

Convierte agentes Swarmind (.opencode/agents/) al formato nativo de Codex CLI:

- .codex/config.toml: Configuracion del asistente Codex.
- .codex/prompts/: Skills convertidos a archivos de prompt.
- AGENTS.md: Indice de agentes disponibles.

Referencia: github.com/openai/codex
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from harness.orchestrator.multi_harness.converter_base import (
    ExportResult,
    HarnessConverter,
)

logger = logging.getLogger(__name__)


class CodexAdapter(HarnessConverter):
    """Adaptador para exportar agentes Swarmind a Codex CLI."""

    @property
    def runtime_name(self) -> str:
        return "codex"

    @property
    def display_name(self) -> str:
        return "Codex CLI"

    @property
    def target_config_dir(self) -> str:
        return ".codex"

    def export_agents(self, dry_run: bool = False) -> ExportResult:
        """Exporta agentes Swarmind a .codex/prompts/.

        Codex CLI utiliza prompts individuales en lugar de un archivo
        central de agentes. Cada agente .md se copia como prompt.

        Args:
            dry_run: Si es True, solo simula la operacion.

        Returns:
            ExportResult con el resultado.
        """
        agents: list[Path] = self._get_opencode_agents()
        errors: list[str] = []

        if not agents:
            return ExportResult(success=True, files_exported=0)

        if dry_run:
            logger.info("[Codex] DRY-RUN: %d agentes a exportar", len(agents))
            return ExportResult(success=True, files_exported=len(agents))

        target_prompts_dir: Path = self._ensure_target_dir("prompts")
        count: int = 0
        for agent_file in agents:
            dest: Path = target_prompts_dir / agent_file.name
            try:
                shutil.copy2(str(agent_file), str(dest))
                count += 1
                logger.debug("[Codex] Exportado agente: %s", agent_file.name)
            except OSError as exc:
                errors.append(f"Error copiando {agent_file.name}: {exc}")

        return ExportResult(
            success=len(errors) == 0,
            files_exported=count,
            errors=errors,
            target_dir=target_prompts_dir,
        )

    def export_skills(self, dry_run: bool = False) -> ExportResult:
        """Exporta skills Swarmind a .codex/prompts/skills/.

        Args:
            dry_run: Si es True, solo simula la operacion.

        Returns:
            ExportResult con el resultado.
        """
        skills: list[Path] = self._get_opencode_skills()
        errors: list[str] = []

        if not skills:
            return ExportResult(success=True, files_exported=0)

        if dry_run:
            logger.info("[Codex] DRY-RUN: %d skills a exportar", len(skills))
            return ExportResult(success=True, files_exported=len(skills))

        target_skills_dir: Path = self._ensure_target_dir("prompts", "skills")
        count: int = 0
        for skill_file in skills:
            dest: Path = target_skills_dir / skill_file.name
            try:
                shutil.copy2(str(skill_file), str(dest))
                count += 1
            except OSError as exc:
                errors.append(f"Error copiando {skill_file.name}: {exc}")

        return ExportResult(
            success=len(errors) == 0,
            files_exported=count,
            errors=errors,
            target_dir=target_skills_dir,
        )

    def export_config(self, dry_run: bool = False) -> ExportResult:
        """Genera .codex/config.toml con configuracion de Codex CLI.

        Args:
            dry_run: Si es True, solo simula la operacion.

        Returns:
            ExportResult con el resultado.
        """
        config_lines: list[str] = [
            "[project]",
            'name = "Swarmind"',
            'version = "3.0.0"',
            "",
            "[agent]",
            'model = "o4-mini"',
            "max_tokens = 32000",
            'prompts_dir = ".codex/prompts"',
            "",
            "[tools]",
            "sandbox = false",
            "code_execution = true",
            "",
            "[settings]",
            "danger_mode = false",
            'ignore_patterns = ["node_modules/", "__pycache__/", ".git/", "*.cover"]',
            "",
        ]

        if dry_run:
            logger.info("[Codex] DRY-RUN: config.toml generado")
            return ExportResult(success=True, files_exported=1)

        config_path: Path = self._target_path("config.toml")
        try:
            config_path.write_text("\n".join(config_lines), encoding="utf-8")
            logger.info("[Codex] config.toml generado: %s", config_path)
            return ExportResult(success=True, files_exported=1, target_dir=config_path.parent)
        except OSError as exc:
            logger.error("[Codex] Error generando config.toml: %s", exc)
            return ExportResult(success=False, files_exported=0, errors=[str(exc)])
