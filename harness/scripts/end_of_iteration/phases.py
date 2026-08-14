"""Fases del pipeline de fin de iteracion.

Submodulo interno del paquete :mod:`harness.scripts.end_of_iteration`.

Extraido de forma mecanica desde ``__init__.py`` (regla AGR: archivos
< 500 lineas). Define las fases ``_phase_*``, la lista ``PHASES`` y el
ejecutor recursivo ``run_pipeline_recursive``. Los cuerpos son identicos
al original; solo cambia la ubicacion fisica del codigo.
"""

from __future__ import annotations

import sys
from typing import Any

from .config import (
    _err,
    _ok,
    _print_banner,
    _safe_print,
    _warn,
)
from .phase1_bugs import auto_fix_bugs, scan_for_bugs
from .phase2_security import security_scan
from .phase3_docs import check_and_update_docs
from .phase4_tokens import calculate_iteration_cost
from .phase5_commit import interactive_commit, prepare_commit


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
    
    Patrón RECURSIVO: cada fase procesa el contexto y lo pasa a la siguiente.
    Cuando no hay más fases, retorna el contexto final.
    
    Args:
        phases: Lista de tuplas (nombre, funcion_fase)
        index: Indice actual en la lista de fases
        context: Dict con estado compartido entre fases
    
    Returns:
        Contexto final después de ejecutar todas las fases
    """
    # Caso base: no hay más fases
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
