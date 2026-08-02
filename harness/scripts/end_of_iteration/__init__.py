"""
end_of_iteration â€” Pipeline de fin de iteracion.

Package que reemplaza el monolito original, dividiendo la funcionalidad en
fases separadas y mÃ³dulos auxiliares (cli, display).

REFACTOR: Aplica patrÃ³n RECURSIVO para ejecutar fases en lugar de un loop for.
La funciÃ³n run_pipeline ejecuta fases recursivamente: cada fase retorna
un contexto que se pasa a la siguiente fase, eliminando ~50 lÃ­neas de
cÃ³digo secuencial repetitivo.

Uso:
    from harness.scripts.end_of_iteration import run_pipeline
    run_pipeline()
"""
from __future__ import annotations

import json
import sys
import time
from datetime import UTC, datetime
from typing import Any

from .cli import parse_args
from .config import (
    HARNESS_ROOT,
    PROJECT_ROOT,
    BugFinding,
    DocsStaleness,
    IterationReport,
    SecurityFinding,
    TokenReport,
    _bold,
    _cyan,
    _err,
    _get_changed_files_since_last_commit,
    _get_git_uncommitted,
    _ok,
    _print_banner,
    _safe_print,
    _warn,
)
from .display import (
    get_last_report,
    list_iteration_reports,
    print_last_report,
    show_iteration_diff,
    show_iteration_history,
)
from .phase1_bugs import auto_fix_bugs, scan_for_bugs
from .phase2_security import security_scan
from .phase3_docs import check_and_update_docs
from .phase4_tokens import calculate_iteration_cost
from .phase5_commit import interactive_commit, prepare_commit

__all__ = [
    "BugFinding",
    "DocsStaleness",
    "IterationReport",
    "SecurityFinding",
    "TokenReport",
    "auto_fix_bugs",
    "calculate_iteration_cost",
    "check_and_update_docs",
    "get_last_report",
    "interactive_commit",
    "list_iteration_reports",
    "main",
    "prepare_commit",
    "print_last_report",
    "run_auto_pipeline",
    "run_pipeline",
    "run_quick_pipeline",
    "scan_for_bugs",
    "security_scan",
    "show_iteration_diff",
    "show_iteration_history",
]


# =============================================================================
# Logging to LanceDB
# =============================================================================


def _save_report_to_lancedb(report: IterationReport) -> bool:
    """Save the iteration report to LanceDB (best-effort, silent fail)."""
    import numpy as np
    try:
        sys.path.insert(1, str(HARNESS_ROOT.parent))
        from harness.memory_rag.lance_vector_store import LanceVectorStore

        store = LanceVectorStore()
        report_id = f"iter_{int(time.time())}"
        existing = store.list_collections()

        if "iteration_reports" not in existing:
            import lancedb
            import pyarrow as pa
            db_path = store._uri if hasattr(store, '_uri') else str(store._db_path)
            db = lancedb.connect(db_path)
            schema = pa.schema([
                ("vector", pa.list_(pa.float32(), 384)),
                ("id", pa.string()), ("timestamp", pa.string()),
                ("bugs_found", pa.int32()), ("bugs_fixed", pa.int32()),
                ("bugs_needs_review", pa.int32()), ("security_issues", pa.int32()),
                ("secrets_found", pa.int32()), ("docs_updated", pa.int32()),
                ("docs_stale", pa.int32()), ("token_input", pa.int32()),
                ("token_output", pa.int32()), ("costo_estimado", pa.float64()),
                ("eficiencia", pa.string()), ("commit_message_suggested", pa.string()),
                ("files_changed", pa.string()), ("elapsed_seconds", pa.float64()),
            ])
            db.create_table("iteration_reports", schema=schema, mode="overwrite")

        vector = np.ones((1, 384), dtype=np.float32) * 0.001
        metadata = {
            "id": report_id, "timestamp": report.timestamp,
            "bugs_found": report.bugs_found, "bugs_fixed": report.bugs_fixed,
            "bugs_needs_review": report.bugs_needs_review,
            "security_issues": report.security_issues,
            "secrets_found": report.secrets_found,
            "docs_updated": report.docs_updated, "docs_stale": report.docs_stale,
            "token_input": report.token_report.tokens_input_total if report.token_report else 0,
            "token_output": report.token_report.tokens_output_total if report.token_report else 0,
            "costo_estimado": report.token_report.costo_estimado_usd if report.token_report else 0.0,
            "eficiencia": json.dumps(report.token_report.eficiencia if report.token_report else {}),
            "commit_message_suggested": report.commit_message_suggested[:500],
            "files_changed": json.dumps(report.files_changed),
            "elapsed_seconds": report.elapsed_seconds,
        }
        store.insert("iteration_reports", vector, [metadata])
        return True
    except Exception:  # noqa: BLE001
        return False


