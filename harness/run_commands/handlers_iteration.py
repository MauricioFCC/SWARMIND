"""run_commands handlers de iteracion (end-of-iteration)."""
from __future__ import annotations

from pathlib import Path

import harness.run_commands as _rc


def _parse_iteration_flags(cmd: str) -> dict:
    """Parse flags from a !iteration end command."""
    flags = {
        "skip_bugs": False, "skip_sec": False, "skip_docs": False,
        "dry_run": False, "quick": False, "auto": False,
    }
    parts = cmd.split()
    if "--dry-run" in parts:
        flags["dry_run"] = True
    if "--skip-bugs" in parts:
        flags["skip_bugs"] = True
    if "--skip-sec" in parts:
        flags["skip_sec"] = True
    if "--skip-docs" in parts:
        flags["skip_docs"] = True
    if "--quick" in parts:
        flags["quick"] = True
    if "--auto" in parts:
        flags["auto"] = True
    return flags

def _handle_iteration_end(cmd: str, harness_root) -> None:
    """Handle ``!iteration end [--dry-run] [--skip-bugs] [--skip-sec] [--skip-docs] [--quick] [--auto]``."""
    flags = _rc._parse_iteration_flags(cmd)

    # Redirect to quick/auto mode if flagged
    if flags["quick"]:
        _rc._handle_iteration_quick(cmd, harness_root)
        return
    if flags["auto"]:
        _rc._handle_iteration_auto(cmd, harness_root)
        return

    _rc.logger.info("[Harness] Iniciando pipeline de fin de iteracion...")
    if flags["dry_run"]:
        _rc.logger.info("[Harness] Modo DRY-RUN — no se modificaran archivos")
    if any([flags["skip_bugs"], flags["skip_sec"], flags["skip_docs"]]):
        skips = []
        if flags["skip_bugs"]:
            skips.append("bugs")
        if flags["skip_sec"]:
            skips.append("security")
        if flags["skip_docs"]:
            skips.append("docs")
        _rc.logger.info(f"[Harness] Fases saltadas: {', '.join(skips)}")
    _rc.sys.path.insert(1, str(harness_root.parent))
    from harness.scripts.end_of_iteration import run_pipeline
    run_pipeline(
        skip_bugs=flags["skip_bugs"], skip_security=flags["skip_sec"],
        skip_docs=flags["skip_docs"], dry_run=flags["dry_run"],
    )

def _handle_iteration_quick(cmd: str = "", harness_root=None) -> None:
    """Handle ``!iteration quick`` or ``!iteration end --quick``.

    Modo rápido: solo bugs + tokens, salta security y docs.
    """
    _rc.sys.path.insert(1, str(Path(__file__).resolve().parent.parent.parent))
    from harness.scripts.end_of_iteration import run_quick_pipeline
    run_quick_pipeline()

def _handle_iteration_auto(cmd: str = "", harness_root=None) -> None:
    """Handle ``!iteration auto`` or ``!iteration end --auto``.

    Modo automático: pipeline completo + commit si no hay criticals.
    """
    _rc.sys.path.insert(1, str(Path(__file__).resolve().parent.parent.parent))
    from harness.scripts.end_of_iteration import run_auto_pipeline
    run_auto_pipeline()

def _handle_iteration_report() -> None:
    """Handle ``!iteration report`` — shows the last saved iteration report."""
    from harness.scripts.end_of_iteration import print_last_report
    print_last_report()

def _handle_iteration_history(cmd: str) -> None:
    """Handle ``!iteration history [--all]`` — muestra timeline de iteraciones."""
    from harness.scripts.end_of_iteration import show_iteration_history
    parts = cmd.split()
    if "--all" in parts:
        show_iteration_history(limit=0)  # 0 = sin límite
    else:
        show_iteration_history(limit=10)

def _handle_iteration_diff(cmd: str) -> None:
    """Handle ``!iteration diff [--last] [--n <num>]`` — muestra detalle de iteración.

    Ejemplos:
        !iteration diff            → última iteración
        !iteration diff --last     → última iteración
        !iteration diff --n 2      → penúltima iteración
        !iteration diff --n 3      → antepenúltima iteración
    """
    from harness.scripts.end_of_iteration import show_iteration_diff
    parts = cmd.split()

    n = 1  # default: última
    if "--n" in parts:
        idx = parts.index("--n")
        if idx + 1 < len(parts):
            try:
                n = max(1, int(parts[idx + 1]))
            except (ValueError, IndexError):
                n = 1
    # --last también es 1 (default)
    show_iteration_diff(n=n)

__all__ = [
    "_handle_iteration_auto",
    "_handle_iteration_diff",
    "_handle_iteration_end",
    "_handle_iteration_history",
    "_handle_iteration_quick",
    "_handle_iteration_report",
    "_parse_iteration_flags",
]
