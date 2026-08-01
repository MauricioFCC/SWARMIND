"""
Phase 1: Bug Hunting â€” scan code for common bugs.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from .config import (
    PROJECT_ROOT,
    BugFinding,
    _is_python_file,
    _load_config,
    _read_file_lines,
    _rel_project,
    _should_exclude,
    _walk_py_files,
)


def _scan_silent_except(lines: list[str], filepath: str) -> list[BugFinding]:
    """Find bare 'except: pass' patterns."""
    findings: list[BugFinding] = []
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if re.search(r"except\s*:\s*pass\s*(#.*)?$", stripped):
            findings.append(BugFinding(
                file=filepath, line=i, severity="critical",
                category="silent_except",
                message="Bare 'except: pass' silencia errores silenciosamente",
                snippet=stripped[:120], auto_fixable=True,
            ))
    return findings


def _scan_print_statements(lines: list[str], filepath: str) -> list[BugFinding]:
    """Find 'print(' calls that should be logging."""
    findings: list[BugFinding] = []
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if re.match(r"^print\s*\(", stripped):
            findings.append(BugFinding(
                file=filepath, line=i, severity="minor",
                category="print_stmt",
                message="Usar logging en lugar de print() para produccion",
                snippet=stripped[:120], auto_fixable=False,
            ))
    return findings


def _scan_hardcoded_creds(lines: list[str], filepath: str) -> list[BugFinding]:
    """Find hardcoded credentials."""
    findings: list[BugFinding] = []
    patterns = [
        (r'(api_key|apikey)\s*=\s*["\'][a-zA-Z0-9_\-]{16,}', "api_key"),
        (r'(password|passwd)\s*=\s*["\'][a-zA-Z0-9_\-]{8,}', "password"),
        (r'(secret)\s*=\s*["\'][a-zA-Z0-9_\-]{16,}', "secret"),
        (r'token\s*=\s*["\'][a-zA-Z0-9_\-]{16,}', "token"),
    ]
    for i, line in enumerate(lines, 1):
        for pattern, category in patterns:
            if re.search(pattern, line):
                stripped = line.strip()
                if stripped.startswith(("#", '"""')):
                    continue
                findings.append(BugFinding(
                    file=filepath, line=i, severity="critical",
                    category=f"hardcoded_{category}",
                    message=f"Posible {category} hardcodeada",
                    snippet=stripped[:120], auto_fixable=False,
                ))
    return findings


def _scan_todo_fixme(lines: list[str], filepath: str) -> list[BugFinding]:
    """Find unresolved TODO/FIXME/HACK/XXX markers."""
    findings: list[BugFinding] = []
    markers = ["TODO", "FIXME", "HACK", "XXX"]
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        for marker in markers:
            if marker in stripped.upper() and not stripped.startswith("#"):
                if "#" in stripped and marker in stripped.upper().split("#")[1]:
                    findings.append(BugFinding(
                        file=filepath, line=i, severity="minor",
                        category=f"unresolved_{marker.lower()}",
                        message=f"Marcador '{marker}' sin resolver",
                        snippet=stripped[:120], auto_fixable=False,
                    ))
                elif marker in stripped.upper():
                    findings.append(BugFinding(
                        file=filepath, line=i, severity="minor",
                        category=f"marker_{marker.lower()}",
                        message=f"Marcador '{marker}' presente en codigo",
                        snippet=stripped[:120], auto_fixable=False,
                    ))
    return findings


def _scan_long_files(all_files: list[str]) -> list[BugFinding]:
    """Flag files over max_file_lines."""
    config = _load_config()
    max_lines = config.get("bug_hunting", {}).get("max_file_lines", 500)
    findings: list[BugFinding] = []
    for filepath in all_files:
        _lines, total = _read_file_lines(filepath)
        if total > max_lines:
            rel_path = _rel_project(filepath)
            findings.append(BugFinding(
                file=rel_path, line=0, severity="major",
                category="long_file",
                message=f"Archivo de {total} lineas (max: {max_lines}). Considera refactorizar.",
                auto_fixable=False,
            ))
    return findings


def _scan_wildcard_import(lines: list[str], filepath: str) -> list[BugFinding]:
    """Find 'from X import *' patterns."""
    findings: list[BugFinding] = []
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if re.match(r"from\s+\w+\s+import\s+\*", stripped):
            findings.append(BugFinding(
                file=filepath, line=i, severity="major",
                category="wildcard_import",
                message="Import * salvaje: importa solo lo necesario",
                snippet=stripped[:120], auto_fixable=False,
            ))
    return findings


