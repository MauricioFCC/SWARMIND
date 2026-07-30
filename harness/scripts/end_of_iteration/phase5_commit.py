"""
Phase 5: Commit Preparation — classify changes, suggest message, interactive commit.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

from .config import (
    HARNESS_ROOT,
    PROJECT_ROOT,
    BugFinding,
    DocsStaleness,
    SecurityFinding,
    TokenReport,
    _bold,
    _cyan,
    _err,
    _get_git_uncommitted,
    _ok,
    _print_banner,
    _safe_print,
    _supports_unicode,
    _warn,
)


def _classify_changes() -> Dict[str, List[str]]:
    """Classify git changes into conventional commit categories."""
    categories: Dict[str, List[str]] = {
        "feat": [], "fix": [], "docs": [], "refactor": [],
        "security": [], "chore": [], "test": [], "style": [],
    }
    changed = _get_git_uncommitted()
    for filepath in changed:
        rel = filepath.replace(os.sep, "/")
        if "test_" in rel or "/tests/" in rel:
            categories["test"].append(rel)
        elif rel.endswith(".md"):
            categories["docs"].append(rel)
        elif "security" in rel or "vuln" in rel or "cve" in rel:
            categories["security"].append(rel)
        elif "refactor" in rel or "_v2" in rel:
            categories["refactor"].append(rel)
        elif rel.startswith("harness/scripts/") or rel.startswith("harness/run"):
            categories["feat"].append(rel)
        elif rel.startswith("harness/orchestrator/"):
            categories["refactor"].append(rel)
        elif rel.startswith(".opencode/"):
            categories["chore"].append(rel)
        else:
            categories["chore"].append(rel)
    return categories


def prepare_commit(
    bugs: List[BugFinding],
    security: List[SecurityFinding],
    token_report: TokenReport,
    docs_staleness: List[DocsStaleness],
) -> str:
    """Phase 5: Prepare a suggested commit message."""
    categories = _classify_changes()
    lines: List[str] = []
    sep = "\u2500" if _supports_unicode() else "-"
    lines.append("")
    lines.append(f"# {sep * 67}")
    lines.append("#  End of Iteration - Suggested Commit Message")
    lines.append(f"# {sep * 67}")
    lines.append("")

    feat_count = len(categories.get("feat", []))
    fix_count = len(categories.get("fix", []))
    if feat_count > 0 and fix_count > 0:
        commit_type = "feat"
    elif fix_count > 0:
        commit_type = "fix"
    elif categories.get("docs"):
        commit_type = "docs"
    elif categories.get("security"):
        commit_type = "security"
    elif categories.get("refactor"):
        commit_type = "refactor"
    else:
        commit_type = "chore"

    short_desc_parts = []
    if feat_count:
        short_desc_parts.append(f"implementar {feat_count} cambio(s)")
    if fix_count:
        short_desc_parts.append(f"corregir {fix_count} issue(s)")
    if categories.get("docs"):
        short_desc_parts.append("actualizar documentacion")
    if categories.get("security"):
        short_desc_parts.append("corregir vulnerabilidades")
    if not short_desc_parts:
        short_desc_parts.append("varios cambios")

    commit_short = f"{commit_type}: {', '.join(short_desc_parts)}"
    lines.append(f"{commit_short}")
    lines.append("")

    lines.append("# Resumen de cambios:")
    for cat, files in categories.items():
        if files:
            lines.append(f"#   {cat}: {', '.join(files[:5])}")
            if len(files) > 5:
                lines.append(f"#     ... y {len(files) - 5} archivo(s) mas")

    critical_bugs = [b for b in bugs if b.severity == "critical"]
    major_bugs = [b for b in bugs if b.severity == "major"]
    fixed_bugs = [b for b in bugs if b.status == "fixed"]
    review_bugs = [b for b in bugs if b.status == "needs_review"]

    lines.append("")
    lines.append(f"# Bug Hunting: {len(bugs)} encontrados, {len(fixed_bugs)} fixed, {len(review_bugs)} needs review")
    if critical_bugs:
        for b in critical_bugs[:3]:
            lines.append(f"#   CRITICAL: {b.category} en {b.file}:{b.line}")
    if major_bugs:
        for b in major_bugs[:3]:
            lines.append(f"#   MAJOR: {b.category} en {b.file}:{b.line}")

    critical_sec = [s for s in security if s.severity == "critical"]
    lines.append("")
    lines.append(f"# Security: {len(security)} issues ({len(critical_sec)} critical)")
    if critical_sec:
        for s in critical_sec[:3]:
            lines.append(f"#   SECRET: {s.message} en {s.file}:{s.line}")

    lines.append("")
    lines.append(f"# Docs: {len(docs_staleness)} archivos desactualizados")
    lines.append("")
    lines.append("# Token Report:")
    lines.append(f"#   Input: {token_report.tokens_input_total:,} tokens")
    lines.append(f"#   Output: {token_report.tokens_output_total:,} tokens")
    if token_report.eficiencia:
        for k, v in token_report.eficiencia.items():
            lines.append(f"#   {k}: {v}")

    sep = "\u2500" if _supports_unicode() else "-"
    lines.append("")
    lines.append(f"# {sep * 67}")
    lines.append("#  LINES STARTING WITH '#' WILL BE STRIPPED.")
    lines.append("#  Edit this message or accept as-is.")
    lines.append(f"# {sep * 67}")
    lines.append("")

    return "\n".join(lines)


def _check_env_not_staged() -> bool:
    """Verificar que .env no esta en staging."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True, text=True, timeout=15, cwd=str(PROJECT_ROOT),
        )
        if result.returncode == 0:
            staged = [f.strip() for f in result.stdout.split("\n") if f.strip()]
            env_staged = [f for f in staged if f == ".env" or f.endswith(".env")]
            if env_staged:
                _safe_print(f"    {_err('[BLOCKED]')} .env en staging! Quita con: git reset HEAD .env")
                return False
        return True
    except Exception:
        return True


