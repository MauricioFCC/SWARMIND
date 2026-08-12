"""auto_fix_all prints — reemplazo de print() por logging.

Extraccion mecanica del modulo original
``harness/scripts/auto_fix_all.py`` (sin cambios de logica ni firmas).
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger("harness.scripts.auto_fix_all")


# =============================================================================
# 1. print() -> logging replacement
# =============================================================================

def _replace_print_with_logging(content: str, filepath: str) -> tuple[str, int]:
    """Replace top-level print() calls with logger.info().

    Handles:
      - print("...") -> logger.info("...")
      - print(f"...") -> logger.info(f"...")
      - Skips print() inside comment blocks and string literals (heuristic)
      - Skips helper functions named _safe_print, _ok, _warn, _err, etc.

    Returns (modified_content, count_of_replacements).
    """
    lines = content.split("\n")
    replacements = 0
    new_lines: list[str] = []

    # Detect if file defines its own print helpers
    any(
        re.match(r'^def\s+_?(safe_print|ok|warn|err|bold|cyan)\s*\(', line)
        for line in lines
    )
    # Detect if file already uses print for CLI output pattern
    any(
        'if __name__ == "__main__"' in line or re.match(r'^def\s+main\s*\(', line)
        for line in lines
    )

    for line in lines:
        stripped = line.strip()

        # Skip imports
        if stripped.startswith(("import ", "from ")):
            new_lines.append(line)
            continue

        # Skip comments
        if stripped.startswith(("#", '"""', "'''")):
            new_lines.append(line)
            continue

        # Skip _safe_print, _ok, _warn, _err, _bold, _cyan - these are custom print wrappers
        if re.match(r'^_?(safe_print|ok|warn|err|bold|cyan)\s*\(', stripped):
            new_lines.append(line)
            continue

        # Skip print() that's part of a custom helper function definition
        if re.match(r'^def\s+_?print\w*\s*\(', stripped):
            new_lines.append(line)
            continue

        # Replace print("...") with logger.info("...")
        # Match: print(...) at start of line (possibly with indent)
        # Use a simple regex that captures the full print call
        match = re.match(r'^(\s*)print\s*\((.*)\)\s*$', line)
        if match:
            indent = match.group(1)
            args = match.group(2)

            # Skip if print is inside a string (simple heuristic - check for odd quotes)
            if args.count('"') % 2 != 0 or args.count("'") % 2 != 0:
                new_lines.append(line)
                continue

            # Convert to logger.info
            new_line = f'{indent}logger.info({args})'
            new_lines.append(new_line)
            replacements += 1
            continue

        # Handle multi-line print(
        if re.match(r'^(\s*)print\s*\($', line):
            indent = re.match(r'^(\s*)', line).group(1)
            new_lines.append(f'{indent}logger.info(')
            replacements += 1  # Assume single-line for now
            continue

        new_lines.append(line)

    return "\n".join(new_lines), replacements


def _ensure_logger_setup(content: str, filepath: str) -> str:
    """Ensure 'import logging' and 'logger = logging.getLogger(__name__)' are present."""
    lines = content.split("\n")
    has_import = any(
        re.match(r'^import logging\s*($|#)', line) or
        re.match(r'^from logging import', line)
        for line in lines
    )
    has_logger = any(
        re.match(r'^logger\s*=\s*logging\.getLogger', line)
        for line in lines
    )

    if has_import and has_logger:
        return content

    # Find the right insertion point (after all imports)
    import_end = 0
    for i, line in enumerate(lines):
        if re.match(r'^(import |from )', line) or line.strip() == "":
            if re.match(r'^(import |from )', line):
                import_end = i + 1
        else:
            if import_end > 0:
                break

    if not has_import:
        lines.insert(import_end, "import logging")
        import_end += 1

    if not has_logger:
        lines.insert(import_end, "logger = logging.getLogger(__name__)")

    return "\n".join(lines)
