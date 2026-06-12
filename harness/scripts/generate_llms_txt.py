"""
Generate /llms.txt and /llms-full.txt for LLM consumption (Hermes-inspired standard).

Scans ``harness/`` and ``.opencode/`` recursively, building a curated index
(llms.txt) and a full concatenation (llms-full.txt) capped at ~100K tokens.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent.parent  # AGENTIC/
DOCS_DIR = ROOT / "harness" / "docs"
LLMS_TXT = DOCS_DIR / "llms.txt"
LLMS_FULL_TXT = DOCS_DIR / "llms-full.txt"

MAX_CHARS = 133_333  # ~100K tokens (chars * 0.75)


# ---------------------------------------------------------------------------
# File scanning
# ---------------------------------------------------------------------------


def _scan_files(directory: Path, extensions: Optional[List[str]] = None) -> List[Path]:
    """Recursively scan a directory for files (excluding __pycache__ and binaries)."""
    if extensions is None:
        extensions = [".py", ".md", ".yaml", ".yml", ".json", ".cfg", ".ini", ".txt"]

    results: List[Path] = []
    if not directory.exists():
        return results

    for item in directory.rglob("*"):
        if not item.is_file():
            continue
        rel = item.relative_to(ROOT)
        parts = rel.parts
        # Skip __pycache__, .git, __pycache__ etc.
        if any(p.startswith("__pycache__") or p == ".git" or p.startswith(".") and p != ".opencode" for p in parts):
            continue
        if item.suffix in extensions:
            results.append(item)

    return sorted(results)


# ---------------------------------------------------------------------------
# Categorisation
# ---------------------------------------------------------------------------


def _categorise(path: Path) -> str:
    """Assign a category based on file path."""
    rel = str(path.relative_to(ROOT)).lower()

    if rel.startswith(".opencode/skills"):
        return "Skills"
    if rel.startswith(".opencode/agents"):
        return "Agents"
    if rel.startswith("harness/orchestrator"):
        return "Orchestrator"
    if rel.startswith("harness/memory_rag"):
        return "Memory"
    if rel.startswith("harness/evolve_loop"):
        return "Evolve"
    if rel.startswith("harness/gateway"):
        return "Gateway"
    if rel.startswith("harness/scripts"):
        return "Scripts"
    if rel.startswith("harness/tools_sandbox"):
        return "Tools"
    if rel.startswith("harness/"):
        return "Core"
    if rel.startswith("docs/"):
        return "Documentation"
    if rel.startswith(".opencode/"):
        return "OpenCode Config"
    return "Other"


# ---------------------------------------------------------------------------
# llms.txt — curated index
# ---------------------------------------------------------------------------


def generate_llms_txt() -> str:
    """Generate the curated llms.txt index."""
    files = _scan_files(ROOT)
    categorised: Dict[str, List[Path]] = {}
    for f in files:
        cat = _categorise(f)
        categorised.setdefault(cat, []).append(f)

    # Sort categories
    category_order = [
        "Core", "Agents", "Skills", "Orchestrator", "Memory",
        "Evolve", "Gateway", "Scripts", "Tools", "Documentation",
        "OpenCode Config", "Other",
    ]

    lines: List[str] = [
        "# AGENTIC Harness",
        "> LLMs.txt — contexto curado para LLMs (generado automaticamente)",
        "",
        "## Core",
    ]

    for cat in category_order:
        if cat not in categorised:
            continue
        lines.append(f"## {cat}")
        lines.append("")
        for f in categorised[cat]:
            rel = str(f.relative_to(ROOT)).replace("\\", "/")
            # Get first heading as title
            title = _get_title(f) or rel
            lines.append(f"- [{title}]({rel})")
        lines.append("")

    # Add quick reference
    lines.append("## Quick Reference")
    lines.append("")
    lines.append("| Comando | Descripcion |")
    lines.append("|---------|-------------|")
    lines.append("| `@rol: mensaje` | Delegacion directa a un agente |")
    lines.append("| `!evolve mutate @<a> \"<t>\"` | Mutar y evaluar prompt de agente |")
    lines.append("| `!schedule add <n> --cron \"<c>\" --task \"<t>\"` | Programar job cron |")
    lines.append("| `!schedule add <n> --interval \"30 min\" --task \"<t>\"` | Programar job por intervalo |")
    lines.append("| `!schedule list` | Listar jobs programados |")
    lines.append("| `--daemon` | Iniciar scheduler en background |")
    lines.append("| `--gateway cli` | Modo gateway interactivo |")
    lines.append("| `python harness/scripts/init.py` | Bootstrap del proyecto |")
    lines.append("")

    content = "\n".join(lines)

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    with open(str(LLMS_TXT), "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[OK] {LLMS_TXT} — {len(content)} caracteres")

    return content


# ---------------------------------------------------------------------------
# llms-full.txt — full content
# ---------------------------------------------------------------------------


def generate_llms_full_txt() -> str:
    """Generate the full concatenation of all scanned files (capped at MAX_CHARS)."""
    files = _scan_files(ROOT)
    sections: List[str] = []
    total_chars = 0

    for filepath in files:
        rel = str(filepath.relative_to(ROOT)).replace("\\", "/")
        header = f"\n--- FILE: {rel} ---\n\n"

        try:
            content = filepath.read_text(encoding="utf-8")
        except Exception:
            content = f"[ERROR: could not read {rel}]"

        section = f"{header}{content}"
        section_chars = len(section)

        if total_chars + section_chars > MAX_CHARS:
            remaining = MAX_CHARS - total_chars
            if remaining > 200:
                sections.append(section[:remaining])
            break

        sections.append(section)
        total_chars += section_chars

    full = "".join(sections)
    estimated_tokens = len(full) // 4

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    with open(str(LLMS_FULL_TXT), "w", encoding="utf-8") as f:
        f.write(full)
    print(f"[OK] {LLMS_FULL_TXT} — {len(full)} caracteres, ~{estimated_tokens} tokens estimados")

    return full


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_title(filepath: Path) -> str:
    """Try to extract the first heading/title from a file."""
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("# ") or stripped.startswith("#skill:"):
                return stripped.lstrip("# ").lstrip("skill:").strip()
            if stripped.startswith("#"):
                return stripped.lstrip("#").strip()
        return ""
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    print("Generando docs/llms.txt y docs/llms-full.txt...")
    print(f"Escaneando: {ROOT}")
    generate_llms_txt()
    generate_llms_full_txt()
    print("Done.")
