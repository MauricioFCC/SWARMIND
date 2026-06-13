"""
Generate /llms.txt and /llms-full.txt for LLM consumption (Hermes-inspired standard).

Scans ``harness/`` and ``.opencode/`` recursively, building a curated index
(llms.txt) and a full concatenation (llms-full.txt) capped at ~100K tokens.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional, Set

ROOT = Path(__file__).resolve().parent.parent.parent  # AGENTIC/
DOCS_DIR = ROOT / "harness" / "docs"
LLMS_TXT = DOCS_DIR / "llms.txt"
LLMS_FULL_TXT = DOCS_DIR / "llms-full.txt"

MAX_CHARS = 133_333  # ~100K tokens (chars * 0.75)

# Directorios y patrones a excluir completamente
EXCLUDED_DIRS: Set[str] = {
    "__pycache__",
    ".git",
    "lancedb",      # datos binarios LanceDB
    "import",       # BDs legacy para migrar
    "_archived",    # colecciones archivadas
    "_backup",      # backups automáticos
    ".lance",       # datos internos LanceDB
}

EXCLUDED_FILE_SUFFIXES: Set[str] = {
    ".txn",
    ".manifest",
    ".lance",
}

EXCLUDED_FILE_NAMES: Set[str] = {
    "latest_version_hint.json",
}


# ---------------------------------------------------------------------------
# File scanning
# ---------------------------------------------------------------------------


def _should_exclude(path: Path) -> bool:
    """Check if a file should be excluded from scanning."""
    rel = path.relative_to(ROOT)
    parts = rel.parts

    # Excluir directorios completos
    for part in parts[:-1]:  # todas excepto el nombre del archivo
        if part in EXCLUDED_DIRS:
            return True
        if part.startswith("_backup") or part.startswith("__pycache__"):
            return True
        if part == ".git":
            return True

    # Excluir archivos por sufijo
    if path.suffix in EXCLUDED_FILE_SUFFIXES:
        return True

    # Excluir archivos por nombre
    if path.name in EXCLUDED_FILE_NAMES:
        return True

    return False


def _scan_files(directory: Path, extensions: Optional[List[str]] = None) -> List[Path]:
    """Recursively scan a directory for files (excluding __pycache__, binaries, and DB data)."""
    if extensions is None:
        extensions = [".py", ".md", ".yaml", ".yml", ".json", ".cfg", ".ini", ".txt"]

    results: List[Path] = []
    if not directory.exists():
        return results

    for item in directory.rglob("*"):
        if not item.is_file():
            continue
        if _should_exclude(item):
            continue
        if item.suffix in extensions:
            results.append(item)

    return sorted(results)


# ---------------------------------------------------------------------------
# Categorisation
# ---------------------------------------------------------------------------


def _categorise(path: Path) -> str:
    """Assign a category based on file path."""
    rel = str(path.relative_to(ROOT)).lower().replace("\\", "/")

    if rel.startswith(".opencode/skills"):
        return "Skills"
    if rel.startswith(".opencode/agents"):
        return "Agents (.opencode/)"
    if rel.startswith("harness/orchestrator/hitl"):
        return "Orchestrator"
    if rel.startswith("harness/orchestrator"):
        return "Orchestrator"
    if rel.startswith("harness/memory_rag"):
        return "Memory & RAG"
    if rel.startswith("harness/model_router"):
        return "Model Router"
    if rel.startswith("harness/evolve_loop"):
        return "Evolve Loop"
    if rel.startswith("harness/gateway"):
        return "Gateway"
    if rel.startswith("harness/scripts"):
        return "Scripts"
    if rel.startswith("harness/tools_sandbox"):
        return "Tools & MCP"
    if rel.startswith("harness/db/"):
        return "DB & Migrations"
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
        "Core", "Agents (.opencode/)", "Skills", "Orchestrator",
        "Memory & RAG", "Evolve Loop", "Model Router", "Tools & MCP",
        "Gateway", "DB & Migrations", "Scripts", "Documentation",
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
    lines.append("| `!db migrate` | Migrar BDs desde `harness/db/import/` |")
    lines.append("| `!db migrate --path <ruta>` | Migrar BD especifica |")
    lines.append("| `!db list-imports` | Listar BDs disponibles para importar |")
    lines.append("| `!db stats` | Estadisticas de la BD activa |")
    lines.append("| `!db rollback <backup>` | Restaurar desde backup |")
    lines.append("| `--daemon` | Iniciar scheduler en background |")
    lines.append("| `--force-cloud` | Override: forzar modo cloud en ModelRouter |")
    lines.append("| `--auto-pilot` | Desactivar HITL (entornos de confianza) |")
    lines.append("| `--hitl-sensitive` | HITL solo para acciones criticas |")
    lines.append("| `--gateway cli` | Modo gateway interactivo |")
    lines.append("| `python harness/scripts/init.py` | Bootstrap del proyecto |")
    lines.append("| `python harness/scripts/check_ollama.py` | Health check de Ollama |")
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
    """Try to extract the first meaningful heading/title from a file."""
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
        for line in content.splitlines():
            stripped = line.strip()
            # Skip separator lines
            if stripped in ("---", "___", "===") or stripped.startswith("---") or stripped.startswith("===") or stripped.startswith("___"):
                continue
            if stripped.startswith("# ") or stripped.startswith("#skill:"):
                return stripped.lstrip("# ").lstrip("skill:").strip()
            if stripped.startswith("#") and not stripped.startswith("##"):
                return stripped.lstrip("#").strip()
        # Fallback: first non-empty line
        for line in content.splitlines():
            stripped = line.strip()
            if stripped and stripped not in ("---", "___", "==="):
                if len(stripped) < 120:
                    return stripped
                return stripped[:120] + "..."
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
