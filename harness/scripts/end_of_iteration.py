"""
end_of_iteration.py — Pipeline de fin de iteracion.

Ejecuta:
    python harness/scripts/end_of_iteration.py [--skip-bugs] [--skip-security]
                                               [--skip-docs] [--dry-run]

Orden:
  1. BUG HUNTING: Escanea codigo en busca de bugs comunes
  2. SECURITY REVIEW: Revisa vulnerabilidades
  3. DOC UPDATE: Actualiza documentacion si hubo cambios
  4. TOKEN REPORT: Reporta consumo estimado de tokens
  5. COMMIT READY: Prepara el commit con mensaje sugerido

Cada fase se puede saltar con --skip-* y el modo --dry-run solo muestra
lo que se haria sin modificar nada.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HERE = Path(__file__).resolve().parent
HARNESS_ROOT = HERE.parent
PROJECT_ROOT = HARNESS_ROOT.parent

CONFIG_PATH = HERE / "iteration_config.yaml"

# ANSI colours for rich terminal output
_RED = "\033[91m"
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_CYAN = "\033[96m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def _ok(msg: str) -> str:
    return f"{_GREEN}{msg}{_RESET}"


def _warn(msg: str) -> str:
    return f"{_YELLOW}{msg}{_RESET}"


def _err(msg: str) -> str:
    return f"{_RED}{msg}{_RESET}"


def _bold(msg: str) -> str:
    return f"{_BOLD}{msg}{_RESET}"


def _cyan(msg: str) -> str:
    return f"{_CYAN}{msg}{_RESET}"


def _supports_unicode() -> bool:
    """Check if the terminal supports Unicode output."""
    enc = sys.stdout.encoding or "utf-8"
    if not enc:
        return False
    enc_lower = enc.lower()
    if enc_lower in ("utf-8", "utf8"):
        return True
    try:
        "\u2500".encode(enc)
        return True
    except (UnicodeEncodeError, UnicodeDecodeError):
        return False


def _safe_print(*args, **kwargs) -> None:
    """Print with Unicode fallback: replaces non-encodable chars."""
    if _supports_unicode():
        print(*args, **kwargs)
    else:
        safe_args = []
        for arg in args:
            if isinstance(arg, str):
                arg = (arg.replace("\u2014", "--")
                       .replace("\u2013", "-")
                       .replace("\u2500", "-")
                       .replace("\u2502", "|")
                       .replace("\u2018", "'")
                       .replace("\u2019", "'")
                       .replace("\u201c", '"')
                       .replace("\u201d", '"')
                       .replace("\u2026", "...")
                       .replace("\u00a0", " ")
                       .replace("\u00e9", "e")
                       .replace("\u00ed", "i")
                       .replace("\u00f3", "o")
                       .replace("\u00fa", "u")
                       .replace("\u00f1", "n"))
            safe_args.append(arg)
        print(*safe_args, **kwargs)


def _print_banner(title: str, icon: str) -> None:
    """Print a section banner with optional icon."""
    title_display = f"{icon} {title}" if _supports_unicode() else title
    sep = "\u2500" if _supports_unicode() else "-"
    _safe_print()
    _safe_print(f"  {_bold(title_display)}")
    _safe_print(f"  {sep * 60}")


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class BugFinding:
    """A single bug finding from the scan."""

    file: str
    line: int
    severity: str  # critical / major / minor
    category: str
    message: str
    snippet: str = ""
    auto_fixable: bool = False
    status: str = "open"  # open / fixed / needs_review


@dataclass
class SecurityFinding:
    """A single security finding."""

    file: str
    line: int
    severity: str  # critical / major / minor
    category: str
    message: str
    snippet: str = ""


@dataclass
class DocsStaleness:
    """A docs staleness finding."""

    module_path: str
    docs_path: str
    staleness_type: str  # missing_docs / outdated / auto_regenerated
    message: str = ""


@dataclass
class TokenReport:
    """Token consumption and efficiency report."""

    prompts_enviados: int = 0
    tokens_input_total: int = 0
    tokens_output_total: int = 0
    tokens_ahorrados_por_routing: int = 0
    tokens_ahorrados_por_skills: int = 0
    tokens_ahorrados_por_hitl: int = 0
    costo_estimado_usd: float = 0.0
    eficiencia: Dict[str, str] = field(default_factory=dict)


@dataclass
class IterationReport:
    """Complete report for one iteration end."""

    timestamp: str = ""
    bugs_found: int = 0
    bugs_fixed: int = 0
    bugs_needs_review: int = 0
    security_issues: int = 0
    secrets_found: int = 0
    docs_updated: int = 0
    docs_stale: int = 0
    token_report: Optional[TokenReport] = None
    commit_message_suggested: str = ""
    files_changed: List[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------


def _load_config() -> Dict[str, Any]:
    """Load iteration_config.yaml, falling back to defaults."""
    try:
        import yaml

        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    except (ImportError, yaml.YAMLError) as exc:
        _safe_print(f"  {_warn('[WARN]')} Config load failed: {exc}")
    return _default_config()


def _default_config() -> Dict[str, Any]:
    """Return hardcoded defaults if config file is missing."""
    return {
        "pipeline": {
            "phases": {
                "bug_hunting": True,
                "security_scan": True,
                "docs_update": True,
                "token_report": True,
                "commit_prep": True,
            }
        },
        "bug_hunting": {
            "exclude_patterns": [
                "*/migrations/*",
                "*/__pycache__/*",
                "*/node_modules/*",
                "*.pyc",
            ],
            "max_file_lines": 500,
            "critical_patterns": [
                "except:\\s*pass",
                "api_key\\s*=",
                "password\\s*=",
                "TODO",
                "FIXME",
                "HACK",
                "XXX",
            ],
        },
        "security": {
            "secret_patterns": [
                "sk-[a-zA-Z0-9]{20,}",
                "ghp_[a-zA-Z0-9]{36}",
                "api_key\\s*=\\s*['\"][a-zA-Z0-9]{16,}",
                "token\\s*=\\s*['\"][a-zA-Z0-9]{16,}",
                "password\\s*=\\s*['\"][a-zA-Z0-9]{8,}",
            ]
        },
        "docs": {
            "auto_regenerate": [
                "harness/scripts/generate_llms_txt.py",
                "harness/docs/llms.txt",
                "harness/docs/llms-full.txt",
            ],
            "modules_to_docs_map": {
                "harness/memory_rag/lance_vector_store.py": "harness/docs/",
                "harness/model_router/router.py": "harness/README.md",
                "harness/orchestrator/hitl_guard.py": "harness/README.md",
                "harness/tools_sandbox/mcp_client.py": "harness/README.md",
            },
        },
        "tokens": {
            "warn_threshold_input": 100000,
            "warn_threshold_output": 50000,
        },
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _should_exclude(filepath: str, exclude_patterns: List[str]) -> bool:
    """Check if a file path matches any exclude pattern."""
    for pattern in exclude_patterns:
        # Simple glob-like matching (converted to regex)
        regex = pattern.replace(".", r"\.").replace("*", ".*")
        if re.search(regex, filepath):
            return True
    return False


def _is_python_file(filepath: str) -> bool:
    return filepath.endswith(".py") and not filepath.endswith(".pyc")


def _walk_py_files(directory: str, exclude_patterns: List[str]) -> List[str]:
    """Walk directory yielding Python files that are not excluded."""
    results: List[str] = []
    for root, _dirs, files in os.walk(directory):
        for fname in files:
            if not _is_python_file(fname):
                continue
            fpath = os.path.join(root, fname)
            if _should_exclude(fpath, exclude_patterns):
                continue
            results.append(fpath)
    return results


def _read_file_lines(filepath: str) -> Tuple[List[str], int]:
    """Read file returning (lines, total_lines)."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        return lines, len(lines)
    except Exception:
        return [], 0


