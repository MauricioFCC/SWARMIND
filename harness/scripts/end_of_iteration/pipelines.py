"""Pipelines de ejecucion y entry point CLI de fin de iteracion.

Submodulo interno del paquete :mod:`harness.scripts.end_of_iteration`.

Extraido de forma mecanica desde ``__init__.py`` (regla AGR: archivos
< 500 lineas). Define ``run_pipeline``, ``run_quick_pipeline``,
``run_auto_pipeline``, ``_run_pre_commit_pipeline``, ``_run_watch_pipeline``
y ``main``. Los cuerpos son identicos al original; solo cambia la ubicacion
fisica del codigo.
"""

from __future__ import annotations

import sys
import time
from datetime import UTC, datetime
from typing import Any

from .cli import parse_args
from .config import (
    PROJECT_ROOT,
    IterationReport,
    _bold,
    _cyan,
    _err,
    _get_changed_files_since_last_commit,
    _get_git_uncommitted,
    _ok,
    _safe_print,
    _warn,
)
from .display import print_last_report
from .phase1_bugs import auto_fix_bugs, scan_for_bugs
from .phase2_security import security_scan
from .phases import PHASES, run_pipeline_recursive
from .reporting import _save_report_to_json, _save_report_to_lancedb

# =============================================================================
# Main Pipeline
# =============================================================================


def run_pipeline(
    skip_bugs: bool = False,
    skip_security: bool = False,
    skip_docs: bool = False,
    dry_run: bool = False,
    auto_commit: bool = False,
) -> IterationReport:
    """Run the complete end-of-iteration pipeline.

    Args:
        skip_bugs: Skip bug hunting phase.
        skip_security: Skip security review phase.
        skip_docs: Skip documentation update phase.
        dry_run: Only simulate, don't modify anything.
        auto_commit: Auto-commit mode (no exit on criticals, no interactive commit).

    Returns:
        IterationReport with all findings.
    """
    start_time = time.time()
    report = IterationReport(timestamp=datetime.now(UTC).isoformat())

    changed_files = _get_changed_files_since_last_commit()
    if not changed_files:
        changed_files = _get_git_uncommitted()
    report.files_changed = changed_files

    if dry_run:
        _safe_print(f"  {_cyan('[DRY-RUN]')} Modo simulado - no se modificaran archivos")
    _safe_print(f"  Archivos cambiados: {len(changed_files)}")
    if changed_files:
        for f in changed_files[:10]:
            _safe_print(f"    {f}")
        if len(changed_files) > 10:
            _safe_print(f"    ... y {len(changed_files) - 10} mas")

    # Contexto compartido entre fases (pasa por el pipeline recursivo)
    context: dict[str, Any] = {
        "report": report,
        "changed_files": changed_files,
        "skip_bugs": skip_bugs,
        "skip_security": skip_security,
        "skip_docs": skip_docs,
        "dry_run": dry_run,
        "auto_commit": auto_commit,
        "bugs": [],
        "sec_findings": [],
        "docs_stale": [],
        "token_rep": None,
    }

    # Pipeline recursivo
    context = run_pipeline_recursive(PHASES, 0, context)

    report.elapsed_seconds = time.time() - start_time
    _safe_print(f"\n  Pipeline completado en {report.elapsed_seconds:.2f}s")

    _save_report_to_json(report)
    _save_report_to_lancedb(report)
    return report


# =============================================================================
# Modo rapido y automatico
# =============================================================================