def _scan_missing_docstrings(lines: list[str], filepath: str) -> list[BugFinding]:
    """Find functions/classes without docstrings using AST."""
    findings: list[BugFinding] = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)
    except (SyntaxError, Exception):  # noqa: BLE001
        return findings
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not ast.get_docstring(node):
                findings.append(BugFinding(
                    file=_rel_project(filepath),
                    line=node.lineno or 0, severity="minor",
                    category="missing_docstring",
                    message=f"Funcion '{node.name}' sin docstring", auto_fixable=False,
                ))
        elif isinstance(node, ast.ClassDef) and not ast.get_docstring(node):
            findings.append(BugFinding(
                file=_rel_project(filepath),
                line=node.lineno or 0, severity="minor",
                category="missing_docstring",
                message=f"Clase '{node.name}' sin docstring", auto_fixable=False,
            ))
    return findings


def _scan_missing_type_hints(lines: list[str], filepath: str) -> list[BugFinding]:
    """Find function definitions without type hints using AST."""
    findings: list[BugFinding] = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)
    except (SyntaxError, Exception):  # noqa: BLE001
        return findings
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("__") and node.name.endswith("__"):
                continue
            has_return_hint = node.returns is not None
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
                findings.append(BugFinding(
                    file=str(_rel_project(filepath)),
                    line=node.lineno or 0, severity="minor",
                    category="missing_type_hint",
                    message=f"Funcion '{node.name}' sin type hints completos",
                    auto_fixable=False,
                ))
    return findings


def _scan_inconsistent_returns(lines: list[str], filepath: str) -> list[BugFinding]:
    """Find functions that sometimes return None and sometimes return value."""
    findings: list[BugFinding] = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)
    except (SyntaxError, Exception):  # noqa: BLE001
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
                findings.append(BugFinding(
                    file=_rel_project(filepath),
                    line=node.lineno or 0, severity="major",
                    category="inconsistent_return",
                    message=f"Funcion '{node.name}' retorna inconsistentemente (valor y None)",
                    auto_fixable=False,
                ))
    return findings


def scan_for_bugs(
    directory: str = ".",
    dry_run: bool = False,
    changed_files: list[str] | None = None,
) -> list[BugFinding]:
    """Phase 1: Scan code for common bugs.

    If ``changed_files`` is provided, only scans those files (git-diff scope).
    Otherwise walks the entire directory.

    Returns list of findings ordered by severity (critical first).
    """
    config = _load_config()
    exclude = config.get("bug_hunting", {}).get("exclude_patterns", [])
    abs_dir = str(PROJECT_ROOT if directory == "." else Path(PROJECT_ROOT) / directory)

    if changed_files is not None:
        all_files = []
        for rel_f in changed_files:
            abs_f = Path(PROJECT_ROOT) / rel_f
            if abs_f.is_file() and _is_python_file(str(abs_f)) and not _should_exclude(str(abs_f), exclude):
                all_files.append(str(abs_f))
    else:
        all_files = _walk_py_files(abs_dir, exclude)

    findings: list[BugFinding] = []
    for filepath in all_files:
        lines, _total = _read_file_lines(filepath)
        if not lines:
            continue
        rel_path = _rel_project(filepath)
        findings.extend(_scan_silent_except(lines, rel_path))
        findings.extend(_scan_print_statements(lines, rel_path))
        findings.extend(_scan_hardcoded_creds(lines, rel_path))
        findings.extend(_scan_todo_fixme(lines, rel_path))
        findings.extend(_scan_wildcard_import(lines, rel_path))
        findings.extend(_scan_missing_docstrings(lines, rel_path))
        findings.extend(_scan_missing_type_hints(lines, rel_path))
        findings.extend(_scan_inconsistent_returns(lines, rel_path))
    findings.extend(_scan_long_files(all_files))

    severity_order = {"critical": 0, "major": 1, "minor": 2}
    findings.sort(key=lambda f: severity_order.get(f.severity, 99))
    return findings


def auto_fix_bugs(bugs: list[BugFinding], dry_run: bool = False) -> list[BugFinding]:
    """Auto-fix bugs where possible (currently only 'except: pass')."""
    for bug in bugs:
        if not bug.auto_fixable:
            continue
        if bug.category != "silent_except":
            continue
        abs_path = str(Path(PROJECT_ROOT) / bug.file)
        if not Path(abs_path).exists():
            bug.status = "needs_review"
            continue
        lines, _ = _read_file_lines(abs_path)
        if bug.line < 1 or bug.line > len(lines):
            bug.status = "needs_review"
            continue
        old_line = lines[bug.line - 1]
        indent = len(old_line) - len(old_line.lstrip())
        new_line = " " * indent + "except Exception:\n"
        if not dry_run:
            lines[bug.line - 1] = new_line
            try:
                with open(abs_path, "w", encoding="utf-8") as f:
                    f.writelines(lines)
                bug.status = "fixed"
            except Exception:  # noqa: BLE001
                bug.status = "needs_review"
        else:
            bug.status = "fixed (dry-run)"

    for bug in bugs:
        if not bug.auto_fixable and bug.status == "open":
            bug.status = "needs_review"
    return bugs