# ---------------------------------------------------------------------------
# Phase 1: Bug Hunting
# ---------------------------------------------------------------------------


def _scan_silent_except(lines: List[str], filepath: str) -> List[BugFinding]:
    """Find bare 'except: pass' patterns."""
    findings: List[BugFinding] = []
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if re.search(r"except\s*:\s*pass\s*(#.*)?$", stripped):
            findings.append(
                BugFinding(
                    file=filepath,
                    line=i,
                    severity="critical",
                    category="silent_except",
                    message="Bare 'except: pass' silencia errores silenciosamente",
                    snippet=stripped[:120],
                    auto_fixable=True,
                )
            )
    return findings


def _scan_print_statements(lines: List[str], filepath: str) -> List[BugFinding]:
    """Find 'print(' calls that should be logging."""
    findings: List[BugFinding] = []
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # Match _safe_print( but not inside comments or strings (simple heuristic)
        if re.match(r"^print\s*\(", stripped):
            findings.append(
                BugFinding(
                    file=filepath,
                    line=i,
                    severity="minor",
                    category="print_stmt",
                    message="Usar logging en lugar de print() para produccion",
                    snippet=stripped[:120],
                    auto_fixable=False,
                )
            )
    return findings


def _scan_hardcoded_creds(lines: List[str], filepath: str) -> List[BugFinding]:
    """Find hardcoded credentials."""
    findings: List[BugFinding] = []
    patterns = [
        (r'(api_key|apikey)\s*=\s*["\'][a-zA-Z0-9_\-]{16,}', "api_key"),
        (r'(password|passwd)\s*=\s*["\'][a-zA-Z0-9_\-]{8,}', "password"),
        (r'(secret)\s*=\s*["\'][a-zA-Z0-9_\-]{16,}', "secret"),
        (r'token\s*=\s*["\'][a-zA-Z0-9_\-]{16,}', "token"),
    ]
    for i, line in enumerate(lines, 1):
        for pattern, category in patterns:
            if re.search(pattern, line):
                # Skip if inside comment or docstring test
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith('"""'):
                    continue
                findings.append(
                    BugFinding(
                        file=filepath,
                        line=i,
                        severity="critical",
                        category=f"hardcoded_{category}",
                        message=f"Posible {category} hardcodeada",
                        snippet=stripped[:120],
                        auto_fixable=False,
                    )
                )
    return findings


def _scan_todo_fixme(lines: List[str], filepath: str) -> List[BugFinding]:
    """Find unresolved TODO/FIXME/HACK/XXX markers."""
    findings: List[BugFinding] = []
    markers = ["TODO", "FIXME", "HACK", "XXX"]
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        for marker in markers:
            if marker in stripped.upper() and not stripped.startswith("#"):
                # Check if it's a comment
                if "#" in stripped and marker in stripped.upper().split("#")[1]:
                    findings.append(
                        BugFinding(
                            file=filepath,
                            line=i,
                            severity="minor",
                            category=f"unresolved_{marker.lower()}",
                            message=f"Marcador '{marker}' sin resolver",
                            snippet=stripped[:120],
                            auto_fixable=False,
                        )
                    )
                elif marker in stripped.upper():
                    # Code line with marker
                    findings.append(
                        BugFinding(
                            file=filepath,
                            line=i,
                            severity="minor",
                            category=f"marker_{marker.lower()}",
                            message=f"Marcador '{marker}' presente en codigo",
                            snippet=stripped[:120],
                            auto_fixable=False,
                        )
                    )
    return findings


def _scan_long_files(all_files: List[str]) -> List[BugFinding]:
    """Flag files over max_file_lines."""
    config = _load_config()
    max_lines = config.get("bug_hunting", {}).get("max_file_lines", 500)
    findings: List[BugFinding] = []
    for filepath in all_files:
        _lines, total = _read_file_lines(filepath)
        if total > max_lines:
            rel_path = os.path.relpath(filepath, str(PROJECT_ROOT))
            findings.append(
                BugFinding(
                    file=rel_path,
                    line=0,
                    severity="major",
                    category="long_file",
                    message=f"Archivo de {total} lineas (max: {max_lines}). Considera refactorizar.",
                    auto_fixable=False,
                )
            )
    return findings


def _scan_wildcard_import(lines: List[str], filepath: str) -> List[BugFinding]:
    """Find 'from X import *' patterns."""
    findings: List[BugFinding] = []
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if re.match(r"from\s+\w+\s+import\s+\*", stripped):
            findings.append(
                BugFinding(
                    file=filepath,
                    line=i,
                    severity="major",
                    category="wildcard_import",
                    message="Import * salvaje: importa solo lo necesario",
                    snippet=stripped[:120],
                    auto_fixable=False,
                )
            )
    return findings


def _scan_missing_docstrings(lines: List[str], filepath: str) -> List[BugFinding]:
    """Find functions/classes without docstrings using AST."""
    findings: List[BugFinding] = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)
    except (SyntaxError, Exception):
        return findings  # Skip files with syntax errors

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not ast.get_docstring(node):
                findings.append(
                    BugFinding(
                        file=os.path.relpath(filepath, str(PROJECT_ROOT)),
                        line=node.lineno or 0,
                        severity="minor",
                        category="missing_docstring",
                        message=f"Funcion '{node.name}' sin docstring",
                        auto_fixable=False,
                    )
                )
        elif isinstance(node, ast.ClassDef):
            if not ast.get_docstring(node):
                findings.append(
                    BugFinding(
                        file=os.path.relpath(filepath, str(PROJECT_ROOT)),
                        line=node.lineno or 0,
                        severity="minor",
                        category="missing_docstring",
                        message=f"Clase '{node.name}' sin docstring",
                        auto_fixable=False,
                    )
                )
    return findings


