"""CursorAdapter — Adaptador para Cursor IDE.

Convierte agentes AGENTIC (.opencode/agents/) al formato nativo de Cursor:

- .cursorrules: Reglas de comportamiento para Cursor AI.
- .cursor/agents/: Agentes individuales en formato Cursor.
- .cursor/skills/: Skills como prompts de sistema.

Referencia: cursor.com
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


class CursorAdapter(HarnessConverter):
    """Adaptador para exportar agentes AGENTIC a Cursor IDE."""

    @property
    def runtime_name(self) -> str:
        return "cursor"

    @property
    def display_name(self) -> str:
        return "Cursor"

    @property
    def target_config_dir(self) -> str:
        return ".cursor"

    def export_agents(self, dry_run: bool = False) -> ExportResult:
        """Exporta agentes AGENTIC a .cursor/agents/.

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
            logger.info("[Cursor] DRY-RUN: %d agentes a exportar", len(agents))
            return ExportResult(success=True, files_exported=len(agents))

        target_agents_dir: Path = self._ensure_target_dir("agents")
        count: int = 0
        for agent_file in agents:
            dest: Path = target_agents_dir / agent_file.name
            try:
                shutil.copy2(str(agent_file), str(dest))
                count += 1
                logger.debug("[Cursor] Exportado agente: %s", agent_file.name)
            except OSError as exc:
                errors.append(f"Error copiando {agent_file.name}: {exc}")

        return ExportResult(
            success=len(errors) == 0,
            files_exported=count,
            errors=errors,
            target_dir=target_agents_dir,
        )

    def export_skills(self, dry_run: bool = False) -> ExportResult:
        """Exporta skills AGENTIC a .cursor/skills/.

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
            logger.info("[Cursor] DRY-RUN: %d skills a exportar", len(skills))
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
        """Genera .cursorrules con reglas de comportamiento Cursor.

        .cursorrules define el comportamiento del asistente Cursor AI
        en formato YAML-like. Se genera a partir de la configuracion
        de los skills y agentes de AGENTIC.

        Args:
            dry_run: Si es True, only simula la operacion.

        Returns:
            ExportResult con el resultado.
        """
        rules_lines: List[str] = [
            "# .cursorrules — Generado por AGENTIC Multi-Harness Adapter",
            "# Fuente: .opencode/",
            "",
            "# Reglas de comportamiento del asistente",
            "you are AGENTIC, a multi-agent system specialized in:",
            "- Software architecture and development",
            "- Legal and compliance document analysis",
            "- Quantitative trading and alpha research",
            "- Data science and machine learning",
            "- Security auditing and penetration testing",
            "",
            "# Contexto del proyecto",
            "- Project: AGENTIC",
            "- Language: Python 3.12+",
            "- Testing: pytest with property-based testing",
            "- Docs: mdbook in docs/",
            "",
            "# Reglas de codigo",
            "- Follow PEP 8 and type hints",
            "- All public functions MUST have docstrings in Spanish",
            "- Error messages MUST include WHAT + WHY + WHERE",
            "- No silent except:pass allowed",
            "- Keep functions under 50 lines where possible",
            "- Maximum 900 lines per file",
            "",
            "# Skills cargados",
        ]

        skills: List[Path] = self._get_opencode_skills()
        for skill in skills:
            skill_name: str = skill.stem.replace("-", " ").title()
            rules_lines.append(f"- {skill_name} ({skill.name})")

        rules_lines.extend([
            "",
            "# Testing",
            "- Run tests with: pytest",
            "- Coverage minimum: 80%",
            "- Always write tests for new code",
            "- Use property-based testing (PBT) for edge cases",
            "",
        ])

        if dry_run:
            logger.info("[Cursor] DRY-RUN: .cursorrules generado")
            return ExportResult(success=True, files_exported=1)

        rules_path: Path = self._root / ".cursorrules"
        try:
            rules_path.write_text("\n".join(rules_lines), encoding="utf-8")
            logger.info("[Cursor] .cursorrules generado: %s", rules_path)
            return ExportResult(success=True, files_exported=1, target_dir=self._root)
        except OSError as exc:
            logger.error("[Cursor] Error generando .cursorrules: %s", exc)
            return ExportResult(success=False, files_exported=0, errors=[str(exc)])