def run_quick_pipeline() -> dict[str, Any]:
    """Modo rapido: solo bugs + tokens, salta security, docs y commit.

    Tiempo objetivo < 2s. Escanea solo archivos staged.
    Returns dict with status info.
    """
    start_time = time.time()

    _safe_print()
    _safe_print(f"  {_bold('Modo rapido activado')}")
    _safe_print()

    import subprocess as _subprocess
    try:
        result = _subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True, text=True, timeout=15, cwd=str(PROJECT_ROOT), check=False,
        )
        staged = [f.strip() for f in result.stdout.split("\n") if f.strip()]
    except Exception:  # noqa: BLE001
        staged = []

    if not staged:
        staged = _get_git_uncommitted()

    scope_files = [
        f for f in staged
        if not f.startswith("harness/db/") and "__pycache__" not in f and ".git/" not in f
    ]

    _safe_print(f"  {_bold('Bug Hunting...')}")
    bugs = scan_for_bugs(directory=".", changed_files=scope_files)
    bugs = auto_fix_bugs(bugs, dry_run=True)
    criticals = [b for b in bugs if b.severity == "critical"]
    majors = [b for b in bugs if b.severity == "major"]
    minors = [b for b in bugs if b.severity == "minor"]

    _safe_print(f"    {len(criticals)} critical, {len(majors)} major, {len(minors)} minor")
    for b in criticals[:5]:
        _safe_print(f"    {_err('[BUG]')} {b.file}:{b.line} - {b.message}")
    for b in majors[:5]:
        _safe_print(f"    {_warn('[BUG]')} {b.file}:{b.line} - {b.message}")

    _safe_print(f"\n  {_bold('Token Report...')}")
    from .phase4_tokens import _estimate_tokens_from_git
    token_rep = _estimate_tokens_from_git()
    _safe_print(f"    Input: ~{token_rep.tokens_input_total:,} tokens")
    _safe_print(f"    Output: ~{token_rep.tokens_output_total:,} tokens")

    elapsed = time.time() - start_time

    if criticals:
        _safe_print(f"\n    {_err('Criticals encontrados. Revisar manualmente.')}")
        for b in criticals[:5]:
            _safe_print(f"    {_err('[CRITICAL]')} {b.file}:{b.line} - {b.message}")
        status = "blocked"
    else:
        _safe_print(f"\n    {_ok('Modo rapido completado.')}")
        status = "ok"

    _safe_print(f"    ({elapsed:.2f}s)")
    return {"status": status, "criticals": len(criticals), "bugs": len(bugs), "elapsed": elapsed}


