"""
Phase 2: Security Review — scan for secrets, dangerous functions, HTTP URLs.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from .config import (
    PROJECT_ROOT,
    SecurityFinding,
    _is_python_file,
    _load_config,
    _read_file_lines,
    _should_exclude,
    _walk_py_files,
)


def _scan_secret_patterns(lines: List[str], filepath: str, patterns: List[str]) -> List[SecurityFinding]:
    """Scan for hardcoded secrets."""
    findings: List[SecurityFinding] = []
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
            continue
        for pattern in patterns:
            match = re.search(pattern, stripped)
            if match:
                masked = match.group()[:8] + "..." if len(match.group()) > 8 else match.group()
                findings.append(SecurityFinding(
                    file=filepath, line=i, severity="critical",
                    category="hardcoded_secret",
                    message=f"Posible secreto hardcodeado: {masked}",
                    snippet=stripped[:120],
                ))
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
                findings.append(SecurityFinding(
                    file=filepath, line=i,
                    severity="major" if category != "eval" else "critical",
                    category=category, message=message,
                    snippet=stripped[:120],
                ))
    return findings


def _scan_http_urls(lines: List[str], filepath: str) -> List[SecurityFinding]:
    """Find hardcoded HTTP URLs (should use HTTPS)."""
    findings: List[SecurityFinding] = []
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        matches = re.findall(r'["\']http://[^"\'\s]+["\']', stripped)
        for match in matches:
            url = match.strip("'\"")
            if "localhost" in url or "127.0.0.1" in url:
                continue
            findings.append(SecurityFinding(
                file=filepath, line=i, severity="minor",
                category="http_url",
                message=f"URL HTTP hardcodeada (usar HTTPS): {url[:80]}",
                snippet=stripped[:120],
            ))
    return findings


def security_scan(directory: str = ".", changed_files: Optional[List[str]] = None) -> List[SecurityFinding]:
    """Phase 2: Security review.

    If ``changed_files`` is provided, only scans those files (git-diff scope).
    Returns list of security findings ordered by severity.
    """
    config = _load_config()
    secret_patterns = config.get("security", {}).get("secret_patterns", [])
    exclude = config.get("bug_hunting", {}).get("exclude_patterns", [])
    abs_dir = str(PROJECT_ROOT if directory == "." else Path(PROJECT_ROOT) / directory)

    if changed_files is not None:
        all_files = []
        for rel_f in changed_files:
            abs_f = str(Path(PROJECT_ROOT) / rel_f)
            if Path(abs_f).is_file() and _is_python_file(abs_f):
                if not _should_exclude(abs_f, exclude):
                    all_files.append(abs_f)
    else:
        all_files = _walk_py_files(abs_dir, exclude)

    findings: List[SecurityFinding] = []
    for filepath in all_files:
        lines, _total = _read_file_lines(filepath)
        if not lines:
            continue
        rel_path = str(Path(filepath).relative_to(PROJECT_ROOT))
        findings.extend(_scan_secret_patterns(lines, rel_path, secret_patterns))
        findings.extend(_scan_dangerous_functions(lines, rel_path))
        findings.extend(_scan_http_urls(lines, rel_path))

    severity_order = {"critical": 0, "major": 1, "minor": 2}
    findings.sort(key=lambda f: severity_order.get(f.severity, 99))
    return findings
