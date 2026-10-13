#!/usr/bin/env python3
"""
compile_agents.py — Pre-compila agent prompts .md a version minimal (.agent.min.md).

Lee agent profiles de `.opencode/agents/{role}.md` y genera
`.opencode/agents/{role}.agent.min.md` con:
  - Frontmatter COMPLETO (el discovery en agent_discovery/parsing.py depende
    de triggers/capabilities/aliases/description; no se puede reducir).
  - Headings (#, ##, ###, ####), checklists, tablas y guardrails (✅, ⚠️, ❌).
  - Listas, reglas numeradas y bloques de config (variable = valor).
  - Referencias a archivos de config/politica (`*.yaml|yml|json|toml`), p. ej.
    `coordinator_policy.yaml` (SSOT de politica del coordinator, ADR-0103).

Omite:
  - Mermaid diagrams (```mermaid ... ```)
  - Ejemplos largos (>3 lineas de codigo)
  - Parrafos de prosa sin estructura

Modo de uso:
    python harness/scripts/compile_agents.py
    python harness/scripts/compile_agents.py --role quality-gate  # solo uno
    python harness/scripts/compile_agents.py --dry-run  # mostrar que se compilaria sin escribir

Ahorro estimado: 40-60% de tokens en carga de agent profiles.
"""

from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# Raiz del proyecto
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # Swarmind/
AGENTS_DIR = PROJECT_ROOT / ".opencode" / "agents"

#: Referencias a archivos de config/politica que SIEMPRE se preservan. El
#: coordinator apunta a `coordinator_policy.yaml` (SSOT de politica, ADR-0103);
#: sin esta regla la prosa que lo referencia se descartaria al minificar.
CONFIG_REF_PATTERN = re.compile(
    r"[\w./\\-]+\.(?:ya?ml|json|toml|ini|cfg)", re.IGNORECASE
)

# Secciones que siempre preservar
KEEP_SECTIONS: set[str] = {
    "mision", "mission",
    "flujo", "flow",
    "reglas", "rules",
    "formato", "format",
    "output",
    "gates",
    "estrategia", "strategy",
    "capacidades", "capabilities",
    "comandos", "commands",
}


def find_agent_files(base: Path = AGENTS_DIR) -> list[Path]:
    """Encontrar todos los archivos .md de agentes (excluyendo .agent.min.md)."""
    if not base.exists():
        logger.warning("Agents directory not found: %s", base)
        return []
    return sorted(
        f for f in base.glob("*.md") if not f.name.endswith(".agent.min.md")
    )


