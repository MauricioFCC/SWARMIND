"""
Phase 4: Token Report â€” estimate consumption and efficiency.
"""
from __future__ import annotations

import re
import subprocess

from .config import (
    PROJECT_ROOT,
    TokenReport,
    _get_git_uncommitted,
    _load_config,
    _safe_print,
    _warn,
)


def _count_tokens_in_file(filepath: str) -> int:
    """Rough token estimation (chars / 4)."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            text = f.read()
        return len(text) // 4
    except Exception:  # noqa: BLE001
        return 0


def _estimate_tokens_from_git() -> TokenReport:
    """Estimate token usage from git diff using heuristic model."""
    report = TokenReport()
    try:
        changed = _get_git_uncommitted()
        subprocess.run(
            ["git", "diff", "--cached", "--stat"],
            capture_output=True, text=True, timeout=30, cwd=str(PROJECT_ROOT), check=False,
        )
        report.prompts_enviados = max(len(changed), 1)

        diff_result = subprocess.run(
            ["git", "diff", "--shortstat"],
            capture_output=True, text=True, timeout=30, cwd=str(PROJECT_ROOT), check=False,
        )
        diff_text = diff_result.stdout.strip()

        insertions = 0
        if diff_text:
            ins_match = re.search(r"(\d+)\s+insertion", diff_text)
            if ins_match:
                insertions = int(ins_match.group(1))

        deletions = 0
        if diff_text:
            del_match = re.search(r"(\d+)\s+deletion", diff_text)
            if del_match:
                deletions = int(del_match.group(1))

        total_diff_lines = insertions + deletions
        tokens_per_line = 30

        report.tokens_input_total = total_diff_lines * tokens_per_line
        report.tokens_output_total = int(report.tokens_input_total * 0.2)
        report.tokens_ahorrados_por_routing = int(report.tokens_input_total * 0.65)
        report.tokens_ahorrados_por_skills = int(report.tokens_output_total * 0.58)
        report.costo_estimado_usd = 0.00

        routing_pct = 0
        if report.tokens_input_total > 0:
            routing_pct = int(
                report.tokens_ahorrados_por_routing
                / (report.tokens_input_total + report.tokens_ahorrados_por_routing) * 100
            )
        skills_pct = 0
        if report.tokens_output_total > 0:
            skills_pct = int(
                report.tokens_ahorrados_por_skills
                / (report.tokens_output_total + report.tokens_ahorrados_por_skills) * 100
            )
        total_without = report.tokens_input_total + report.tokens_ahorrados_por_routing
        total_savings_pct = 0
        if total_without > 0:
            total_savings_pct = int((total_without - report.tokens_input_total) / total_without * 100)

        report.eficiencia = {
            "routing": f"{routing_pct}% ahorro vs cloud-only",
            "skills": f"{skills_pct}% ahorro vs razonar desde cero",
            "total": f"{total_savings_pct}% ahorro total",
        }
    except Exception:  # noqa: BLE001
        report.prompts_enviados = 1
        report.tokens_input_total = 0
        report.tokens_output_total = 0

    return report


def calculate_iteration_cost(report: TokenReport | None = None) -> TokenReport:
    """Phase 4: Calculate token consumption and efficiency.

    Returns a TokenReport with usage estimates and efficiency metrics.
    """
    if report is None:
        report = _estimate_tokens_from_git()

    config = _load_config()
    warn_input = config.get("tokens", {}).get("warn_threshold_input", 100000)
    warn_output = config.get("tokens", {}).get("warn_threshold_output", 50000)

    if report.tokens_input_total > warn_input:
        _safe_print(
            f"    {_warn('[WARN]')} Input tokens ({report.tokens_input_total:,}) "
            f"excede umbral ({warn_input:,}). "
            f"Sugerencia: usar --force-cloud solo para tareas criticas."
        )
    if report.tokens_output_total > warn_output:
        _safe_print(
            f"    {_warn('[WARN]')} Output tokens ({report.tokens_output_total:,}) "
            f"excede umbral ({warn_output:,}). "
            f"Sugerencia: revisar prompts para ser mas concisos."
        )

    return report