def _check_secrets_in_diff() -> bool:
    """Verificar que no hay tokens/secrets en el diff."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached"],
            capture_output=True, text=True, timeout=30, cwd=str(PROJECT_ROOT),
        )
        if result.returncode != 0:
            return True
        diff_text = result.stdout
        secret_patterns = [
            r'sk-[a-zA-Z0-9]{20,}', r'ghp_[a-zA-Z0-9]{36}',
            r'gho_[a-zA-Z0-9]{36}', r'xox[bpras]-[a-zA-Z0-9\-]+',
            r'AKIA[0-9A-Z]{16}', r'-----BEGIN\s+(RSA |EC |)?PRIVATE KEY-----',
        ]
        found = []
        for pattern in secret_patterns:
            matches = re.findall(pattern, diff_text)
            for m in matches:
                masked = m[:8] + "..." if len(m) > 8 else m
                found.append(masked)
        if found:
            _safe_print(f"    {_err('[BLOCKED]')} Secreto(s) detectado(s) en el diff!")
            for s in found[:5]:
                _safe_print(f"      {_err('[SECRET]')} {s}")
            _safe_print(f"    {_warn('[SUGGEST]')} Remueve los secretos antes de commitear.")
            return False
        return True
    except Exception:
        return True


def _do_git_commit(commit_msg: str) -> bool:
    """Execute git commit and git push."""
    try:
        msg_path = Path(HARNESS_ROOT) / ".commit_msg.tmp"
        with open(msg_path, "w", encoding="utf-8") as f:
            f.write(commit_msg)

        result = subprocess.run(
            ["git", "commit", "-F", str(msg_path)],
            capture_output=True, text=True, timeout=30, cwd=str(PROJECT_ROOT),
        )
        if msg_path.exists():
            msg_path.unlink()
        if result.returncode != 0:
            _safe_print(f"    {_err('[ERROR]')} Commit fallo: {result.stderr.strip()}")
            return False
        _safe_print(f"    {_ok('[OK]')} Commit exitoso: {result.stdout.strip()}")

        push_result = subprocess.run(
            ["git", "push"],
            capture_output=True, text=True, timeout=60, cwd=str(PROJECT_ROOT),
        )
        if push_result.returncode != 0:
            _safe_print(f"    {_warn('[WARN]')} Push fallo: {push_result.stderr.strip()}")
            _safe_print(f"    {_warn('[WARN]')} Haz push manual: git push")
            return True
        _safe_print(f"    {_ok('[OK]')} Push exitoso")
        return True
    except Exception as exc:
        _safe_print(f"    {_err('[ERROR]')} Error en commit/push: {exc}")
        return False


def interactive_commit(commit_msg: str) -> None:
    """Phase 5: Commit Seguro — interactive commit flow."""
    _print_banner("FASE 5: Commit Seguro", "\U0001F4DD")

    if not _check_env_not_staged():
        _safe_print(f"\n    {_err('[ABORT]')} .env en staging. Corrige y vuelve a intentar.")
        return
    if not _check_secrets_in_diff():
        _safe_print(f"\n    {_err('[ABORT]')} Secretos en el diff. Corrige y vuelve a intentar.")
        return

    _safe_print(commit_msg)
    _safe_print()

    while True:
        try:
            response = input(f"  {_bold('?')} {_cyan('¿Commit?')} [Y/n/--edit] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            _safe_print(f"\n  {_warn('[SKIP]')} Commit cancelado.")
            return

        if response in ("", "y", "yes"):
            _safe_print(f"  {_cyan('[COMMIT]')} Ejecutando commit y push...")
            _do_git_commit(commit_msg)
            break
        elif response in ("n", "no"):
            _safe_print(f"  {_warn('[SKIP]')} Commit cancelado por el usuario.")
            break
        elif response == "--edit":
            _safe_print(f"  {_cyan('[EDIT]')} Abriendo editor para modificar el mensaje...")
            msg_path = Path(HARNESS_ROOT) / ".commit_msg_edit.tmp"
            try:
                with open(msg_path, "w", encoding="utf-8") as f:
                    f.write(commit_msg)
                editor = os.environ.get("EDITOR", "")
                if not editor:
                    editor = "notepad" if sys.platform == "win32" else "vim"
                subprocess.run([editor, str(msg_path)], cwd=str(PROJECT_ROOT))
                with open(msg_path, "r", encoding="utf-8") as f:
                    edited_msg = f.read()
                if edited_msg.strip():
                    _do_git_commit(edited_msg)
                else:
                    _safe_print(f"  {_warn('[SKIP]')} Mensaje vacio, commit cancelado.")
            except Exception as exc:
                _safe_print(f"  {_err('[ERROR]')} Error al editar: {exc}")
            finally:
                if msg_path.exists():
                    msg_path.unlink()
            break
        else:
            _safe_print("  Opcion invalida. Responde Y, n, o --edit.")