def minify_agent(md_content: str) -> str:
    """Compilar agent prompt a version minima para contexto.

    Preserva:
    - Frontmatter completo (identidad + triggers/capabilities para el discovery)
    - Headings (#, ##, ###, ####) de las secciones principales
    - Checklists (- [ ] ...)
    - Tablas (| ... |)
    - Guardrails (✅ ⚠️ ❌)
    - Output format blocks (``` ... ``` cortos)
    - Lineas con @menciones o #hashtags
    - Referencias a config/politica (``*.yaml``/``*.json``; ver
      :data:`CONFIG_REF_PATTERN`)

    Omite:
    - Diagramas mermaid (```mermaid ... ```)
    - Parrafos largos (>80 chars sin estructura)
    - Ejemplos extensos
    """
    lines = md_content.split("\n")
    minified: list[str] = []
    in_frontmatter = False
    frontmatter_ended = False
    in_mermaid = False
    in_code_block = False
    code_block_lines = 0
    skip_verbose_paragraph = False
    verbose_line_count = 0

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

        # --- Code blocks (contar lineas, preservar solo si cortos) ---
        if stripped.startswith("```") and not in_mermaid:
            if in_code_block:
                in_code_block = False
                code_block_lines = 0
                # Incluir el ``` de cierre
                minified.append(line)
                continue
            in_code_block = True
            code_block_lines = 0
            # Incluir el ``` de apertura
            minified.append(line)
            continue

        if in_code_block:
            code_block_lines += 1
            # Solo preservar si es muy corto (< 6 lineas de codigo)
            if code_block_lines <= 5:
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
            # Preservar el frontmatter completo: agent_discovery/parsing.py lee
            # triggers/capabilities/aliases/description desde aqui.
            minified.append(line)
            continue

        # Resetear deteccion de parrafos verbosos
        if stripped == "":
            skip_verbose_paragraph = False
            verbose_line_count = 0

        # --- Lineas normales ---
        # Preservar siempre:
        # - Titulos de seccion (##)
        # - Checklists
        # - Tablas
        # - Guardrails
        # - @menciones
        # - Comandos (!comando)
        # - Items de lista (- o *)
        is_heading = stripped.startswith("#")
        is_checklist = stripped.startswith(("- [", "* ["))
        is_table = stripped.startswith("|")
        is_guardrail = any(stripped.startswith(g) for g in ("✅", "⚠️", "❌", "🔴", "🟢", "📌"))
        is_mention = "@" in stripped and not stripped.startswith("```")
        is_command = stripped.startswith("!")
        is_list_item = stripped.startswith(("- ", "* "))
        is_config_ref = bool(CONFIG_REF_PATTERN.search(stripped))

        if any([is_heading, is_checklist, is_table, is_guardrail,
                is_mention, is_command, is_list_item, is_config_ref]):
            minified.append(line)
            verbose_line_count = 0
            skip_verbose_paragraph = False
            continue

        # Lineas en blanco entre secciones (preservar espaciado)
        if stripped == "" and minified and minified[-1].strip():
            minified.append(line)
            continue

        # Detectar parrafos verbosos (>80 chars y sin estructura)
        if len(stripped) > 120 and not any(c in stripped for c in (':', '|', '-', '#')):
            verbose_line_count += 1
            if verbose_line_count >= 3:
                skip_verbose_paragraph = True
            if skip_verbose_paragraph:
                continue

        # Preservar lineas de configuracion cortas (variable = valor)
        if "=" in stripped and len(stripped) < 100:
            minified.append(line)
            continue

        # Preservar numeros de regla (1. 2. etc)
        if re.match(r"^\d+\.", stripped) and len(stripped) < 200:
            minified.append(line)
            continue

    # Post-procesamiento: eliminar lineas en blanco duplicadas
    result: list[str] = []
    prev_blank = False
    for line in minified:
        is_blank = line.strip() == ""
        if is_blank and prev_blank:
            continue
        result.append(line)
        prev_blank = is_blank

    return "\n".join(result)


def compile_agent(agent_file: Path, dry_run: bool = False) -> Path | None:
    """Compilar un agent profile individual. Retorna ruta del .agent.min.md generado."""
    dst = agent_file.with_suffix('.agent.min.md')

    if not agent_file.exists():
        logger.warning("  Agent file not found: %s", agent_file)
        return None

    content = agent_file.read_text(encoding="utf-8")
    minified = minify_agent(content)

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
            agent_file.stem, original_tokens, minified_tokens, savings_pct,
        )
        return dst

    dst.write_text(minified, encoding="utf-8")
    logger.info(
        "  ✓ %s: %d -> %d tokens (%d%% savings) -> %s",
        agent_file.stem, original_tokens, minified_tokens, savings_pct,
        dst.relative_to(PROJECT_ROOT),
    )
    return dst


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compilar agent prompts .md a version minima .agent.min.md"
    )
    parser.add_argument(
        "--role",
        type=str,
        default="",
        help="Compilar solo un rol (ej: quality-gate)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostrar que se compilaria sin escribir archivos",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Compilar todos los agentes (default)",
    )
    args = parser.parse_args()

    if args.role:
        agent_file = AGENTS_DIR / f"{args.role}.md"
        if not agent_file.exists():
            logger.error("Agent file not found: %s", agent_file)
            return
        files = [agent_file]
    else:
        files = find_agent_files()

    if not files:
        logger.warning("No agent files found in %s", AGENTS_DIR)
        return

    logger.info(
        "Compiling %d agent(s) from %s%s",
        len(files), AGENTS_DIR,
        " (DRY-RUN)" if args.dry_run else "",
    )

    total_original = 0
    total_minified = 0
    compiled = 0

    for f in files:
        result = compile_agent(f, dry_run=args.dry_run)
        if result:
            compiled += 1
            if not args.dry_run:
                total_original += len(f.read_text(encoding="utf-8"))
                if result.exists():
                    total_minified += len(result.read_text(encoding="utf-8"))

    if compiled > 0 and not args.dry_run:
        total_savings = round(
            (1 - total_minified / max(total_original, 1)) * 100
        )
        logger.info(
            "Done: %d agents compiled. Total savings: %d%% (%d -> %d chars)",
            compiled, total_savings, total_original, total_minified,
        )
    elif args.dry_run:
        logger.info("Dry-run complete. Use without --dry-run to write files.")


if __name__ == "__main__":
    main()