def _save_report_to_json(report: IterationReport) -> bool:
    """Save the iteration report as JSON in harness/db/iteration_reports/."""
    from dataclasses import asdict
    reports_dir = HARNESS_ROOT / "db" / "iteration_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(reports_dir.glob("report_*.json"))
    iter_num = len(existing) + 1
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    filename = f"report_{timestamp}_iter{iter_num:04d}.json"
    filepath = reports_dir / filename

    data = asdict(report)
    if data.get("token_report") and isinstance(data["token_report"], TokenReport):
        data["token_report"] = asdict(data["token_report"])

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        _safe_print(f"    {_ok('[OK]')} Reporte guardado: {filepath}")
        return True
    except Exception as exc:  # noqa: BLE001
        _safe_print(f"    {_warn('[WARN]')} No se pudo guardar reporte JSON: {exc}")
        return False


# =============================================================================
# Pipeline phases as callables
# =============================================================================


def _phase_bugs(context: dict[str, Any]) -> dict[str, Any]:
    """Phase 1: Bug Hunting."""
    report = context["report"]
    dry_run = context.get("dry_run", False)
    skip = context.get("skip_bugs", False)
    changed_files = context.get("changed_files", [])
    auto_commit = context.get("auto_commit", False)

    _print_banner("FASE 1: Bug Hunting", "\U0001F50D")
    if skip:
        _safe_print(f"    {_warn('[SKIP]')} Bug hunting omitido.")
        return context

    bugs = scan_for_bugs(directory=".", dry_run=dry_run, changed_files=changed_files)
    bugs = auto_fix_bugs(bugs, dry_run=dry_run)
    criticals = [b for b in bugs if b.severity == "critical"]
    majors = [b for b in bugs if b.severity == "major"]
    fixed = [b for b in bugs if b.status == "fixed"]
    needs_review = [b for b in bugs if b.status == "needs_review"]

    _safe_print(f"    {len(bugs)} bugs encontrados "
          f"({len(criticals)} critical, {len(majors)} major, "
          f"{len(bugs) - len(criticals) - len(majors)} minor)")
    _safe_print(f"    {len(fixed)} auto-fixed, {len(needs_review)} needs review")
    for b in criticals[:5]:
        _safe_print(f"    {_err('[CRITICAL]')} {b.file}:{b.line} - {b.message}")
    for b in majors[:5]:
        _safe_print(f"    {_warn('[MAJOR]')} {b.file}:{b.line} - {b.message}")
    for b in needs_review[:5]:
        _safe_print(f"    {_warn('[REVIEW]')} {b.file}:{b.line} - {b.message}")

    if criticals and not dry_run:
        if auto_commit:
            _safe_print(f"\n    {_err('[BLOCKED]')} {len(criticals)} bug(s) critico(s) - se omite commit automatico.")
        else:
            _safe_print(f"\n    {_err('[ABORT]')} {len(criticals)} bug(s) critico(s) encontrados.")
            sys.exit(1)

    report.bugs_found = len(bugs)
    report.bugs_critical = len(criticals)
    report.bugs_major = len(majors)
    report.bugs_fixed = len(fixed)
    report.bugs_needs_review = len(needs_review)

    context["bugs"] = bugs
    context["sec_findings"] = context.get("sec_findings", [])
    return context


def _phase_security(context: dict[str, Any]) -> dict[str, Any]:
    """Phase 2: Security Review."""
    report = context["report"]
    skip = context.get("skip_security", False)
    changed_files = context.get("changed_files", [])

    _print_banner("FASE 2: Security Scan", "\U0001F6E1\uFE0F")
    if skip:
        _safe_print(f"    {_warn('[SKIP]')} Security scan omitido.")
        return context

    sec_findings = security_scan(directory=".", changed_files=changed_files)
    critical_sec = [s for s in sec_findings if s.severity == "critical"]
    major_sec = [s for s in sec_findings if s.severity == "major"]
    minor_sec = [s for s in sec_findings if s.severity == "minor"]

    _safe_print(f"    {len(sec_findings)} hallazgos de seguridad "
          f"({len(critical_sec)} critical, {len(major_sec)} major, {len(minor_sec)} minor)")
    if critical_sec:
        _safe_print(f"\n    {_err('[!] SECRETOS ENCONTRADOS')}")
        for s in critical_sec:
            _safe_print(f"    {_err('[SECRET]')} {s.file}:{s.line} - {s.message}")
        _safe_print(f"\n    {_warn('[SUGGEST]')} Usa variables de entorno en lugar de hardcodear.")
    for s in major_sec:
        _safe_print(f"    {_warn('[MAJOR]')} {s.file}:{s.line} - {s.message}")
    for s in minor_sec:
        _safe_print(f"    {'[MINOR]'} {s.file}:{s.line} - {s.message}")

    if critical_sec:
        _safe_print(f"\n    {_warn('[WARN]')} Secretos encontrados pero NO se bloquea el pipeline.")

    report.security_issues = len(sec_findings)
    report.secrets_found = len(critical_sec)
    context["sec_findings"] = sec_findings
    return context


