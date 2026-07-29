"""OpenCodeAdapter — Adaptador nativo para OpenCode.

OpenCode es el runtime nativo de AGENTIC. Este adaptador es un passthrough:
no convierte nada porque .opencode/ YA esta en el formato correcto.

Proposito:
- Validar que la estructura .opencode/ es correcta.
- Proveer metadatos para el CLI (stats, conteo de agentes/skills).
- Servir como referencia para otros adaptadores.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

from harness.orchestrator.multi_harness.converter_base import (
    ExportResult,
    HarnessConverter,
)

logger = logging.getLogger(__name__)


class OpenCodeAdapter(HarnessConverter):
    """Adaptador nativo para OpenCode (passthrough).

    No realiza conversiones porque .opencode/ es el formato SSOT.
    Todos los metodos de exportacion retornan exito inmediato.
    """

    @property
    def runtime_name(self) -> str:
        return "opencode"

    @property
    def display_name(self) -> str:
        return "OpenCode"

    @property
    def target_config_dir(self) -> str:
        return ".opencode"

    def export_agents(self, dry_run: bool = False) -> ExportResult:
        """Verifica que los agentes existen (sin copiar).

        Returns:
            ExportResult con conteo de agentes encontrados.
        """
        agents: List[Path] = self._get_opencode_agents()
        if dry_run:
            logger.info("[OpenCode] DRY-RUN: %d agentes disponibles", len(agents))
        return ExportResult(
            success=True,
            files_exported=len(agents),
            target_dir=self._opencode_root / "agents",
        )

    def export_skills(self, dry_run: bool = False) -> ExportResult:
        """Verifica que los skills existen (sin copiar).

        Returns:
            ExportResult con conteo de skills encontrados.
        """
        skills: List[Path] = self._get_opencode_skills()
        if dry_run:
            logger.info("[OpenCode] DRY-RUN: %d skills disponibles", len(skills))
        return ExportResult(
            success=True,
            files_exported=len(skills),
            target_dir=self._opencode_root / "skills",
        )

    def export_config(self, dry_run: bool = False) -> ExportResult:
        """Verifica que la configuracion existe (sin copiar).

        Returns:
            ExportResult indicando si opencode.json existe.
        """
        config_file: Path = self._opencode_root / "opencode.json"
        exists: bool = config_file.exists()
        if dry_run:
            logger.info("[OpenCode] DRY-RUN: config %s", "presente" if exists else "ausente")
        return ExportResult(
            success=exists,
            files_exported=1 if exists else 0,
            target_dir=self._opencode_root,
        )

    def get_stats(self) -> Dict[str, int]:
        """Retorna estadisticas del proyecto OpenCode.

        Returns:
            Dict con num_agents, num_skills, num_configs.
        """
        return {
            "num_agents": len(self._get_opencode_agents()),
            "num_skills": len(self._get_opencode_skills()),
            "num_configs": 1 if (self._opencode_root / "opencode.json").exists() else 0,
        }
