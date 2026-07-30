"""
Display â€” Helpers de visualizaciÃ³n para reportes de iteraciÃ³n.

ExtraÃ­do de __init__.py para reducir el monolito.
Incluye:
  - print_last_report()
  - show_iteration_history()
  - show_iteration_diff()
  - list_iteration_reports()

PatrÃ³n RECURSIVO: show_iteration_diff usa indexaciÃ³n recursiva
para navegar por la lista de reports.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import (
    HARNESS_ROOT,
    _bold,
    _err,
    _ok,
    _print_banner,
    _safe_print,
    _supports_unicode,
    _warn,
)

# ---------------------------------------------------------------------------
# Report persistence
# ---------------------------------------------------------------------------


def _get_reports_dir() -> Path:
    """Retorna el directorio de reportes de iteracion."""
    return HARNESS_ROOT / "db" / "iteration_reports"


def _get_last_report_path() -> Path | None:
    """Obtiene la ruta al reporte JSON mas reciente."""
    reports_dir = _get_reports_dir()
    if not reports_dir.exists():
        return None
    existing = sorted(reports_dir.glob("report_*.json"))
    return existing[-1] if existing else None


# ---------------------------------------------------------------------------
# List reports
# ---------------------------------------------------------------------------


def list_iteration_reports(limit: int = 10) -> list[dict]:
    """
    Lista los ultimos N reports de iteracion desde iteration_reports/.

    Returns:
        Lista de dicts con timestamp, status, bugs, tokens, commit.
        Cada dict incluye _file y _path con metadata del archivo.
    """
    reports_dir = _get_reports_dir()
    if not reports_dir.exists():
        return []

    reports: list[dict] = []
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


# ---------------------------------------------------------------------------
# Print last report
# ---------------------------------------------------------------------------


def print_last_report() -> None:
    """Imprime el ultimo reporte guardado en formato legible."""
    report_path = _get_last_report_path()
    if report_path is None:
        _safe_print(f"  {_warn('[WARN]')} No hay reportes de iteracion guardados.")
        return
    try:
        with open(report_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:  # noqa: BLE001
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


# ---------------------------------------------------------------------------
# Show iteration history
# ---------------------------------------------------------------------------


def show_iteration_history(limit: int = 10):
    """Muestra timeline de iteraciones en consola.

    Args:
        limit: Numero de iteraciones a mostrar. Usa 0 para mostrar todas.
    """
    icon = "" if not _supports_unicode() else "\U0001F4CB"
    sep = "=" if not _supports_unicode() else "\u2500"

    actual_limit = limit if limit > 0 else None
    reports = list_iteration_reports(max(0, limit))

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

    _safe_print(f"  {'#':<5} {'Fecha':<22} {'Bugs':<22} {'Tokens':<24} {'Estado':<10}")
    _safe_print(f"  {sep * 75}")

    for i, r in enumerate(reports, 1):
        fecha = r.get("timestamp", "?")[:19] if isinstance(r.get("timestamp"), str) else "?"
        tc = r.get("bugs_critical", r.get("bugs_found", 0))
        tm = r.get("bugs_major", 0)
        tmn = r.get("bugs_minor", 0)
        if not tmn:
            tmn = max(0, r.get("bugs_found", 0) - tc - tm)

        bugs = f"{tc}C/{tm}M/{tmn}m"

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


# ---------------------------------------------------------------------------
# Show iteration diff
# ---------------------------------------------------------------------------


def show_iteration_diff(n: int = 1):
    """Muestra el diff detallado de la iteracion N (1=ultima).

    Args:
        n: Numero de iteracion. 1 = ultima, 2 = penultima, etc.
    """
    reports = list_iteration_reports(n)

    if not reports:
        _safe_print()
        _safe_print(f"  {_warn('[WARN]')} No hay reports de iteracion.")
        _safe_print(f"  Ejecuta: {_bold('!iteration end')}")
        return

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

    # Bugs
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

    # Security
    icon_sec = "" if not _supports_unicode() else "\U0001F6E1\uFE0F"
    sec_issues = r.get("security_issues", 0)
    secrets = r.get("secrets_found", 0)
    _safe_print(f"\n  {icon_sec:<4} Security:")
    _safe_print(f"     Issues:  {sec_issues}")
    if secrets:
        _safe_print(f"     Secrets: {_err(str(secrets))}")
    else:
        _safe_print(f"     Secrets: {secrets}")

    # Docs
    docs_upd = r.get("docs_updated", 0)
    docs_stale = r.get("docs_stale", 0)
    icon_docs = "" if not _supports_unicode() else "\U0001F4C4"
    _safe_print(f"\n  {icon_docs:<4} Docs:")
    _safe_print(f"     Updated: {docs_upd}")
    _safe_print(f"     Stale:   {docs_stale}")

    # Tokens
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
        _safe_print("     Eficiencia:")
        for k, v in eficiencia.items():
            display = v
            if isinstance(v, str) and '%' in v:
                try:
                    pct = int(v.split('%')[0])
                    display = _ok(v) if pct > 50 else _warn(v)
                except (ValueError, IndexError):
                    pass
            _safe_print(f"       {k}: {display}")

    # Duracion
    elapsed = r.get("elapsed_seconds", 0)
    icon_time = "" if not _supports_unicode() else "\u23F1\uFE0F"
    _safe_print(f"\n  {icon_time:<4} Duracion: {elapsed:.2f}s")

    # Commit
    commit = r.get("commit_message_suggested", "") or ""
    if commit:
        icon_commit = "" if not _supports_unicode() else "\U0001F4DD"
        _safe_print(f"\n  {icon_commit:<4} Commit sugerido:")
        first_line = commit.split('\n')[0].strip()
        _safe_print(f"     {first_line}")
        if len(commit) > 200:
            _safe_print("     ... (commit message truncated)")

    # Archivos
    files = r.get("files_changed", []) or []
    if files:
        icon_files = "" if not _supports_unicode() else "\U0001F4C4"
        _safe_print(f"\n  {icon_files:<4} Archivos ({len(files)}):")
        for f in files[:10]:
            _safe_print(f"     {f}")
        if len(files) > 10:
            _safe_print(f"     ... y {len(files) - 10} mas")

    icon_save = "" if not _supports_unicode() else "\U0001F4BE"
    _safe_print(f"\n  {icon_save:<4} Reporte: {r.get('_file', '?')}")


def get_last_report() -> dict[str, Any] | None:
    """Recupera el ultimo reporte de iteracion desde JSON."""
    report_path = _get_last_report_path()
    if report_path is None:
        _safe_print(f"  {_warn('[WARN]')} No hay reportes de iteracion guardados.")
        return None
    try:
        with open(report_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:  # noqa: BLE001
        _safe_print(f"  Error al recuperar report: {exc}")
        return None