def _phase_docs(context: dict[str, Any]) -> dict[str, Any]:
    """Phase 3: Documentation Update."""
    report = context["report"]
    skip = context.get("skip_docs", False)
    dry_run = context.get("dry_run", False)
    changed_files = context.get("changed_files", [])

    _print_banner("FASE 3: Docs Update", "\U0001F4C4")
    if skip:
        _safe_print(f"    {_warn('[SKIP]')} Docs update omitido.")
        return context

    docs_stale, docs_updated_count = check_and_update_docs(changed_files, dry_run=dry_run)
    _safe_print(f"    {len(docs_stale)} archivo(s) de docs desactualizado(s)")
    for d in docs_stale:
        _safe_print(f"    {_warn('[STALE]')} {d.module_path} -> {d.docs_path} ({d.message})")
    if docs_updated_count > 0:
        _safe_print(f"    {_ok('[OK]')} Documentacion procesada.")

    report.docs_updated = docs_updated_count
    report.docs_stale = len(docs_stale)
    context["docs_stale"] = docs_stale
    return context


def _phase_tokens(context: dict[str, Any]) -> dict[str, Any]:
    """Phase 4: Token Report."""
    report = context["report"]
    changed_files = context.get("changed_files", [])

    _print_banner("FASE 4: Token Report", "\U0001F4B0")
    token_rep = calculate_iteration_cost()
    report.token_report = token_rep

    _safe_print(f"    Archivos cambiados:   {len(changed_files)}")
    _safe_print(f"    Prompts enviados:     {token_rep.prompts_enviados}")
    _safe_print(f"    Input tokens:         {token_rep.tokens_input_total:>10,}")
    _safe_print(f"    Output tokens:        {token_rep.tokens_output_total:>10,}")
    _safe_print(f"    Ahorro por routing:   {token_rep.tokens_ahorrados_por_routing:>10,} (~65%)")
    _safe_print(f"    Ahorro por skills:    {token_rep.tokens_ahorrados_por_skills:>10,} (~60%)")
    _safe_print(f"    Ahorro por HITL:      {token_rep.tokens_ahorrados_por_hitl:>10,}")
    _safe_print(f"    Costo estimado:       ${token_rep.costo_estimado_usd:.2f}")
    if token_rep.eficiencia:
        _safe_print()
        for k, v in token_rep.eficiencia.items():
            _safe_print(f"    {k}: {_ok(v) if '%' in v and int(v.split('%')[0]) > 50 else v}")

    context["token_rep"] = token_rep
    return context


def _phase_commit(context: dict[str, Any]) -> dict[str, Any]:
    """Phase 5: Commit Seguro."""
    report = context["report"]
    dry_run = context.get("dry_run", False)
    auto_commit = context.get("auto_commit", False)
    bugs = context.get("bugs", [])
    sec_findings = context.get("sec_findings", [])
    token_rep = context.get("token_rep")
    docs_stale = context.get("docs_stale", [])

    commit_msg = prepare_commit(bugs, sec_findings, token_rep, docs_stale)
    report.commit_message_suggested = commit_msg

    if auto_commit:
        _print_banner("FASE 5: Commit Message", "\U0001F4DD")
        first_line = commit_msg.split('\n')[0].strip() if commit_msg else "(empty)"
        _safe_print(f"    {first_line}")
    elif dry_run:
        _print_banner("FASE 5: Commit (DRY-RUN)", "\U0001F4DD")
        _safe_print(commit_msg)
    else:
        interactive_commit(commit_msg)

    return context


# ---------------------------------------------------------------------------
# Pipeline phases list (orden de ejecucion)
# ---------------------------------------------------------------------------

PHASES = [
    ("bugs", _phase_bugs),
    ("security", _phase_security),
    ("docs", _phase_docs),
    ("tokens", _phase_tokens),
    ("commit", _phase_commit),
]


# =============================================================================
# Recursive Pipeline Execution
# =============================================================================


def run_pipeline_recursive(phases, index: int, context: dict[str, Any]) -> dict[str, Any]:
    """
    Ejecuta fases recursivamente en lugar de un loop for.
    
    PatrÃ³n RECURSIVO: cada fase procesa el contexto y lo pasa a la siguiente.
    Cuando no hay mÃ¡s fases, retorna el contexto final.
    
    Args:
        phases: Lista de tuplas (nombre, funcion_fase)
        index: Indice actual en la lista de fases
        context: Dict con estado compartido entre fases
    
    Returns:
        Contexto final despuÃ©s de ejecutar todas las fases
    """
    # Caso base: no hay mÃ¡s fases
    if index >= len(phases):
        return context

    # Caso recursivo: ejecutar fase actual y pasar a la siguiente
    phase_name, phase_func = phases[index]
    try:
        context = phase_func(context)
    except Exception as exc:
        _safe_print(f"  {_err(f'[ERROR] Fase {phase_name}: {exc}')}")
        if not context.get("auto_commit", False):
            raise

    return run_pipeline_recursive(phases, index + 1, context)


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


if __name__ == "__main__":
    main()