def _scan_missing_type_hints(lines: List[str], filepath: str) -> List[BugFinding]:
    """Find function definitions without type hints using AST."""
    findings: List[BugFinding] = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)
    except (SyntaxError, Exception):
        return findings

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Skip dunder methods like __init__
            if node.name.startswith("__") and node.name.endswith("__"):
                continue
            # Check return annotation
            has_return_hint = node.returns is not None
            # Check parameter annotations
            all_args = (
                [ast.arg(arg=a.arg, annotation=a.annotation) for a in node.args.args]
                + [ast.arg(arg=a.arg, annotation=a.annotation) for a in node.args.kwonlyargs]
            )
            if node.args.vararg:
                all_args.append(ast.arg(arg=node.args.vararg.arg, annotation=node.args.vararg.annotation))
            if node.args.kwarg:
                all_args.append(ast.arg(arg=node.args.kwarg.arg, annotation=node.args.kwarg.annotation))

            params_hinted = all(a.annotation is not None for a in all_args)
            if not has_return_hint or not params_hinted:
                findings.append(
                    BugFinding(
                        file=os.path.relpath(filepath, str(PROJECT_ROOT)),
                        line=node.lineno or 0,
                        severity="minor",
                        category="missing_type_hint",
                        message=f"Funcion '{node.name}' sin type hints completos",
                        auto_fixable=False,
                    )
                )
    return findings


def _scan_inconsistent_returns(lines: List[str], filepath: str) -> List[BugFinding]:
    """Find functions that sometimes return None and sometimes return value."""
    findings: List[BugFinding] = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)
    except (SyntaxError, Exception):
        return findings

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            returns_value = False
            returns_none = False
            for child in ast.walk(node):
                if isinstance(child, ast.Return):
                    if child.value is None:
                        returns_none = True
                    else:
                        returns_value = True
            if returns_value and returns_none:
                findings.append(
                    BugFinding(
                        file=os.path.relpath(filepath, str(PROJECT_ROOT)),
                        line=node.lineno or 0,
                        severity="major",
                        category="inconsistent_return",
                        message=f"Funcion '{node.name}' retorna inconsistentemente (valor y None)",
                        auto_fixable=False,
                    )
                )
    return findings


def scan_for_bugs(directory: str = ".", dry_run: bool = False, changed_files: Optional[List[str]] = None) -> List[BugFinding]:
    """
    Phase 1: Scan code for common bugs.

    If ``changed_files`` is provided, only scans those files (git-diff scope).
    Otherwise walks the entire directory.

    Returns list of findings ordered by severity (critical first).
    """
    config = _load_config()
    exclude = config.get("bug_hunting", {}).get("exclude_patterns", [])
    max_lines = config.get("bug_hunting", {}).get("max_file_lines", 500)

    abs_dir = str(PROJECT_ROOT if directory == "." else os.path.join(PROJECT_ROOT, directory))

    if changed_files is not None:
        # Scope: only scan provided changed files (relative to PROJECT_ROOT)
        all_files = []
        for rel_f in changed_files:
            abs_f = os.path.join(PROJECT_ROOT, rel_f)
            if os.path.isfile(abs_f) and _is_python_file(abs_f):
                if not _should_exclude(abs_f, exclude):
                    all_files.append(abs_f)
    else:
        all_files = _walk_py_files(abs_dir, exclude)

    findings: List[BugFinding] = []

    for filepath in all_files:
        lines, _total = _read_file_lines(filepath)
        if not lines:
            continue
        rel_path = os.path.relpath(filepath, str(PROJECT_ROOT))

        findings.extend(_scan_silent_except(lines, rel_path))
        findings.extend(_scan_print_statements(lines, rel_path))
        findings.extend(_scan_hardcoded_creds(lines, rel_path))
        findings.extend(_scan_todo_fixme(lines, rel_path))
        findings.extend(_scan_wildcard_import(lines, rel_path))
        findings.extend(_scan_missing_docstrings(lines, rel_path))
        findings.extend(_scan_missing_type_hints(lines, rel_path))
        findings.extend(_scan_inconsistent_returns(lines, rel_path))

    findings.extend(_scan_long_files(all_files))

    # Sort by severity
    severity_order = {"critical": 0, "major": 1, "minor": 2}
    findings.sort(key=lambda f: severity_order.get(f.severity, 99))

    return findings


def auto_fix_bugs(bugs: List[BugFinding], dry_run: bool = False) -> List[BugFinding]:
    """
    Auto-fix bugs where possible.

    Currently supports:
      - except: pass → except Exception: pass (with logging suggestion)
    """
    for bug in bugs:
        if not bug.auto_fixable:
            continue
        if bug.category != "silent_except":
            continue

        abs_path = os.path.join(PROJECT_ROOT, bug.file)
        if not os.path.exists(abs_path):
            bug.status = "needs_review"
            continue

        lines, _ = _read_file_lines(abs_path)
        if bug.line < 1 or bug.line > len(lines):
            bug.status = "needs_review"
            continue

        old_line = lines[bug.line - 1]
        # Fix: except: pass → except Exception: pass
        # More sophisticated: add logging
        indent = len(old_line) - len(old_line.lstrip())
        new_line = " " * indent + "except Exception:\n"
        if not dry_run:
            lines[bug.line - 1] = new_line
            try:
                with open(abs_path, "w", encoding="utf-8") as f:
                    f.writelines(lines)
                bug.status = "fixed"
            except Exception:
                bug.status = "needs_review"
        else:
            bug.status = "fixed (dry-run)"

    # Mark non-auto-fixable as needs_review
    for bug in bugs:
        if not bug.auto_fixable and bug.status == "open":
            bug.status = "needs_review"

    return bugs


# ---------------------------------------------------------------------------
# Phase 2: Security Review
# ---------------------------------------------------------------------------


def _scan_secret_patterns(lines: List[str], filepath: str, patterns: List[str]) -> List[SecurityFinding]:
    """Scan for hardcoded secrets."""
    findings: List[SecurityFinding] = []
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # Skip comments and docstrings
        if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
            continue
        for pattern in patterns:
            match = re.search(pattern, stripped)
            if match:
                # Mask the actual secret for display
                masked = match.group()[:8] + "..." if len(match.group()) > 8 else match.group()
                findings.append(
                    SecurityFinding(
                        file=filepath,
                        line=i,
                        severity="critical",
                        category="hardcoded_secret",
                        message=f"Posible secreto hardcodeado: {masked}",
                        snippet=stripped[:120],
                    )
                )
    return findings


