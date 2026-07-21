"""
Phase 3: Documentation Update — check staleness and auto-regenerate.
"""
from __future__ import annotations

import os
import sys
from typing import List, Tuple

from .config import (
    HARNESS_ROOT,
    DocsStaleness,
    _cyan,
    _err,
    _has_changed_files_in_dir,
    _ok,
    _safe_print,
    _warn,
)


def check_and_update_docs(changed_files: List[str], dry_run: bool = False) -> Tuple[List[DocsStaleness], int]:
    """Phase 3: Check documentation staleness and auto-update based on changed dirs.

    Returns (staleness_list, updated_count).
    """
    staleness: List[DocsStaleness] = []
    updated_count = 0

    if not changed_files:
        return staleness, updated_count

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
                sys.path.insert(1, str(HARNESS_ROOT.parent))
                sys.path.insert(1, str(HARNESS_ROOT))
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
