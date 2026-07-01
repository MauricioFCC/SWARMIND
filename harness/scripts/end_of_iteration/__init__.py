"""
end_of_iteration — Pipeline de fin de iteracion.

Package que reemplaza el monolito original, dividiendo la funcionalidad en
fases separadas, cada una < 300 lineas.

Uso:
    from harness.scripts.end_of_iteration import run_pipeline
    run_pipeline()
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import (
    BugFinding, SecurityFinding, DocsStaleness, TokenReport, IterationReport,
    HARNESS_ROOT, PROJECT_ROOT, _safe_print, _ok, _err, _warn, _bold, _cyan,
    _print_banner, _supports_unicode, _load_config,
    _get_changed_files_since_last_commit, _get_git_uncommitted,
)
from .phase1_bugs import scan_for_bugs, auto_fix_bugs
from .phase2_security import security_scan
from .phase3_docs import check_and_update_docs
from .phase4_tokens import calculate_iteration_cost
from .phase5_commit import prepare_commit, interactive_commit

__all__ = [
    "BugFinding", "SecurityFinding", "DocsStaleness", "TokenReport",
    "IterationReport", "scan_for_bugs", "auto_fix_bugs", "security_scan",
    "check_and_update_docs", "calculate_iteration_cost", "prepare_commit",
    "interactive_commit", "run_pipeline", "run_quick_pipeline",
    "run_auto_pipeline", "print_last_report", "get_last_report", "main",
    "list_iteration_reports", "show_iteration_history", "show_iteration_diff",
]


# =============================================================================
# Logging to LanceDB
# =============================================================================


def _save_report_to_lancedb(report: IterationReport) -> bool:
    """Save the iteration report to LanceDB (best-effort, silent fail)."""
    import numpy as np
    try:
        sys.path.insert(0, str(HARNESS_ROOT.parent))
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
    except Exception:
        return False


# =============================================================================
# Report persistence
# =============================================================================


def _save_report_to_json(report: IterationReport) -> bool:
    """Save the iteration report as JSON in harness/db/iteration_reports/."""
    from dataclasses import asdict
    reports_dir = HARNESS_ROOT / "db" / "iteration_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(reports_dir.glob("report_*.json"))
    iter_num = len(existing) + 1
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
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
    except Exception as exc:
        _safe_print(f"    {_warn('[WARN]')} No se pudo guardar reporte JSON: {exc}")
        return False


def _get_last_report_path() -> Optional[Path]:
    """Get the path to the most recent JSON report."""
    reports_dir = HARNESS_ROOT / "db" / "iteration_reports"
    if not reports_dir.exists():
        return None
    existing = sorted(reports_dir.glob("report_*.json"))
    return existing[-1] if existing else None


def print_last_report() -> None:
    """Print the last saved report in a human-readable format."""
    report_path = _get_last_report_path()
    if report_path is None:
        _safe_print(f"  {_warn('[WARN]')} No hay reportes de iteracion guardados.")
        return
    try:
        with open(report_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        _safe_print(f"  {_err('[ERROR]')} No se pudo leer el reporte: {exc}")
        return

    _safe_print()
    _print_banner("ULTIMO REPORTE DE ITERACION", "\U0001F4CB")
    _safe_print(f"  Timestamp:    {data.get('timestamp', 'N/A')}")
    _safe_print(f"  Duracion:     {data.get('elapsed_seconds', 0):.2f}s")
    _safe_print(f"  Bugs:         {data.get('bugs_found', 0)} encontrados, "
          f"{data.get('bugs_fixed', 0)} fixed, {data.get('bugs_needs_review', 0)} needs review")
    _safe_print(f"  Seguridad:    {data.get('security_issues', 0)} issues, "
          f"{data.get('secrets_found', 0)} secrets")
    _safe_print(f"  Docs:         {data.get('docs_updated', 0)} updated, "
          f"{data.get('docs_stale', 0)} stale")
    tr = data.get('token_report', {}) or {}
    _safe_print(f"  Tokens in:    {tr.get('tokens_input_total', 0):,}")
    _safe_print(f"  Tokens out:   {tr.get('tokens_output_total', 0):,}")
    _safe_print(f"  Costo:        ${tr.get('costo_estimado_usd', 0):.2f}")
    files_changed = data.get('files_changed', []) or []
    _safe_print(f"  Archivos:     {len(files_changed)} cambiados")
    _safe_print(f"  Reporte:      {report_path}")


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
    report = IterationReport(timestamp=datetime.now(timezone.utc).isoformat())

    changed_files = _get_changed_files_since_last_commit()
    if not changed_files:
        changed_files = _get_git_uncommitted()
    report.files_changed = changed_files

    if dry_run:
        _safe_print(f"  {_cyan('[DRY-RUN]')} Modo simulado — no se modificaran archivos")
    _safe_print(f"  Archivos cambiados: {len(changed_files)}")
    if changed_files:
        for f in changed_files[:10]:
            _safe_print(f"    {f}")
        if len(changed_files) > 10:
            _safe_print(f"    ... y {len(changed_files) - 10} mas")

    # Phase 1: Bug Hunting
    bugs: List[BugFinding] = []
    if not skip_bugs:
        _print_banner("FASE 1: Bug Hunting", "\U0001F50D")
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
            _safe_print(f"    {_err('[CRITICAL]')} {b.file}:{b.line} — {b.message}")
        for b in majors[:5]:
            _safe_print(f"    {_warn('[MAJOR]')} {b.file}:{b.line} — {b.message}")
        for b in needs_review[:5]:
            _safe_print(f"    {_warn('[REVIEW]')} {b.file}:{b.line} — {b.message}")
        if criticals and not dry_run:
            if auto_commit:
                _safe_print(f"\n    {_err('[BLOCKED]')} {len(criticals)} bug(s) critico(s) — se omite commit automatico.")
                report.bugs_critical = len(criticals)
                report.bugs_major = len(majors)
            else:
                _safe_print(f"\n    {_err('[ABORT]')} {len(criticals)} bug(s) critico(s) encontrados.")
                sys.exit(1)
        report.bugs_found = len(bugs)
        report.bugs_critical = len(criticals)
        report.bugs_major = len(majors)
        report.bugs_fixed = len(fixed)
        report.bugs_needs_review = len(needs_review)
    else:
        _print_banner("FASE 1: Bug Hunting", "\U0001F50D")
        _safe_print(f"    {_warn('[SKIP]')} Bug hunting omitido.")

    # Phase 2: Security Review
    sec_findings: List[SecurityFinding] = []
    if not skip_security:
        _print_banner("FASE 2: Security Scan", "\U0001F6E1\uFE0F")
        sec_findings = security_scan(directory=".", changed_files=changed_files)
        critical_sec = [s for s in sec_findings if s.severity == "critical"]
        major_sec = [s for s in sec_findings if s.severity == "major"]
        minor_sec = [s for s in sec_findings if s.severity == "minor"]

        _safe_print(f"    {len(sec_findings)} hallazgos de seguridad "
              f"({len(critical_sec)} critical, {len(major_sec)} major, {len(minor_sec)} minor)")
        if critical_sec:
            _safe_print(f"\n    {_err('[!] SECRETOS ENCONTRADOS')}")
            for s in critical_sec:
                _safe_print(f"    {_err('[SECRET]')} {s.file}:{s.line} — {s.message}")
            _safe_print(f"\n    {_warn('[SUGGEST]')} Usa variables de entorno en lugar de hardcodear.")
        for s in major_sec:
            _safe_print(f"    {_warn('[MAJOR]')} {s.file}:{s.line} — {s.message}")
        for s in minor_sec:
            _safe_print(f"    {'[MINOR]'} {s.file}:{s.line} — {s.message}")
        if critical_sec:
            _safe_print(f"\n    {_warn('[WARN]')} Secretos encontrados pero NO se bloquea el pipeline.")
        report.security_issues = len(sec_findings)
        report.secrets_found = len(critical_sec)
    else:
        _print_banner("FASE 2: Security Scan", "\U0001F6E1\uFE0F")
        _safe_print(f"    {_warn('[SKIP]')} Security scan omitido.")

    # Phase 3: Documentation Update
    docs_stale: List[DocsStaleness] = []
    docs_updated_count = 0
    if not skip_docs:
        _print_banner("FASE 3: Docs Update", "\U0001F4C4")
        docs_stale, docs_updated_count = check_and_update_docs(changed_files, dry_run=dry_run)
        _safe_print(f"    {len(docs_stale)} archivo(s) de docs desactualizado(s)")
        for d in docs_stale:
            _safe_print(f"    {_warn('[STALE]')} {d.module_path} → {d.docs_path} ({d.message})")
        if docs_updated_count > 0:
            _safe_print(f"    {_ok('[OK]')} Documentacion procesada.")
        report.docs_updated = docs_updated_count
        report.docs_stale = len(docs_stale)
    else:
        _print_banner("FASE 3: Docs Update", "\U0001F4C4")
        _safe_print(f"    {_warn('[SKIP]')} Docs update omitido.")

    # Phase 4: Token Report
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

    # Phase 5: Commit Seguro
    commit_msg = prepare_commit(bugs, sec_findings, token_rep, docs_stale)
    report.commit_message_suggested = commit_msg

    if auto_commit:
        # In auto-commit mode, just print the message, don't interact
        _print_banner("FASE 5: Commit Message", "\U0001F4DD")
        # Extract first line only for display
        first_line = commit_msg.split('\n')[0].strip() if commit_msg else "(empty)"
        _safe_print(f"    {first_line}")
    elif dry_run:
        _print_banner("FASE 5: Commit (DRY-RUN)", "\U0001F4DD")
        _safe_print(commit_msg)
    else:
        interactive_commit(commit_msg)

    report.elapsed_seconds = time.time() - start_time
    _safe_print(f"\n  Pipeline completado en {report.elapsed_seconds:.2f}s")

    _save_report_to_json(report)
    _save_report_to_lancedb(report)
    return report


# =============================================================================
# Modo rápido y automático
# =============================================================================


def run_quick_pipeline() -> Dict[str, Any]:
    """Modo rápido: solo bugs + tokens, salta security, docs y commit.

    Tiempo objetivo < 2s. Escanea solo archivos staged.
    Returns dict with status info.
    """
    start_time = time.time()

    _safe_print()
    _safe_print(f"  {_bold('⚡ Modo rápido activado')}")
    _safe_print()

    # ── Obtener archivos staged ──────────────────────────────────────────
    import subprocess as _subprocess
    try:
        result = _subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True, text=True, timeout=15, cwd=str(PROJECT_ROOT),
        )
        staged = [f.strip() for f in result.stdout.split("\n") if f.strip()]
    except Exception:
        staged = []

    if not staged:
        staged = _get_git_uncommitted()

    scope_files = [
        f for f in staged
        if not f.startswith("harness/db/") and "__pycache__" not in f and ".git/" not in f
    ]

    # ── Fase 1: Bug Hunting (rápido, solo staged) ────────────────────────
    _safe_print(f"  {_bold('🔍 Bug Hunting...')}")
    bugs = scan_for_bugs(directory=".", changed_files=scope_files)
    bugs = auto_fix_bugs(bugs, dry_run=True)
    criticals = [b for b in bugs if b.severity == "critical"]
    majors = [b for b in bugs if b.severity == "major"]
    minors = [b for b in bugs if b.severity == "minor"]

    _safe_print(f"    {len(criticals)} critical, {len(majors)} major, {len(minors)} minor")
    for b in criticals[:5]:
        _safe_print(f"    {_err('[BUG]')} {b.file}:{b.line} — {b.message}")
    for b in majors[:5]:
        _safe_print(f"    {_warn('[BUG]')} {b.file}:{b.line} — {b.message}")

    # ── Fase 4: Token Report ────────────────────────────────────────────
    _safe_print(f"\n  {_bold('💰 Token Report...')}")
    from .phase4_tokens import _estimate_tokens_from_git
    token_rep = _estimate_tokens_from_git()
    _safe_print(f"    Input: ~{token_rep.tokens_input_total:,} tokens")
    _safe_print(f"    Output: ~{token_rep.tokens_output_total:,} tokens")

    elapsed = time.time() - start_time

    if criticals:
        _safe_print(f"\n    {_err('❌ Criticals encontrados. Revisar manualmente.')}")
        for b in criticals[:5]:
            _safe_print(f"    {_err('[CRITICAL]')} {b.file}:{b.line} — {b.message}")
        status = "blocked"
    else:
        _safe_print(f"\n    {_ok('✅ Modo rápido completado.')}")
        status = "ok"

    _safe_print(f"    ({elapsed:.2f}s)")
    return {"status": status, "criticals": len(criticals), "bugs": len(bugs), "elapsed": elapsed}


def run_auto_pipeline() -> Dict[str, Any]:
    """Modo automático: ejecuta pipeline completo, hace commit si no hay criticals.

    Si hay criticals, aborta y muestra los issues para revisión manual.
    Si no hay criticals, hace commit automático con el mensaje generado.
    """
    _safe_print()
    _safe_print(f"  {_bold('🤖 Modo automático activado')}")
    _safe_print()

    # ── Fases 1-4: Pipeline completo en modo auto_commit ────────────────
    report = run_pipeline(auto_commit=True)

    blocked = report.bugs_critical > 0

    if blocked:
        _safe_print(f"\n    {_err('❌ Pipeline bloqueado por issues críticos. No se hará commit.')}")
        return {
            "status": "blocked",
            "criticals": report.bugs_critical,
            "report": report,
            "commit_message": report.commit_message_suggested,
        }

    # ── Fase 5: Auto-commit ─────────────────────────────────────────────
    _safe_print(f"\n  {_bold('📝 Preparando commit automático...')}")
    commit_msg = report.commit_message_suggested

    if not commit_msg or not commit_msg.strip():
        _safe_print(f"    {_warn('⚠️ No se generó mensaje de commit. Omitiendo.')}")
        return {"status": "ok", "auto_commit": False, "report": report}

    # Limpiar líneas de comentario del mensaje
    clean_lines = [l for l in commit_msg.split('\n') if not l.strip().startswith('#')]
    clean_msg = '\n'.join(l for l in clean_lines if l.strip())

    if not clean_msg:
        clean_msg = "chore: actualización automática"

    import subprocess
    try:
        r = subprocess.run(
            ["git", "commit", "-m", clean_msg],
            capture_output=True, text=True, timeout=30, cwd=str(PROJECT_ROOT),
        )
        if r.returncode == 0:
            _safe_print(f"    {_ok('✅ Commit automático exitoso')}")
            auto_committed = True

            # Push opcional
            _safe_print()
            try:
                push = input(f"  {_bold('¿Hacer push automático?')} [y/N]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                push = ""
            if push == "y":
                r2 = subprocess.run(
                    ["git", "push"], capture_output=True, text=True, timeout=60,
                    cwd=str(PROJECT_ROOT),
                )
                if r2.returncode == 0:
                    _safe_print(f"    {_ok('✅ Push exitoso')}")
                else:
                    _safe_print(f"    {_warn(f'⚠️ Push falló: {r2.stderr[:200]}')}")
        else:
            _safe_print(f"    {_warn(f'⚠️ Error en commit: {r.stderr[:200]}')}")
            auto_committed = False
    except Exception as exc:
        _safe_print(f"    {_warn(f'⚠️ Error en commit: {exc}')}")
        auto_committed = False

    return {
        "status": "ok",
        "auto_commit": auto_committed,
        "commit_message": clean_msg,
        "report": report,
    }


def get_last_report() -> Optional[Dict[str, Any]]:
    """Retrieve the last saved iteration report from JSON."""
    report_path = _get_last_report_path()
    if report_path is None:
        _safe_print(f"  {_warn('[WARN]')} No hay reportes de iteracion guardados.")
        return None
    try:
        with open(report_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        _safe_print(f"  Error al recuperar report: {exc}")
        return None


# =============================================================================
# Report history browsing (CLI-friendly)
# =============================================================================


def list_iteration_reports(limit: int = 10) -> list[dict]:
    """
    Lista los últimos N reports de iteración desde iteration_reports/.

    Returns:
        Lista de dicts con timestamp, status, bugs, tokens, commit.
        Cada dict incluye _file y _path con metadata del archivo.
    """
    reports_dir = HARNESS_ROOT / "db" / "iteration_reports"
    if not reports_dir.exists():
        return []

    reports: list[dict] = []
    # Sort newest first, take top `limit` (if limit > 0)
    all_files = sorted(reports_dir.glob("report_*.json"), reverse=True)
    if limit > 0:
        all_files = all_files[:limit]

    for f in all_files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            data["_file"] = f.name
            data["_path"] = str(f)
            reports.append(data)
        except (json.JSONDecodeError, OSError):
            continue

    return reports


def show_iteration_history(limit: int = 10):
    """Muestra timeline de iteraciones en consola.

    Args:
        limit: Número de iteraciones a mostrar. Usa 0 para mostrar todas.
    """
    icon = "" if not _supports_unicode() else "\U0001F4CB"
    sep = "=" if not _supports_unicode() else "\u2500"

    # Para 'all' o sin límite, pasamos 0 que significa ilimitado
    actual_limit = limit if limit > 0 else None
    reports = list_iteration_reports(limit if limit > 0 else 0)

    if not reports:
        _safe_print()
        _safe_print(f"  {_warn('[WARN]')} No hay reports de iteracion aun.")
        _safe_print(f"  Ejecuta: {_bold('!iteration end')}")
        return

    if actual_limit is not None and len(reports) < len(list_iteration_reports(0)):
        total_reports = len(list_iteration_reports(0))
        _safe_print(f"\n  {_bold(f'{icon} Historial de Iteraciones (mostrando {len(reports)} de {total_reports})')}:")
    else:
        _safe_print(f"\n  {_bold(f'{icon} Historial de Iteraciones ({len(reports)})')}:")

    # Cabecera
    _safe_print(f"  {'#':<5} {'Fecha':<22} {'Bugs':<22} {'Tokens':<24} {'Estado':<10}")
    _safe_print(f"  {sep * 75}")

    for i, r in enumerate(reports, 1):
        fecha = r.get("timestamp", "?")[:19] if isinstance(r.get("timestamp"), str) else "?"
        tc = r.get("bugs_critical", r.get("bugs_found", 0))
        tm = r.get("bugs_major", 0)
        tmn = r.get("bugs_minor", 0)
        # Fallback: si bugs_minor no esta reportado directamente, lo calculamos
        if not tmn:
            tmn = max(0, r.get("bugs_found", 0) - tc - tm)

        bugs = f"{tc}C/{tm}M/{tmn}m"

        # Token data: puede estar anidado en token_report o plano
        tr = r.get("token_report") or {}
        if isinstance(tr, dict):
            tin = tr.get("tokens_input_total", 0)
            tout = tr.get("tokens_output_total", 0)
        else:
            tin = r.get("token_input", 0)
            tout = r.get("token_output", 0)
        tokens = f"~{tin:,}in/~{tout:,}out"

        status = r.get("status", "ok")

        _safe_print(f"  #{i:<3} {fecha:<22} {bugs:<22} {tokens:<24} {status:<10}")

    if limit > 10 or limit == 0:
        _safe_print()
    elif len(reports) >= limit:
        _safe_print()
        _safe_print(f"  Usa {_bold('!iteration history --all')} para ver todas.")
    _safe_print(f"  Usa {_bold('!iteration diff --last')} para ver detalles de la ultima.")
    _safe_print(f"  Usa {_bold('!iteration diff --n 3')} para ver la iteracion #3.")


def show_iteration_diff(n: int = 1):
    """Muestra el diff detallado de la iteracion N (1=ultima).

    Args:
        n: Numero de iteracion. 1 = ultima, 2 = penultima, etc.
    """
    # Necesitamos suficientes reports para indexar el n-esimo
    reports = list_iteration_reports(n)

    if not reports:
        _safe_print()
        _safe_print(f"  {_warn('[WARN]')} No hay reports de iteracion.")
        _safe_print(f"  Ejecuta: {_bold('!iteration end')}")
        return

    # reports esta ordenado newest-first. Indice n-1 para el n-esimo
    idx = min(n - 1, len(reports) - 1)
    r = reports[idx]

    timestamp_raw = r.get("timestamp", "?")
    if isinstance(timestamp_raw, str):
        timestamp_display = timestamp_raw[:19]
    else:
        timestamp_display = str(timestamp_raw)

    icon_detail = "" if not _supports_unicode() else "\U0001F4CB"
    sep_double = "=" if not _supports_unicode() else "\u2550"

    _safe_print(f"\n  {_bold(f'{icon_detail} Detalle de Iteracion')}: {timestamp_display}")
    _safe_print(f"  {sep_double * 60}")

    # ── Bugs ──
    tc = r.get("bugs_critical", 0)
    tm = r.get("bugs_major", 0)
    tmn = r.get("bugs_minor", 0)
    bugs_found = r.get("bugs_found", 0)
    bugs_fixed = r.get("bugs_fixed", 0)
    bugs_review = r.get("bugs_needs_review", 0)

    icon_bug = "" if not _supports_unicode() else "\U0001F50D"
    _safe_print(f"\n  {icon_bug:<4} Bug Hunting:")
    _safe_print(f"     Encontrados:  {bugs_found}")
    _safe_print(f"     Critical:     {_err(str(tc)) if tc else tc}")
    _safe_print(f"     Major:        {_warn(str(tm)) if tm else tm}")
    _safe_print(f"     Minor:        {tmn}")
    _safe_print(f"     Auto-fixed:   {bugs_fixed}")
    _safe_print(f"     Needs review: {bugs_review}")

    # ── Security ──
    icon_sec = "" if not _supports_unicode() else "\U0001F6E1\uFE0F"
    sec_issues = r.get("security_issues", 0)
    secrets = r.get("secrets_found", 0)
    _safe_print(f"\n  {icon_sec:<4} Security:")
    _safe_print(f"     Issues:  {sec_issues}")
    if secrets:
        _safe_print(f"     Secrets: {_err(str(secrets))}")
    else:
        _safe_print(f"     Secrets: {secrets}")

    # ── Docs ──
    docs_upd = r.get("docs_updated", 0)
    docs_stale = r.get("docs_stale", 0)
    icon_docs = "" if not _supports_unicode() else "\U0001F4C4"
    _safe_print(f"\n  {icon_docs:<4} Docs:")
    _safe_print(f"     Updated: {docs_upd}")
    _safe_print(f"     Stale:   {docs_stale}")

    # ── Tokens ──
    tr = r.get("token_report") or {}
    if isinstance(tr, dict):
        tin = tr.get("tokens_input_total", 0)
        tout = tr.get("tokens_output_total", 0)
        cost = tr.get("costo_estimado_usd", 0)
        routing_savings = tr.get("tokens_ahorrados_por_routing", 0)
        skills_savings = tr.get("tokens_ahorrados_por_skills", 0)
        hitl_savings = tr.get("tokens_ahorrados_por_hitl", 0)
        eficiencia = tr.get("eficiencia", {})
    else:
        tin = r.get("token_input", 0)
        tout = r.get("token_output", 0)
        cost = r.get("costo_estimado", 0)
        routing_savings = r.get("routing_savings", 0)
        skills_savings = r.get("skills_savings", 0)
        hitl_savings = 0
        eficiencia = {}

    icon_money = "" if not _supports_unicode() else "\U0001F4B0"
    _safe_print(f"\n  {icon_money:<4} Token Report:")
    _safe_print(f"     Input:  ~{tin:,} tokens")
    _safe_print(f"     Output: ~{tout:,} tokens")
    _safe_print(f"     Costo:  ${cost:.4f}")
    if routing_savings:
        _safe_print(f"     Ahorro routing: {routing_savings:,} tokens (~65%)")
    if skills_savings:
        _safe_print(f"     Ahorro skills:  {skills_savings:,} tokens (~60%)")
    if hitl_savings:
        _safe_print(f"     Ahorro HITL:    {hitl_savings:,} tokens")
    if eficiencia:
        _safe_print(f"     Eficiencia:")
        for k, v in eficiencia.items():
            display = v
            if isinstance(v, str) and '%' in v:
                try:
                    pct = int(v.split('%')[0])
                    display = _ok(v) if pct > 50 else _warn(v)
                except (ValueError, IndexError):
                    pass
            _safe_print(f"       {k}: {display}")

    # ── Duracion ──
    elapsed = r.get("elapsed_seconds", 0)
    icon_time = "" if not _supports_unicode() else "\u23F1\uFE0F"
    _safe_print(f"\n  {icon_time:<4} Duracion: {elapsed:.2f}s")

    # ── Commit ──
    commit = r.get("commit_message_suggested", "") or ""
    if commit:
        icon_commit = "" if not _supports_unicode() else "\U0001F4DD"
        _safe_print(f"\n  {icon_commit:<4} Commit sugerido:")
        # Mostrar primeras 200 chars (ya esta truncado en el reporte)
        first_line = commit.split('\n')[0].strip()
        _safe_print(f"     {first_line}")
        if len(commit) > 200:
            _safe_print(f"     ... (commit message truncated)")

    # ── Archivos ──
    files = r.get("files_changed", []) or []
    if files:
        icon_files = "" if not _supports_unicode() else "\U0001F4C4"
        _safe_print(f"\n  {icon_files:<4} Archivos ({len(files)}):")
        for f in files[:10]:
            _safe_print(f"     {f}")
        if len(files) > 10:
            _safe_print(f"     ... y {len(files) - 10} mas")

    # ── Archivo fuente ──
    icon_save = "" if not _supports_unicode() else "\U0001F4BE"
    _safe_print(f"\n  {icon_save:<4} Reporte: {r.get('_file', '?')}")


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
            capture_output=True, text=True, timeout=15, cwd=str(PROJECT_ROOT),
        )
        staged = [f.strip() for f in result.stdout.split("\n") if f.strip()]
    except Exception:
        staged = []

    if not staged:
        _safe_print(f"    No staged files to check.")
        return 0

    scope_files = [f for f in staged if f.startswith("harness/") or f.startswith(".opencode/")]
    scope_files = [
        f for f in scope_files
        if not f.startswith("harness/db/") and "__pycache__" not in f and ".git/" not in f
    ]

    if not scope_files:
        _safe_print(f"    No relevant files in scope (harness/ or .opencode/).")
        return 0

    _safe_print(f"  Scoping {len(scope_files)} staged file(s) in scope...")
    for f in scope_files[:10]:
        _safe_print(f"    {f}")
    if len(scope_files) > 10:
        _safe_print(f"    ... and {len(scope_files) - 10} more")

    # Phase 1: Bug hunting (staged files only)
    _safe_print(f"  {_bold('[Bug hunting]')}...")
    bugs = scan_for_bugs(directory=".", changed_files=scope_files)
    bugs = auto_fix_bugs(bugs, dry_run=True)
    critical_bugs = [b for b in bugs if b.severity == "critical"]
    major_bugs = [b for b in bugs if b.severity == "major"]
    minor_bugs = [b for b in bugs if b.severity == "minor"]

    if critical_bugs:
        _safe_print(f"    {_err(f'[CRITICAL] {len(critical_bugs)} bug(s) critico(s)')}")
        for b in critical_bugs[:5]:
            _safe_print(f"    {_err('[BUG]')} {b.file}:{b.line} — {b.message}")
    if major_bugs:
        _safe_print(f"    {_warn(f'[MAJOR] {len(major_bugs)} bug(s) major')}")
        has_warnings = True
    if minor_bugs:
        _safe_print(f"    {len(minor_bugs)} bug(s) minor")
        has_warnings = True
    if not critical_bugs and not major_bugs and not minor_bugs:
        _safe_print(f"    {_ok('0 issues')}")

    # Phase 2: Security scan (staged files only) — skipped in quick mode
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
                _safe_print(f"    {_err('[SECRET]')} {s.file}:{s.line} — {s.message}")
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
        _safe_print(f"    {_warn('[SKIP]')} Security scan omitido (modo rápido).")

    # Phase 4: Token report
    _safe_print(f"  {_bold('[Token report]')}...")
    from .phase4_tokens import _estimate_tokens_from_git
    token_rep = _estimate_tokens_from_git()
    _safe_print(f"    Input: ~{token_rep.tokens_input_total:,} tokens / Output: ~{token_rep.tokens_output_total:,} tokens")

    elapsed = time.time() - start
    _safe_print(f"  Completed in {elapsed:.2f}s")

    if critical_bugs or sec_critical_found:
        _safe_print(f"\n  {_err('[ABORT]')} Critical issues found. Commit blocked.")
        _safe_print(f"  Fix issues or use `git commit --no-verify` to skip.")
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

    scope_files = [f for f in changed_files if f.startswith("harness/") or f.startswith(".opencode/")]
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
        _safe_print(f"    CRITICAL: {b.file}:{b.line} — {b.message[:80]}")
    for b in major_bugs[:3]:
        _safe_print(f"    MAJOR: {b.file}:{b.line} — {b.message[:80]}")

    sec_findings = security_scan(directory=".", changed_files=scope_files)
    critical_sec = [s for s in sec_findings if s.severity == "critical"]
    sec_count = len(sec_findings)
    sec_summary = f"{sec_count} issues"
    if critical_sec:
        sec_summary += f" ({len(critical_sec)} secrets)"
    _safe_print(f"  [Security scan]: {sec_summary}")
    for s in critical_sec[:3]:
        _safe_print(f"    SECRET: {s.file}:{s.line} — {s.message[:80]}")

    from .phase4_tokens import _estimate_tokens_from_git
    token_rep = _estimate_tokens_from_git()
    _safe_print(f"  [Tokens]: ~{token_rep.tokens_input_total:,} input / ~{token_rep.tokens_output_total:,} output")

    elapsed = time.time() - start
    _safe_print(f"  Done in {elapsed:.2f}s")
    return 0


def main() -> None:
    """CLI entry point for the end-of-iteration pipeline."""
    import argparse
    parser = argparse.ArgumentParser(
        description="End of Iteration Pipeline — Calidad, Seguridad, Docs, Tokens",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Ejemplos:\n"
            "  python harness/scripts/end_of_iteration.py\n"
            "  python harness/scripts/end_of_iteration.py --quick\n"
            "  python harness/scripts/end_of_iteration.py --auto\n"
            "  python harness/scripts/end_of_iteration.py --skip-bugs\n"
            "  python harness/scripts/end_of_iteration.py --skip-sec\n"
            "  python harness/scripts/end_of_iteration.py --skip-docs\n"
            "  python harness/scripts/end_of_iteration.py --dry-run\n"
            "  python harness/scripts/end_of_iteration.py --report\n"
            "  python harness/scripts/end_of_iteration.py --pre-commit\n"
            "  python harness/scripts/end_of_iteration.py --pre-commit --quick\n"
            "  python harness/scripts/end_of_iteration.py --watch\n"
        ),
    )
    parser.add_argument("--quick", action="store_true",
                        help="Modo rapido: solo bugs + tokens, salta security y docs")
    parser.add_argument("--auto", action="store_true",
                        help="Modo automatico: pipeline completo + commit si no hay criticals")
    parser.add_argument("--skip-bugs", action="store_true", help="Salta bug hunting")
    parser.add_argument("--skip-sec", "--skip-security", action="store_true",
                        dest="skip_security", help="Salta security scan")
    parser.add_argument("--skip-docs", action="store_true", help="Salta docs update")
    parser.add_argument("--dry-run", action="store_true", help="Solo muestra que haria")
    parser.add_argument("--report", action="store_true", help="Muestra el ultimo reporte guardado")
    parser.add_argument("--pre-commit", action="store_true",
                        help="Modo pre-commit: solo staged files, silencioso, no interactivo")
    parser.add_argument("--watch", action="store_true",
                        help="Modo watch: solo fases 1, 2, 4, salida concisa")

    args = parser.parse_args()
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