def _scan_dangerous_functions(lines: List[str], filepath: str) -> List[SecurityFinding]:
    """Scan for dangerous function calls."""
    findings: List[SecurityFinding] = []
    dangerous = [
        (r"\beval\s*\(", "eval", "Ejecucion de codigo arbitrario"),
        (r"\bexec\s*\(", "exec", "Ejecucion de codigo arbitrario"),
        (r"\b__import__\s*\(", "__import__", "Import dinamico peligroso"),
        (r"shell\s*=\s*True", "shell_true", "Shell=True en subprocess"),
        (r"pickle\.load\s*\(", "pickle_load", "Pickle de fuente no confiable"),
        (r"os\.system\s*\(", "os_system", "os.system sin validacion"),
    ]
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith('"""'):
            continue
        for pattern, category, message in dangerous:
            if re.search(pattern, stripped):
                findings.append(
                    SecurityFinding(
                        file=filepath,
                        line=i,
                        severity="major" if category != "eval" else "critical",
                        category=category,
                        message=message,
                        snippet=stripped[:120],
                    )
                )
    return findings


def _scan_http_urls(lines: List[str], filepath: str) -> List[SecurityFinding]:
    """Find hardcoded HTTP URLs (should use HTTPS)."""
    findings: List[SecurityFinding] = []
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        # Match http:// but not http://localhost or http://127.0.0.1
        matches = re.findall(r'["\']http://[^"\'\s]+["\']', stripped)
        for match in matches:
            url = match.strip("'\"")
            if "localhost" in url or "127.0.0.1" in url:
                continue
            findings.append(
                SecurityFinding(
                    file=filepath,
                    line=i,
                    severity="minor",
                    category="http_url",
                    message=f"URL HTTP hardcodeada (usar HTTPS): {url[:80]}",
                    snippet=stripped[:120],
                )
            )
    return findings


def security_scan(directory: str = ".", changed_files: Optional[List[str]] = None) -> List[SecurityFinding]:
    """
    Phase 2: Security review.

    If ``changed_files`` is provided, only scans those files (git-diff scope).

    Returns list of security findings ordered by severity.
    """
    config = _load_config()
    secret_patterns = config.get("security", {}).get("secret_patterns", [])
    exclude = config.get("bug_hunting", {}).get("exclude_patterns", [])

    abs_dir = str(PROJECT_ROOT if directory == "." else os.path.join(PROJECT_ROOT, directory))

    if changed_files is not None:
        all_files = []
        for rel_f in changed_files:
            abs_f = os.path.join(PROJECT_ROOT, rel_f)
            if os.path.isfile(abs_f) and _is_python_file(abs_f):
                if not _should_exclude(abs_f, exclude):
                    all_files.append(abs_f)
    else:
        all_files = _walk_py_files(abs_dir, exclude)

    findings: List[SecurityFinding] = []

    for filepath in all_files:
        lines, _total = _read_file_lines(filepath)
        if not lines:
            continue
        rel_path = os.path.relpath(filepath, str(PROJECT_ROOT))

        findings.extend(_scan_secret_patterns(lines, rel_path, secret_patterns))
        findings.extend(_scan_dangerous_functions(lines, rel_path))
        findings.extend(_scan_http_urls(lines, rel_path))

    severity_order = {"critical": 0, "major": 1, "minor": 2}
    findings.sort(key=lambda f: severity_order.get(f.severity, 99))

    return findings


# ---------------------------------------------------------------------------
# Phase 3: Documentation Update
# ---------------------------------------------------------------------------


def _get_git_changed_files() -> List[str]:
    """Get list of changed files from git diff against last commit."""
    try:
        # Try diff against HEAD (working tree vs last commit)
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(PROJECT_ROOT),
        )
        if result.returncode == 0:
            files = [f.strip() for f in result.stdout.split("\n") if f.strip()]
            if files:
                return files
    except Exception:
        pass
    return []


def _get_git_uncommitted() -> List[str]:
    """Get uncommitted tracked files (working tree + staged)."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(PROJECT_ROOT),
        )
        staged = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(PROJECT_ROOT),
        )
        files = set()
        if result.returncode == 0:
            files.update(f.strip() for f in result.stdout.split("\n") if f.strip())
        if staged.returncode == 0:
            files.update(f.strip() for f in staged.stdout.split("\n") if f.strip())
        return list(files)
    except Exception:
        return []


def _get_changed_files_since_last_commit() -> List[str]:
    """
    Get files changed since the last commit using ``git diff --name-only HEAD~1..HEAD``.
    Falls back to working-tree diff if there's only one commit.
    """
    try:
        # Check if there's at least one parent commit
        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=str(PROJECT_ROOT),
        )
        commit_count = int(result.stdout.strip() or "0")
        if commit_count >= 2:
            diff_result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD~1..HEAD"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(PROJECT_ROOT),
            )
            if diff_result.returncode == 0:
                files = [f.strip() for f in diff_result.stdout.split("\n") if f.strip()]
                if files:
                    return files
    except Exception:
        pass
    # Fallback: working tree diff
    return _get_git_changed_files()


def _has_changed_files_in_dir(changed_files: List[str], prefix: str) -> bool:
    """Check if any changed file lives under a given directory prefix."""
    prefix_norm = prefix.replace("/", os.sep)
    for f in changed_files:
        f_norm = f.replace("/", os.sep)
        if f_norm.startswith(prefix_norm):
            return True
    return False


def check_and_update_docs(changed_files: List[str], dry_run: bool = False) -> Tuple[List[DocsStaleness], int]:
    """
    Phase 3: Check documentation staleness and auto-update based on changed dirs.

    Rules (from user requirements):
      - Si cambiaron archivos .py en harness/memory_rag/ → regenerar llms.txt
      - Si cambiaron archivos .py en harness/model_router/ → actualizar README.md
      - Si cambiaron archivos .py en harness/orchestrator/ → actualizar README.md
      - Si cambiaron agentes en .opencode/agents/ → actualizar AGENTS.md

    Returns (staleness_list, updated_count).
    """
    staleness: List[DocsStaleness] = []
    updated_count = 0

    if not changed_files:
        return staleness, updated_count

    # Filter to .py and agent .md files
    py_changed = [f for f in changed_files if f.endswith(".py")]
    agent_changed = [f for f in changed_files if f.startswith(".opencode/agents/") and f.endswith(".md")]

    # ── Check memory_rag/ changes → regenerate llms.txt ──
    if _has_changed_files_in_dir(py_changed, "harness/memory_rag/"):
        staleness.append(DocsStaleness(
            module_path="harness/memory_rag/",
            docs_path="harness/docs/llms.txt",
            staleness_type="outdated",
            message="Archivos .py en memory_rag/ cambiaron → regenerar llms.txt",
        ))
        if dry_run:
            _safe_print(f"    {_cyan('[DRY-RUN]')} Regeneraria llms.txt (cambios en memory_rag/)")
        else:
            try:
                sys.path.insert(0, str(HARNESS_ROOT.parent))
                sys.path.insert(0, str(HARNESS_ROOT))
                from harness.scripts.generate_llms_txt import generate_llms_txt
                generate_llms_txt()
                _safe_print(f"    {_ok('[OK]')} llms.txt regenerado (cambios en memory_rag/)")
                updated_count += 1
            except Exception as exc:
                _safe_print(f"    {_err('[ERROR]')} No se pudo regenerar llms.txt: {exc}")

    # ── Check model_router/ changes → update README.md ──
    if _has_changed_files_in_dir(py_changed, "harness/model_router/"):
        staleness.append(DocsStaleness(
            module_path="harness/model_router/",
            docs_path="harness/README.md",
            staleness_type="outdated",
            message="Archivos .py en model_router/ cambiaron → actualizar README.md",
        ))
        _safe_print(f"    {_warn('[REVIEW]')} model_router/ cambio — README.md requiere revision manual")
        updated_count += 1

    # ── Check orchestrator/ changes → update README.md ──
    if _has_changed_files_in_dir(py_changed, "harness/orchestrator/"):
        staleness.append(DocsStaleness(
            module_path="harness/orchestrator/",
            docs_path="harness/README.md",
            staleness_type="outdated",
            message="Archivos .py en orchestrator/ cambiaron → actualizar README.md",
        ))
        _safe_print(f"    {_warn('[REVIEW]')} orchestrator/ cambio — README.md requiere revision manual")
        updated_count += 1

    # ── Check .opencode/agents/ changes → update AGENTS.md ──
    if agent_changed:
        staleness.append(DocsStaleness(
            module_path=".opencode/agents/",
            docs_path="harness/AGENTS.md",
            staleness_type="outdated",
            message="Agentes en .opencode/agents/ cambiaron → actualizar AGENTS.md",
        ))
        names = ", ".join(os.path.basename(a).replace(".md", "") for a in agent_changed[:5])
        _safe_print(f"    {_warn('[REVIEW]')} Agentes modificados: {names} — AGENTS.md requiere revision manual")
        updated_count += 1

    return staleness, updated_count


# ---------------------------------------------------------------------------
# Phase 4: Token Report
# ---------------------------------------------------------------------------


def _count_tokens_in_file(filepath: str) -> int:
    """Rough token estimation (chars / 4)."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            text = f.read()
        return len(text) // 4  # Very rough: ~4 chars per token
    except Exception:
        return 0


