"""
Configuration, data types and shared utilities for the end-of-iteration pipeline.
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

HERE = Path(__file__).resolve().parent.parent
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
                        .replace("\u00f1", "n")
                        .replace("\u26a1", "!")         # ⚡ -> !
                        .replace("\U0001f50d", "[SEARCH]")  # 🔍 -> [SEARCH]
                        .replace("\U0001f4b0", "[MONEY]")   # 💰 -> [MONEY]
                        .replace("\u2705", "[OK]")           # ✅ -> [OK]
                        .replace("\u274c", "[X]")            # ❌ -> [X]
                        .replace("\U0001f4cb", "[LIST]")     # 📋 -> [LIST]
                        .replace("\U0001f4dd", "[NOTE]")     # 📝 -> [NOTE]
                        .replace("\U0001f916", "[AI]"))      # 🤖 -> [AI]
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
    bugs_critical: int = 0
    bugs_major: int = 0
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
                "bug_hunting": True, "security_scan": True,
                "docs_update": True, "token_report": True, "commit_prep": True,
            }
        },
        "bug_hunting": {
            "exclude_patterns": [
                "*/migrations/*", "*/__pycache__/*", "*/node_modules/*", "*.pyc",
            ],
            "max_file_lines": 500,
            "critical_patterns": [
                "except:\\s*pass", "api_key\\s*=", "password\\s*=",
                "TODO", "FIXME", "HACK", "XXX",
            ],
        },
        "security": {
            "secret_patterns": [
                "sk-[a-zA-Z0-9]{20,}", "ghp_[a-zA-Z0-9]{36}",
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
# File helpers
# ---------------------------------------------------------------------------


def _should_exclude(filepath: str, exclude_patterns: List[str]) -> bool:
    """Check if a file path matches any exclude pattern."""
    for pattern in exclude_patterns:
        regex = pattern.replace(".", r"\.").replace("*", ".*")
        if re.search(regex, filepath):
            return True
    return False


def _is_python_file(filepath: str) -> bool:
    """Check if filepath ends with .py and is not .pyc."""
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


def _get_git_changed_files() -> List[str]:
    """Get list of changed files from git diff against last commit."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, timeout=30, cwd=str(PROJECT_ROOT),
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
    import subprocess
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only"],
            capture_output=True, text=True, timeout=30, cwd=str(PROJECT_ROOT),
        )
        staged = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True, text=True, timeout=30, cwd=str(PROJECT_ROOT),
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
    """Get files changed since the last commit."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            capture_output=True, text=True, timeout=15, cwd=str(PROJECT_ROOT),
        )
        commit_count = int(result.stdout.strip() or "0")
        if commit_count >= 2:
            diff_result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD~1..HEAD"],
                capture_output=True, text=True, timeout=30, cwd=str(PROJECT_ROOT),
            )
            if diff_result.returncode == 0:
                files = [f.strip() for f in diff_result.stdout.split("\n") if f.strip()]
                if files:
                    return files
    except Exception:
        pass
    return _get_git_changed_files()


def _has_changed_files_in_dir(changed_files: List[str], prefix: str) -> bool:
    """Check if any changed file lives under a given directory prefix."""
    prefix_norm = prefix.replace("/", os.sep)
    for f in changed_files:
        f_norm = f.replace("/", os.sep)
        if f_norm.startswith(prefix_norm):
            return True
    return False
