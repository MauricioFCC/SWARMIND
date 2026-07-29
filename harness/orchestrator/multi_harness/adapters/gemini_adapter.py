"""GeminiAdapter — Adaptador para Gemini CLI de Google.

Convierte agentes AGENTIC (.opencode/agents/) al formato nativo de Gemini CLI:

- .gemini/instructions.md: Instrucciones de sistema para Gemini.
- .gemini/agents/: Agentes individuales en formato compatible.
- .gemini/skills/: Skills como prompts de sistema adicionales.

Referencia: ai.google.dev/gemini-cli
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional

from harness.orchestrator.multi_harness.converter_base import (
    ExportResult,
    HarnessConverter,
)

logger = logging.getLogger(__name__)


class GeminiAdapter(HarnessConverter):
    """Adaptador para exportar agentes AGENTIC a Gemini CLI."""

    @property
    def runtime_name(self) -> str:
        return "gemini"

    @property
    def display_name(self) -> str:
        return "Gemini CLI"

    @property
    def target_config_dir(self) -> str:
        return ".gemini"

    def export_agents(self, dry_run: bool = False) -> ExportResult:
        """Exporta agentes AGENTIC a .gemini/agents/.

        Args:
            dry_run: Si es True, solo simula la operacion.

        Returns:
            ExportResult con el resultado.
        """
        agents: List[Path] = self._get_opencode_agents()
        errors: List[str] = []

        if not agents:
            return ExportResult(success=True, files_exported=0)

        if dry_run:
            logger.info("[Gemini] DRY-RUN: %d agentes a exportar", len(agents))
            return ExportResult(success=True, files_exported=len(agents))

        target_agents_dir: Path = self._ensure_target_dir("agents")
        count: int = 0
        for agent_file in agents:
            dest: Path = target_agents_dir / agent_file.name
            try:
                shutil.copy2(str(agent_file), str(dest))
                count += 1
                logger.debug("[Gemini] Exportado agente: %s", agent_file.name)
            except OSError as exc:
                errors.append(f"Error copiando {agent_file.name}: {exc}")

        return ExportResult(
            success=len(errors) == 0,
            files_exported=count,
            errors=errors,
            target_dir=target_agents_dir,
        )

    def export_skills(self, dry_run: bool = False) -> ExportResult:
        """Exporta skills AGENTIC a .gemini/skills/.

        Args:
            dry_run: Si es True, solo simula la operacion.

        Returns:
            ExportResult con el resultado.
        """
        skills: List[Path] = self._get_opencode_skills()
        errors: List[str] = []

        if not skills:
            return ExportResult(success=True, files_exported=0)

        if dry_run:
            logger.info("[Gemini] DRY-RUN: %d skills a exportar", len(skills))
            return ExportResult(success=True, files_exported=len(skills))

        target_skills_dir: Path = self._ensure_target_dir("skills")
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
        """Genera .gemini/instructions.md con instrucciones de sistema.

        Las instrucciones definen el comportamiento de Gemini CLI cuando
        trabaja con el proyecto AGENTIC. Se genera un resumen de todos
        los agentes y skills disponibles.

        Args:
            dry_run: Si es True, solo simula la operacion.

        Returns:
            ExportResult con el resultado.
        """
        instructions: List[str] = [
            "# AGENTIC — Instrucciones de Sistema para Gemini CLI",
            "",
            "> Generado automaticamente por Multi-Harness Adapter Layer.",
            "> Fuente: .opencode/",
            "",
            "Eres AGENTIC, un sistema multi-agente construido sobre Gemini CLI.",
            "",
            "## Agentes disponibles",
        ]

        agents: List[Path] = self._get_opencode_agents()
        for agent in agents:
            agent_name: str = agent.stem.replace("-", " ").title()
            instructions.append(f"- {agent_name} (`{agent.name}`)")

        instructions.extend([
            "",
            "## Skills disponibles",
        ])

        skills: List[Path] = self._get_opencode_skills()
        for skill in skills:
            skill_name: str = skill.stem.replace("-", " ").title()
            instructions.append(f"- {skill_name} (`{skill.name}`)")

        instructions.extend([
            "",
            "## Reglas de operacion",
            "- Usa siempre Python 3.12+",
            "- Sigue PEP 8 con type hints",
            "- Documentacion en espanol",
            "- Errores con formato WHAT + WHY + WHERE",
            "- Tests con pytest, min 80% coverage",
            "- Sin except:pass silencioso",
            "- Maximo 900 lines por archivo",
            "",
        ])

        if dry_run:
            logger.info("[Gemini] DRY-RUN: instructions.md generado")
            return ExportResult(success=True, files_exported=1)

        instructions_path: Path = self._ensure_target_dir()
        instructions_path = instructions_path / "instructions.md"
        try:
            instructions_path.write_text("\n".join(instructions), encoding="utf-8")
            logger.info("[Gemini] instructions.md generado: %s", instructions_path)
            return ExportResult(success=True, files_exported=1, target_dir=instructions_path.parent)
        except OSError as exc:
            logger.error("[Gemini] Error generando instructions.md: %s", exc)
            return ExportResult(success=False, files_exported=0, errors=[str(exc)])