def _estimate_tokens_from_git() -> TokenReport:
    """
    Estimate token usage from git diff.

    Uses an heuristic model:
      - Each changed file → 1 prompt
      - Input tokens = diff lines * ~30 tokens/line
      - Output tokens = input * 0.2 (typical ratio)
      - Routing savings: 65% of input would go to cloud
      - Skills savings: 58% of output from procedural memory
    """
    report = TokenReport()

    try:
        # Count changed files
        changed = _get_git_uncommitted()
        staged = subprocess.run(
            ["git", "diff", "--cached", "--stat"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(PROJECT_ROOT),
        )
        report.prompts_enviados = max(len(changed), 1)

        # Get diff stats
        diff_result = subprocess.run(
            ["git", "diff", "--shortstat"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(PROJECT_ROOT),
        )
        diff_text = diff_result.stdout.strip()

        # Parse "X file changed, Y insertions(+), Z deletions(-)"
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

        # Rough estimation: ~30 tokens per line of diff context
        total_diff_lines = insertions + deletions
        tokens_per_line = 30

        report.tokens_input_total = total_diff_lines * tokens_per_line
        report.tokens_output_total = int(report.tokens_input_total * 0.2)

        # Savings estimation (vs sending everything to cloud)
        report.tokens_ahorrados_por_routing = int(report.tokens_input_total * 0.65)
        report.tokens_ahorrados_por_skills = int(report.tokens_output_total * 0.58)

        # Cost: local = $0, cloud = ~$0.002 per 1K tokens
        report.costo_estimado_usd = 0.00  # Local by default

        # Efficiency percentages
        routing_pct = 0
        if report.tokens_input_total > 0:
            routing_pct = int(
                report.tokens_ahorrados_por_routing / (report.tokens_input_total + report.tokens_ahorrados_por_routing) * 100
            )
        skills_pct = 0
        if report.tokens_output_total > 0:
            skills_pct = int(
                report.tokens_ahorrados_por_skills / (report.tokens_output_total + report.tokens_ahorrados_por_skills) * 100
            )
        total_without = report.tokens_input_total + report.tokens_ahorrados_por_routing
        total_with = report.tokens_input_total
        total_savings_pct = 0
        if total_without > 0:
            total_savings_pct = int((total_without - total_with) / total_without * 100)

        report.eficiencia = {
            "routing": f"{routing_pct}% ahorro vs cloud-only",
            "skills": f"{skills_pct}% ahorro vs razonar desde cero",
            "total": f"{total_savings_pct}% ahorro total",
        }

    except Exception:
        # Fallback: minimal report
        report.prompts_enviados = 1
        report.tokens_input_total = 0
        report.tokens_output_total = 0

    return report


def calculate_iteration_cost(report: Optional[TokenReport] = None) -> TokenReport:
    """
    Phase 4: Calculate token consumption and efficiency.

    Returns a TokenReport with usage estimates and efficiency metrics.
    """
    if report is None:
        report = _estimate_tokens_from_git()

    config = _load_config()
    warn_input = config.get("tokens", {}).get("warn_threshold_input", 100000)
    warn_output = config.get("tokens", {}).get("warn_threshold_output", 50000)

    # Warnings
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


# ---------------------------------------------------------------------------
# Commit Safety Checks
# ---------------------------------------------------------------------------


def _check_env_not_staged() -> bool:
    """Verificar que .env no está en staging."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=str(PROJECT_ROOT),
        )
        if result.returncode == 0:
            staged = [f.strip() for f in result.stdout.split("\n") if f.strip()]
            env_staged = [f for f in staged if f == ".env" or f.endswith(".env")]
            if env_staged:
                _safe_print(f"    {_err('[BLOCKED]')} .env en staging! Quita con: git reset HEAD .env")
                return False
        return True
    except Exception:
        return True  # No git repo, skip check


def _check_secrets_in_diff() -> bool:
    """Verificar que no hay tokens/secrets en el diff."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(PROJECT_ROOT),
        )
        if result.returncode != 0:
            return True  # Fallback: allow
        diff_text = result.stdout

        # Common secret patterns
        secret_patterns = [
            r'sk-[a-zA-Z0-9]{20,}',       # OpenAI keys
            r'ghp_[a-zA-Z0-9]{36}',        # GitHub PAT
            r'gho_[a-zA-Z0-9]{36}',        # GitHub OAuth
            r'xox[bpras]-[a-zA-Z0-9\-]+', # Slack tokens
            r'AKIA[0-9A-Z]{16}',           # AWS keys
            r'-----BEGIN\s+(RSA |EC |)?PRIVATE KEY-----',
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
        return True  # No git repo or error, skip check


def _do_git_commit(commit_msg: str) -> bool:
    """Execute git commit and git push."""
    try:
        # Write message to temp file to avoid shell escaping issues
        msg_path = os.path.join(HARNESS_ROOT, ".commit_msg.tmp")
        with open(msg_path, "w", encoding="utf-8") as f:
            f.write(commit_msg)

        result = subprocess.run(
            ["git", "commit", "-F", msg_path],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(PROJECT_ROOT),
        )
        # Clean up temp file
        if os.path.exists(msg_path):
            os.remove(msg_path)

        if result.returncode != 0:
            _safe_print(f"    {_err('[ERROR]')} Commit fallo: {result.stderr.strip()}")
            return False
        _safe_print(f"    {_ok('[OK]')} Commit exitoso: {result.stdout.strip()}")

        # Push
        push_result = subprocess.run(
            ["git", "push"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(PROJECT_ROOT),
        )
        if push_result.returncode != 0:
            _safe_print(f"    {_warn('[WARN]')} Push fallo: {push_result.stderr.strip()}")
            _safe_print(f"    {_warn('[WARN]')} Haz push manual: git push")
            return True  # Commit worked even if push fails
        _safe_print(f"    {_ok('[OK]')} Push exitoso")
        return True
    except Exception as exc:
        _safe_print(f"    {_err('[ERROR]')} Error en commit/push: {exc}")
        return False


def interactive_commit(commit_msg: str) -> None:
    """
    Phase 5: Commit Seguro — interactive commit flow.

    1. Verificar .env no en staging
    2. Verificar no secrets en diff
    3. Mostrar mensaje de commit y preguntar
    """
    _print_banner("FASE 5: Commit Seguro", "\U0001F4DD")

    # Safety check 1: .env
    env_ok = _check_env_not_staged()
    if not env_ok:
        _safe_print(f"\n    {_err('[ABORT]')} .env en staging. Corrige y vuelve a intentar.")
        _safe_print(f"    Sugerencia: git reset HEAD .env")
        return

    # Safety check 2: secrets in diff
    secrets_ok = _check_secrets_in_diff()
    if not secrets_ok:
        _safe_print(f"\n    {_err('[ABORT]')} Secretos en el diff. Corrige y vuelve a intentar.")
        _safe_print(f"    Sugerencia: revisa los archivos y usa variables de entorno.")
        return

    # Show the commit message
    _safe_print(commit_msg)
    _safe_print()

    # Prompt user
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
            _safe_print(f"  El mensaje sugerido queda en el reporte JSON.")
            break
        elif response == "--edit":
            _safe_print(f"  {_cyan('[EDIT]')} Abriendo editor para modificar el mensaje...")
            # Write message to temp file and open editor
            msg_path = os.path.join(HARNESS_ROOT, ".commit_msg_edit.tmp")
            try:
                with open(msg_path, "w", encoding="utf-8") as f:
                    f.write(commit_msg)

                # Try $EDITOR, then fallback to vim/notepad
                editor = os.environ.get("EDITOR", "")
                if not editor:
                    if sys.platform == "win32":
                        editor = "notepad"
                    else:
                        editor = "vim"

                subprocess.run([editor, msg_path], cwd=str(PROJECT_ROOT))
                with open(msg_path, "r", encoding="utf-8") as f:
                    edited_msg = f.read()

                if edited_msg.strip():
                    _safe_print(f"  {_cyan('[COMMIT]')} Ejecutando commit con mensaje editado...")
                    _do_git_commit(edited_msg)
                else:
                    _safe_print(f"  {_warn('[SKIP]')} Mensaje vacio, commit cancelado.")
            except Exception as exc:
                _safe_print(f"  {_err('[ERROR]')} Error al editar: {exc}")
            finally:
                if os.path.exists(msg_path):
                    os.remove(msg_path)
            break
        else:
            _safe_print(f"  Opcion invalida. Responde Y, n, o --edit.")


# ---------------------------------------------------------------------------
# Phase 5 (legacy): Commit Ready
# ---------------------------------------------------------------------------


def _classify_changes() -> Dict[str, List[str]]:
    """Classify git changes into conventional commit categories."""
    categories: Dict[str, List[str]] = {
        "feat": [],
        "fix": [],
        "docs": [],
        "refactor": [],
        "security": [],
        "chore": [],
        "test": [],
        "style": [],
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
    """
    Phase 5: Prepare a suggested commit message.

    Does NOT commit — just prints the message for human review.
    """
    categories = _classify_changes()

    lines: List[str] = []
    sep = "\u2500" if _supports_unicode() else "-"
    lines.append("")
    lines.append(f"# {sep * 67}")
    lines.append("#  End of Iteration - Suggested Commit Message")
    lines.append(f"# {sep * 67}")
    lines.append("")

    # Conventional commit format
    feat_count = len(categories.get("feat", []))
    fix_count = len(categories.get("fix", []))

    if feat_count > 0 and fix_count > 0:
        commit_type = "feat"
        scope = ""
    elif fix_count > 0:
        commit_type = "fix"
        scope = ""
    elif categories.get("docs"):
        commit_type = "docs"
        scope = ""
    elif categories.get("security"):
        commit_type = "security"
        scope = ""
    elif categories.get("refactor"):
        commit_type = "refactor"
        scope = ""
    else:
        commit_type = "chore"
        scope = ""

    # Build short description
    short_desc_parts = []
    if feat_count:
        short_desc_parts.append(f"implementar {feat_count} cambio(s)")
    if fix_count:
        short_desc_parts.append(f"corregir {fix_count} issue(s)")
    if categories.get("docs"):
        short_desc_parts.append(f"actualizar documentacion")
    if categories.get("security"):
        short_desc_parts.append(f"corregir vulnerabilidades")
    if not short_desc_parts:
        short_desc_parts.append("varios cambios")

    commit_short = f"{commit_type}: {', '.join(short_desc_parts)}"
    lines.append(f"{commit_short}")
    lines.append("")

    # Body: summary
    lines.append("# Resumen de cambios:")
    for cat, files in categories.items():
        if files:
            lines.append(f"#   {cat}: {', '.join(files[:5])}")
            if len(files) > 5:
                lines.append(f"#     ... y {len(files) - 5} archivo(s) mas")

    # Body: bug hunting results
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

    # Body: security results
    critical_sec = [s for s in security if s.severity == "critical"]
    lines.append("")
    lines.append(f"# Security: {len(security)} issues ({len(critical_sec)} critical)")
    if critical_sec:
        for s in critical_sec[:3]:
            lines.append(f"#   SECRET: {s.message} en {s.file}:{s.line}")

    # Body: docs
    lines.append("")
    lines.append(f"# Docs: {len(docs_staleness)} archivos desactualizados")

    # Body: token report
    lines.append("")
    lines.append(f"# Token Report:")
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


# ---------------------------------------------------------------------------
# Logging to LanceDB
# ---------------------------------------------------------------------------


def _save_report_to_lancedb(report: IterationReport) -> bool:
    """Save the iteration report to LanceDB (best-effort, silent fail)."""
    try:
        sys.path.insert(0, str(HARNESS_ROOT.parent))
        from harness.memory_rag.lance_vector_store import LanceVectorStore
        import numpy as np

        store = LanceVectorStore()
        report_id = f"iter_{int(time.time())}"

        # Check if table exists; if not, use insert with data to auto-create
        existing = store.list_collections()
        if "iteration_reports" not in existing:
            # Use a direct LanceDB approach to create table with data
            import lancedb
            db_path = store._uri if hasattr(store, '_uri') else str(store._db_path)
            db = lancedb.connect(db_path)
            # Create with one dummy row first, then we'll append real data
            import pyarrow as pa
            schema = pa.schema([
                ("vector", pa.list_(pa.float32(), 384)),
                ("id", pa.string()),
                ("timestamp", pa.string()),
                ("bugs_found", pa.int32()),
                ("bugs_fixed", pa.int32()),
                ("bugs_needs_review", pa.int32()),
                ("security_issues", pa.int32()),
                ("secrets_found", pa.int32()),
                ("docs_updated", pa.int32()),
                ("docs_stale", pa.int32()),
                ("token_input", pa.int32()),
                ("token_output", pa.int32()),
                ("costo_estimado", pa.float64()),
                ("eficiencia", pa.string()),
                ("commit_message_suggested", pa.string()),
                ("files_changed", pa.string()),
                ("elapsed_seconds", pa.float64()),
            ])
            db.create_table("iteration_reports", schema=schema, mode="overwrite")

        vector = np.ones((1, 384), dtype=np.float32) * 0.001
        metadata = {
            "id": report_id,
            "timestamp": report.timestamp,
            "bugs_found": report.bugs_found,
            "bugs_fixed": report.bugs_fixed,
            "bugs_needs_review": report.bugs_needs_review,
            "security_issues": report.security_issues,
            "secrets_found": report.secrets_found,
            "docs_updated": report.docs_updated,
            "docs_stale": report.docs_stale,
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
        return False  # Silent fail — JSON is primary storage


# ---------------------------------------------------------------------------
# Main Pipeline
# ---------------------------------------------------------------------------


def _save_report_to_json(report: IterationReport) -> bool:
    """Save the iteration report as JSON in harness/db/iteration_reports/."""
    reports_dir = HARNESS_ROOT / "db" / "iteration_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    # Determine iteration number
    existing = sorted(reports_dir.glob("report_*.json"))
    iter_num = len(existing) + 1

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"report_{timestamp}_iter{iter_num:04d}.json"
    filepath = reports_dir / filename

    data = asdict(report)
    # Convert dataclasses to dicts recursively
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
    if not existing:
        return None
    return existing[-1]


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


def run_pipeline(
    skip_bugs: bool = False,
    skip_security: bool = False,
    skip_docs: bool = False,
    dry_run: bool = False,
) -> IterationReport:
    """
    Run the complete end-of-iteration pipeline.

    Args:
        skip_bugs: Skip bug hunting phase.
        skip_security: Skip security review phase.
        skip_docs: Skip documentation update phase.
        dry_run: Only simulate, don't modify anything.

    Returns:
        IterationReport with all findings.
    """
    start_time = time.time()
    report = IterationReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    # Get changed files since last commit to scope scanning
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

    # ------------------------------------------------------------------
    # Phase 1: Bug Hunting
    # ------------------------------------------------------------------
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

        # Abort on critical if not skipped
        if criticals and not dry_run:
            _safe_print(f"\n    {_err('[ABORT]')} {len(criticals)} bug(s) critico(s) encontrados.")
            _safe_print(f"    Usa --skip-bugs para saltear esta verificacion.")
            sys.exit(1)

        report.bugs_found = len(bugs)
        report.bugs_fixed = len(fixed)
        report.bugs_needs_review = len(needs_review)
    else:
        _print_banner("FASE 1: Bug Hunting", "\U0001F50D")
        _safe_print(f"    {_warn('[SKIP]')} Bug hunting omitido.")

    # ------------------------------------------------------------------
    # Phase 2: Security Review
    # ------------------------------------------------------------------
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
            _safe_print(f"    {_warn('[WARN]')} Revisa manualmente antes de hacer commit.")

        report.security_issues = len(sec_findings)
        report.secrets_found = len(critical_sec)
    else:
        _print_banner("FASE 2: Security Scan", "\U0001F6E1\uFE0F")
        _safe_print(f"    {_warn('[SKIP]')} Security scan omitido.")

    # ------------------------------------------------------------------
    # Phase 3: Documentation Update
    # ------------------------------------------------------------------
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
        else:
            _safe_print(f"    No se requirieron actualizaciones automaticas.")

        report.docs_updated = docs_updated_count
        report.docs_stale = len(docs_stale)
    else:
        _print_banner("FASE 3: Docs Update", "\U0001F4C4")
        _safe_print(f"    {_warn('[SKIP]')} Docs update omitido.")

    # ------------------------------------------------------------------
    # Phase 4: Token Report
    # ------------------------------------------------------------------
    token_rep: TokenReport = TokenReport()
    _print_banner("FASE 4: Token Report", "\U0001F4B0")
    token_rep = calculate_iteration_cost()
    report.token_report = token_rep

    _safe_print(f"    Archivos cambiados:   {len(changed_files)}")
    _safe_print(f"    Líneas diff:          {token_rep.tokens_input_total // 30 if token_rep.tokens_input_total else 0}")
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

    # ------------------------------------------------------------------
    # Phase 5: Commit Seguro
    # ------------------------------------------------------------------
    commit_msg = prepare_commit(bugs, sec_findings, token_rep, docs_stale)
    report.commit_message_suggested = commit_msg

    if dry_run:
        _print_banner("FASE 5: Commit (DRY-RUN)", "\U0001F4DD")
        _safe_print(commit_msg)
    else:
        interactive_commit(commit_msg)

    # Elapsed
    report.elapsed_seconds = time.time() - start_time
    _safe_print(f"\n  Pipeline completado en {report.elapsed_seconds:.2f}s")

    # Save to JSON
    _save_report_to_json(report)

    # Also save to LanceDB (best-effort, silent)
    _save_report_to_lancedb(report)

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


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


def _run_pre_commit_pipeline() -> int:
    """
    Fast, silent, non-interactive pipeline for pre-commit hooks.

    Only scans staged files (git diff --cached --name-only).
    Phases: bug hunting (1), security scan (2), token report (4).
    No docs update, no commit prompt.

    Returns:
        0 = clean (no critical issues)
        1 = critical bugs/secrets found (abort commit)
        2 = warnings only (allow commit with --no-verify)
    """
    import subprocess as _subprocess

    start = time.time()
    has_warnings = False

    # Get staged files
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

    # Filter to our scope: harness/ and .opencode/
    scope_files = [
        f for f in staged
        if f.startswith("harness/") or f.startswith(".opencode/")
    ]
    # Exclude harness/db/, __pycache__/, .git/
    scope_files = [
        f for f in scope_files
        if not f.startswith("harness/db/")
        and "__pycache__" not in f
        and ".git/" not in f
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
    bugs = auto_fix_bugs(bugs, dry_run=True)  # Never auto-fix in pre-commit
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

    # Phase 2: Security scan (staged files only)
    _safe_print(f"  {_bold('[Security scan]')}...")
    sec_findings = security_scan(directory=".", changed_files=scope_files)
    critical_sec = [s for s in sec_findings if s.severity == "critical"]
    major_sec = [s for s in sec_findings if s.severity == "major"]
    minor_sec = [s for s in sec_findings if s.severity == "minor"]

    if critical_sec:
        _safe_print(f"    {_err(f'[CRITICAL] {len(critical_sec)} secreto(s) encontrado(s)')}")
        for s in critical_sec[:5]:
            _safe_print(f"    {_err('[SECRET]')} {s.file}:{s.line} — {s.message}")
    if major_sec:
        _safe_print(f"    {_warn(f'[MAJOR] {len(major_sec)} issue(s) de seguridad')}")
        has_warnings = True
    if minor_sec:
        _safe_print(f"    {len(minor_sec)} issue(s) de seguridad menores")
        has_warnings = True

    if not critical_sec and not major_sec and not minor_sec:
        _safe_print(f"    {_ok('0 issues')}")

    # Phase 4: Token report (quick estimation)
    _safe_print(f"  {_bold('[Token report]')}...")
    token_rep = _estimate_tokens_from_git()
    _safe_print(f"    Input: ~{token_rep.tokens_input_total:,} tokens / Output: ~{token_rep.tokens_output_total:,} tokens")

    elapsed = time.time() - start
    _safe_print(f"  Completed in {elapsed:.2f}s")

    # Decision:
    if critical_bugs or critical_sec:
        _safe_print(f"\n  {_err('[ABORT]')} Critical issues found. Commit blocked.")
        _safe_print(f"  Fix issues or use `git commit --no-verify` to skip.")
        return 1
    if has_warnings:
        _safe_print(f"\n  {_warn('[WARN]')} Minor issues found. Commit allowed with --no-verify.")
        return 2

    _safe_print(f"\n  {_ok('[OK]')} All checks passed.")
    return 0


def _run_watch_pipeline() -> int:
    """
    Quick pipeline for --watch mode.
    Only phases 1 (bugs), 2 (security), 4 (tokens).
    Concise output — one line per finding.
    """
    start = time.time()

    # Get changed files (uncommitted)
    changed_files = _get_git_uncommitted()
    if not changed_files:
        changed_files = _get_changed_files_since_last_commit()

    # Filter to scope: harness/ and .opencode/
    scope_files = [
        f for f in changed_files
        if f.startswith("harness/") or f.startswith(".opencode/")
    ]
    scope_files = [
        f for f in scope_files
        if not f.startswith("harness/db/")
        and "__pycache__" not in f
        and ".git/" not in f
    ]

    if not scope_files:
        return 0

    # Phase 1: Bug hunting
    bugs = scan_for_bugs(directory=".", changed_files=scope_files)
    critical_bugs = [b for b in bugs if b.severity == "critical"]
    major_bugs = [b for b in bugs if b.severity == "major"]
    minor_bugs = [b for b in bugs if b.severity == "minor"]
    bug_count = len(bugs)
    bug_summary = f"{bug_count} issues"
    if critical_bugs:
        bug_summary += f" ({len(critical_bugs)} critical)"
    _safe_print(f"  [Bug hunting]: {bug_summary}")
    for b in critical_bugs[:3]:
        _safe_print(f"    CRITICAL: {b.file}:{b.line} — {b.message[:80]}")
    for b in major_bugs[:3]:
        _safe_print(f"    MAJOR: {b.file}:{b.line} — {b.message[:80]}")

    # Phase 2: Security scan
    sec_findings = security_scan(directory=".", changed_files=scope_files)
    critical_sec = [s for s in sec_findings if s.severity == "critical"]
    major_sec = [s for s in sec_findings if s.severity == "major"]
    sec_count = len(sec_findings)
    sec_summary = f"{sec_count} issues"
    if critical_sec:
        sec_summary += f" ({len(critical_sec)} secrets)"
    _safe_print(f"  [Security scan]: {sec_summary}")
    for s in critical_sec[:3]:
        _safe_print(f"    SECRET: {s.file}:{s.line} — {s.message[:80]}")

    # Phase 4: Token report
    token_rep = _estimate_tokens_from_git()
    _safe_print(f"  [Tokens]: ~{token_rep.tokens_input_total:,} input / ~{token_rep.tokens_output_total:,} output")

    elapsed = time.time() - start
    _safe_print(f"  Done in {elapsed:.2f}s")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="End of Iteration Pipeline — Calidad, Seguridad, Docs, Tokens",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Ejemplos:\n"
            "  python harness/scripts/end_of_iteration.py\n"
            "  python harness/scripts/end_of_iteration.py --skip-bugs\n"
            "  python harness/scripts/end_of_iteration.py --skip-sec\n"
            "  python harness/scripts/end_of_iteration.py --skip-docs\n"
            "  python harness/scripts/end_of_iteration.py --dry-run\n"
            "  python harness/scripts/end_of_iteration.py --report\n"
            "  python harness/scripts/end_of_iteration.py --pre-commit\n"
            "  python harness/scripts/end_of_iteration.py --watch\n"
        ),
    )
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

    if args.pre_commit:
        sys.exit(_run_pre_commit_pipeline())

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