def run_auto_pipeline() -> dict[str, Any]:
    """Modo automatico: ejecuta pipeline completo, hace commit si no hay criticals.

    Si hay criticals, aborta y muestra los issues para revision manual.
    Si no hay criticals, hace commit automatico con el mensaje generado.
    """
    _safe_print()
    _safe_print(f"  {_bold('Modo automatico activado')}")
    _safe_print()

    report = run_pipeline(auto_commit=True)

    blocked = report.bugs_critical > 0

    if blocked:
        _safe_print(f"\n    {_err('Pipeline bloqueado por issues criticos. No se hara commit.')}")
        return {
            "status": "blocked",
            "criticals": report.bugs_critical,
            "report": report,
            "commit_message": report.commit_message_suggested,
        }

    _safe_print(f"\n  {_bold('Preparando commit automatico...')}")
    commit_msg = report.commit_message_suggested

    if not commit_msg or not commit_msg.strip():
        _safe_print(f"    {_warn('No se genero mensaje de commit. Omitiendo.')}")
        return {"status": "ok", "auto_commit": False, "report": report}

    clean_lines = [line for line in commit_msg.split('\n') if not line.strip().startswith('#')]
    clean_msg = '\n'.join(line for line in clean_lines if line.strip())

    if not clean_msg:
        clean_msg = "chore: actualizacion automatica"

    import subprocess
    try:
        r = subprocess.run(
            ["git", "commit", "-m", clean_msg],
            capture_output=True, text=True, timeout=30, cwd=str(PROJECT_ROOT), check=False,
        )
        if r.returncode == 0:
            _safe_print(f"    {_ok('Commit automatico exitoso')}")
            auto_committed = True

            _safe_print()
            try:
                push = input(f"  {_bold('Hacer push automatico?')} [y/N]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                push = ""
            if push == "y":
                r2 = subprocess.run(
                    ["git", "push"], capture_output=True, text=True, timeout=60,
                    cwd=str(PROJECT_ROOT), check=False,
                )
                if r2.returncode == 0:
                    _safe_print(f"    {_ok('Push exitoso')}")
                else:
                    _safe_print(f"    {_warn(f'Push fallo: {r2.stderr[:200]}')}")
        else:
            _safe_print(f"    {_warn(f'Error en commit: {r.stderr[:200]}')}")
            auto_committed = False
    except Exception as exc:  # noqa: BLE001
        _safe_print(f"    {_warn(f'Error en commit: {exc}')}")
        auto_committed = False

    return {
        "status": "ok",
        "auto_commit": auto_committed,
        "commit_message": clean_msg,
        "report": report,
    }


# =============================================================================
# Pre-commit & Watch pipelines
# =============================================================================


def _run_pre_commit_pipeline(skip_security: bool = False) -> int:
    """Fast, silent, non-interactive pipeline for pre-commit hooks.

    Args:
        skip_security: If True, skip the security scan phase (--quick mode).

    Returns:
        0 = clean, 1 = critical issues, 2 = warnings only
    """
    import subprocess as _subprocess

    start = time.time()
    has_warnings = False

    try:
        result = _subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True, text=True, timeout=15, cwd=str(PROJECT_ROOT), check=False,
        )
        staged = [f.strip() for f in result.stdout.split("\n") if f.strip()]
    except Exception:  # noqa: BLE001
        staged = []

    if not staged:
        _safe_print("    No staged files to check.")
        return 0

    scope_files = [f for f in staged if f.startswith(("harness/", ".opencode/"))]
    scope_files = [
        f for f in scope_files
        if not f.startswith("harness/db/") and "__pycache__" not in f and ".git/" not in f
    ]

    if not scope_files:
        _safe_print("    No relevant files in scope (harness/ or .opencode/).")
        return 0

    _safe_print(f"  Scoping {len(scope_files)} staged file(s) in scope...")
    for f in scope_files[:10]:
        _safe_print(f"    {f}")
    if len(scope_files) > 10:
        _safe_print(f"    ... and {len(scope_files) - 10} more")

    _safe_print(f"  {_bold('[Bug hunting]')}...")
    bugs = scan_for_bugs(directory=".", changed_files=scope_files)
    bugs = auto_fix_bugs(bugs, dry_run=True)
    critical_bugs = [b for b in bugs if b.severity == "critical"]
    major_bugs = [b for b in bugs if b.severity == "major"]
    minor_bugs = [b for b in bugs if b.severity == "minor"]

    if critical_bugs:
        _safe_print(f"    {_err(f'[CRITICAL] {len(critical_bugs)} bug(s) critico(s)')}")
        for b in critical_bugs[:5]:
            _safe_print(f"    {_err('[BUG]')} {b.file}:{b.line} - {b.message}")
    if major_bugs:
        _safe_print(f"    {_warn(f'[MAJOR] {len(major_bugs)} bug(s) major')}")
        has_warnings = True
    if minor_bugs:
        _safe_print(f"    {len(minor_bugs)} bug(s) minor")
        has_warnings = True
    if not critical_bugs and not major_bugs and not minor_bugs:
        _safe_print(f"    {_ok('0 issues')}")

    sec_critical_found = False
    if not skip_security:
        _safe_print(f"  {_bold('[Security scan]')}...")
        sec_findings = security_scan(directory=".", changed_files=scope_files)
        critical_sec = [s for s in sec_findings if s.severity == "critical"]
        major_sec = [s for s in sec_findings if s.severity == "major"]
        minor_sec = [s for s in sec_findings if s.severity == "minor"]

        if critical_sec:
            _safe_print(f"    {_err(f'[CRITICAL] {len(critical_sec)} secreto(s) encontrado(s)')}")
            for s in critical_sec[:5]:
                _safe_print(f"    {_err('[SECRET]')} {s.file}:{s.line} - {s.message}")
            sec_critical_found = True
        if major_sec:
            _safe_print(f"    {_warn(f'[MAJOR] {len(major_sec)} issue(s) de seguridad')}")
            has_warnings = True
        if minor_sec:
            _safe_print(f"    {len(minor_sec)} issue(s) de seguridad menores")
            has_warnings = True
        if not critical_sec and not major_sec and not minor_sec:
            _safe_print(f"    {_ok('0 issues')}")
    else:
        _safe_print(f"  {_bold('[Security scan]')}...")
        _safe_print(f"    {_warn('[SKIP]')} Security scan omitido (modo rapido).")

    _safe_print(f"  {_bold('[Token report]')}...")
    from .phase4_tokens import _estimate_tokens_from_git
    token_rep = _estimate_tokens_from_git()
    _safe_print(f"    Input: ~{token_rep.tokens_input_total:,} tokens / Output: ~{token_rep.tokens_output_total:,} tokens")

    elapsed = time.time() - start
    _safe_print(f"  Completed in {elapsed:.2f}s")

    if critical_bugs or sec_critical_found:
        _safe_print(f"\n  {_err('[ABORT]')} Critical issues found. Commit blocked.")
        _safe_print("  Fix issues or use `git commit --no-verify` to skip.")
        return 1
    if has_warnings:
        _safe_print(f"\n  {_warn('[WARN]')} Minor issues found. Commit allowed with --no-verify.")
        return 2
    _safe_print(f"\n  {_ok('[OK]')} All checks passed.")
    return 0


