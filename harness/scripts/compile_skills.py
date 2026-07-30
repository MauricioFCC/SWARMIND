#!/usr/bin/env python3
"""
compile_skills.py — Pre-compila skills .md a version minimal (.min.md).

Lee skills de `.opencode/skills/{role}/SKILL.md` y genera
`.opencode/skills/{role}/SKILL.min.md` con solo:
  - Secciones de pasos (## ...)
  - Checklists (- [ ] ...)
  - Variables ({{ ... }})
  - Guardrails (✅, ⚠️, ❌)
  - Frontmatter (--- ... ---) reducido (solo name, description)

Modo de uso:
    python harness/scripts/compile_skills.py
    python harness/scripts/compile_skills.py --role software-engineer  # solo uno
    python harness/scripts/compile_skills.py --dry-run  # mostrar que se compilaria sin escribir

Ahorro estimado: 40-60% de tokens en carga de skills.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import List, Optional

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# Raiz del proyecto
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # Swarmind/
SKILLS_DIR = PROJECT_ROOT / ".opencode" / "skills"

# Frontmatter keys que preservar en version minificada
KEEP_FRONTMATTER_KEYS = {"name", "description", "model", "provider"}


def find_skill_dirs(base: Path = SKILLS_DIR) -> List[Path]:
    """Encontrar todos los directorios de skills que contienen SKILL.md."""
    if not base.exists():
        logger.warning("Skills directory not found: %s", base)
        return []
    return sorted(
        d for d in base.iterdir() if d.is_dir() and (d / "SKILL.md").exists()
    )


def minify_skill(md_content: str) -> str:
    """Compilar skill a version minima para contexto del agente.

    Preserva:
    - Frontmatter reducido (solo name, description)
    - ## Secciones principales
    - Checklists (- [ ] ...)
    - Variables {{ }}
    - Guardrails (✅ ⚠️ ❌)
    - Referencias a archivos (file://)

    Omite:
    - Diagramas mermaid (```mermaid ... ```)
    - Ejemplos largos (>3 lineas de codigo)
    - Frontmatter verboso (tags, version, etc.)
    """
    lines = md_content.split("\n")
    minified: List[str] = []
    in_frontmatter = False
    frontmatter_ended = False
    in_mermaid = False
    in_code_block = False
    code_block_lines = 0
    in_example = False

    for line in lines:
        stripped = line.strip()

        # --- Mermaid blocks (omitir completamente) ---
        if stripped == "```mermaid":
            in_mermaid = True
            continue
        if in_mermaid:
            if stripped == "```":
                in_mermaid = False
            continue

        # --- Code blocks (contar lineas) ---
        if stripped.startswith("```") and not in_mermaid:
            if in_code_block:
                in_code_block = False
                code_block_lines = 0
                continue
            in_code_block = True
            code_block_lines = 0
            # Incluir el ``` de apertura si es corto (config snippet)
            # Pero omitir ejemplos largos (>3 lineas)
            continue

        if in_code_block:
            code_block_lines += 1
            # Solo preservar si es muy corto (config snippet)
            if code_block_lines <= 3:
                minified.append(line)
            continue

        # --- Frontmatter (procesar) ---
        if stripped == "---" and not frontmatter_ended:
            if not in_frontmatter:
                in_frontmatter = True
                minified.append("---")
                continue
            else:
                in_frontmatter = False
                frontmatter_ended = True
                minified.append("---")
                continue

        if in_frontmatter:
            # Preservar solo keys importantes
            for key in KEEP_FRONTMATTER_KEYS:
                if stripped.startswith(key + ":"):
                    minified.append(line)
                    break
            continue

        # --- Lineas normales ---
        # Preservar siempre:
        # - Titulos de seccion (##)
        # - Checklists
        # - Variables
        # - Guardrails
        # - Referencias a archivos
        if any([
            stripped.startswith("##"),
            stripped.startswith("- [ ]"),
            stripped.startswith("- [x]"),
            "{{" in stripped,
            "}}" in stripped,
            stripped.startswith("✅"),
            stripped.startswith("⚠️"),
            stripped.startswith("❌"),
            "file://" in stripped,
            stripped.startswith("|"),  # tablas
            stripped.startswith(">"),  # blockquotes importantes
        ]):
            minified.append(line)
            continue

        # Lineas en blanco entre secciones (preservar espaciado)
        if stripped == "" and minified and minified[-1].strip():
            minified.append(line)

    # Post-procesamiento: eliminar lineas en blanco duplicadas
    result: List[str] = []
    prev_blank = False
    for line in minified:
        is_blank = line.strip() == ""
        if is_blank and prev_blank:
            continue
        result.append(line)
        prev_blank = is_blank

    return "\n".join(result)


def compile_skill(skill_dir: Path, dry_run: bool = False) -> Optional[Path]:
    """Compilar un skill individual. Retorna ruta del .min.md generado."""
    src = skill_dir / "SKILL.md"
    dst = skill_dir / "SKILL.min.md"

    if not src.exists():
        logger.warning("  SKILL.md not found in %s", skill_dir)
        return None

    content = src.read_text(encoding="utf-8")
    minified = minify_skill(content)

    original_tokens = len(content) // 4  # ~4 chars/token
    minified_tokens = len(minified) // 4
    savings_pct = (
        round((1 - minified_tokens / max(original_tokens, 1)) * 100)
        if original_tokens > 0
        else 0
    )

    if dry_run:
        logger.info(
            "  [DRY-RUN] %s: %d -> %d tokens (%d%% savings)",
            skill_dir.name, original_tokens, minified_tokens, savings_pct,
        )
        return dst

    dst.write_text(minified, encoding="utf-8")
    logger.info(
        "  ✓ %s: %d -> %d tokens (%d%% savings) -> %s",
        skill_dir.name, original_tokens, minified_tokens, savings_pct,
        dst.relative_to(PROJECT_ROOT),
    )
    return dst


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compilar skills .md a version minima .min.md"
    )
    parser.add_argument(
        "--role",
        type=str,
        default="",
        help="Compilar solo un rol (ej: software-engineer)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostrar que se compilaria sin escribir archivos",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Compilar todos los skills (default)",
    )
    args = parser.parse_args()

    if args.role:
        skill_dir = SKILLS_DIR / args.role
        if not skill_dir.exists():
            logger.error("Skill directory not found: %s", skill_dir)
            return
        dirs = [skill_dir]
    else:
        dirs = find_skill_dirs()

    if not dirs:
        logger.warning("No skill directories found in %s", SKILLS_DIR)
        return

    logger.info(
        "Compiling %d skill(s) from %s%s",
        len(dirs), SKILLS_DIR,
        " (DRY-RUN)" if args.dry_run else "",
    )

    total_original = 0
    total_minified = 0
    compiled = 0

    for d in dirs:
        result = compile_skill(d, dry_run=args.dry_run)
        if result:
            compiled += 1
            src = d / "SKILL.md"
            dst = d / "SKILL.min.md"
            if src.exists():
                total_original += len(src.read_text(encoding="utf-8"))
            if dst.exists():
                total_minified += len(dst.read_text(encoding="utf-8"))

    if compiled > 0 and not args.dry_run:
        total_savings = round(
            (1 - total_minified / max(total_original, 1)) * 100
        )
        logger.info(
            "Done: %d skills compiled. Total savings: %d%% (%d -> %d chars)",
            compiled, total_savings, total_original, total_minified,
        )
    elif args.dry_run:
        logger.info("Dry-run complete. Use without --dry-run to write files.")


if __name__ == "__main__":
    main()
