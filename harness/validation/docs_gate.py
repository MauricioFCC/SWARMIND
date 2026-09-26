"""docs_gate.py — Gate de documentacion viva pre-codigo (Search 9-13, ADR-0082).

WHAT: Verifica que el repo tenga actualizaciones de documentacion viva
(PLAN.md/AGENTS.md/SPECS.md/ADR/specs/) en el working tree antes de
aprobar generacion de codigo.
WHY: Fase 2 del doc — docs vivas (SPECS/PLAN/ADRs) como artefactos de
primera clase; aprobar codigo sin actualizar docs degrada el sistema.
Fuera de repos git: SKIP pass (no bloquea scripts sueltos).
WHERE: `task_planner` antes del `parallel_executor`; gate T1.

Uso:
    report = check_docs_fresh(repo_path)
    if not report.passed: pedir(report.missing)
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("harness.validation.docs_gate")

#: Archivos/dirs de documentacion viva (Fase 2).
DOC_LIVING_FILES: tuple[str, ...] = (
    "PLAN.md",
    "AGENTS.md",
    "SPECS.md",
    "ARCHITECTURE.md",
    "ADR",
    "adr",
    "docs",
    "specs",
    "CLAUDE.md",
)


@dataclass(frozen=True)
class DocsGateReport:
    """Resultado del gate de documentacion viva.

    Attributes:
        passed: True si hay docs actualizadas (o SKIP fuera de repo).
        updated: Rutas vivas modificadas detectadas.
        missing: Sugerencia de que actualizar si no hay nada.
        skipped: True si no es repo git (no bloquea).
    """

    passed: bool
    updated: tuple[str, ...] = ()
    missing: tuple[str, ...] = DOC_LIVING_FILES
    skipped: bool = False


def _git_changed(repo: Path) -> list[str]:
    """Lista archivos modificados (staged + unstaged + untracked).

    Args:
        repo: Raiz del repo git.

    Returns:
        Rutas relativas modificadas ([] si git falla).
    """
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain", "-uall"],
            cwd=str(repo), capture_output=True, text=True,
            timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if out.returncode != 0:
        return []
    changed: list[str] = []
    for line in out.stdout.splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) == 2:
            path = parts[1].strip('"')
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            changed.append(path)
    return changed


def check_docs_fresh(repo: Path) -> DocsGateReport:
    """Verifica documentacion viva actualizada en el repo.

    Args:
        repo: Raiz del proyecto (debe tener .git para auditar; si no,
            retorna SKIP pass).

    Returns:
        DocsGateReport con pass/updated/missing/skipped.
    """
    if not (repo / ".git").is_dir():
        logger.debug("docs_gate: %s no es repo git; SKIP", repo)
        return DocsGateReport(passed=True, skipped=True)
    changed = _git_changed(repo)
    updated = tuple(
        sorted({
            path for path in changed
            if any(
                path == marker or path.startswith(marker.rstrip("/") + "/") or marker in path.split("/")
                for marker in DOC_LIVING_FILES
            )
        })
    )
    if updated:
        return DocsGateReport(passed=True, updated=updated, missing=())
    return DocsGateReport(passed=False, missing=DOC_LIVING_FILES)