def _run_watch_pipeline() -> int:
    """Quick pipeline for --watch mode. Only phases 1, 2, 4."""
    start = time.time()
    changed_files = _get_git_uncommitted()
    if not changed_files:
        changed_files = _get_changed_files_since_last_commit()

    scope_files = [f for f in changed_files if f.startswith(("harness/", ".opencode/"))]
    scope_files = [
        f for f in scope_files
        if not f.startswith("harness/db/") and "__pycache__" not in f and ".git/" not in f
    ]
    if not scope_files:
        return 0

    bugs = scan_for_bugs(directory=".", changed_files=scope_files)
    critical_bugs = [b for b in bugs if b.severity == "critical"]
    major_bugs = [b for b in bugs if b.severity == "major"]
    bug_count = len(bugs)
    bug_summary = f"{bug_count} issues"
    if critical_bugs:
        bug_summary += f" ({len(critical_bugs)} critical)"
    _safe_print(f"  [Bug hunting]: {bug_summary}")
    for b in critical_bugs[:3]:
        _safe_print(f"    CRITICAL: {b.file}:{b.line} - {b.message[:80]}")
    for b in major_bugs[:3]:
        _safe_print(f"    MAJOR: {b.file}:{b.line} - {b.message[:80]}")

    sec_findings = security_scan(directory=".", changed_files=scope_files)
    critical_sec = [s for s in sec_findings if s.severity == "critical"]
    sec_count = len(sec_findings)
    sec_summary = f"{sec_count} issues"
    if critical_sec:
        sec_summary += f" ({len(critical_sec)} secrets)"
    _safe_print(f"  [Security scan]: {sec_summary}")
    for s in critical_sec[:3]:
        _safe_print(f"    SECRET: {s.file}:{s.line} - {s.message[:80]}")

    from .phase4_tokens import _estimate_tokens_from_git
    token_rep = _estimate_tokens_from_git()
    _safe_print(f"  [Tokens]: ~{token_rep.tokens_input_total:,} input / ~{token_rep.tokens_output_total:,} output")

    elapsed = time.time() - start
    _safe_print(f"  Done in {elapsed:.2f}s")
    return 0


# =============================================================================
# CLI entry point
# =============================================================================


def main() -> None:
    """CLI entry point for the end-of-iteration pipeline."""
    args = parse_args()

    if args.report:
        print_last_report()
        return
    if args.quick:
        run_quick_pipeline()
        return
    if args.auto:
        run_auto_pipeline()
        return
    if args.pre_commit:
        sys.exit(_run_pre_commit_pipeline(skip_security=args.quick))
    if args.watch:
        sys.exit(_run_watch_pipeline())

    run_pipeline(
        skip_bugs=args.skip_bugs,
        skip_security=args.skip_security,
        skip_docs=args.skip_docs,
        dry_run=args.dry_run,
    )
