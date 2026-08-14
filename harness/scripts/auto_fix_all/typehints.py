"""auto_fix_all typehints — agregado de type hints faltantes.

Extraccion mecanica del modulo original
``harness/scripts/auto_fix_all.py`` (sin cambios de logica ni firmas).
"""
from __future__ import annotations

import ast
import logging
import re

logger = logging.getLogger("harness.scripts.auto_fix_all")


# =============================================================================
# 2. Missing type hints
# =============================================================================

def _should_skip_type_hint(node_name: str) -> bool:
    """Skip dunder methods like __init__, __str__, etc."""
    return node_name.startswith("__") and node_name.endswith("__")


def _fix_missing_type_hints(content: str, filepath: str) -> tuple[str, int]:
    """Add -> None to functions without return type hints.

    We can only safely add -> None when we detect no return value.
    We add -> Any when we cannot determine the return type.
    """
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return content, 0

    # Collect line numbers and fix info
    fixes: list[tuple[int, str]] = []  # (line_number, original_suffix, replacement_suffix)
    replacements = 0

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if _should_skip_type_hint(node.name):
            continue

        # Check if function already has return annotation
        if node.returns is not None:
            continue

        # Check if function actually returns something
        has_return_value = False
        for child in ast.walk(node):
            if isinstance(child, ast.Return) and child.value is not None:
                has_return_value = True
                break

        if has_return_value:
            # We can't determine the type -> add -> Any
            suffix = " -> Any"
            # need to ensure 'Any' is imported
        else:
            suffix = " -> None"

        # Find the function definition line in source
        lineno = node.lineno
        if lineno is None:
            continue

        # Try to find the exact line in the source
        lines = content.split("\n")
        idx = lineno - 1
        if idx < 0 or idx >= len(lines):
            continue

        line = lines[idx]
        # Match the function definition and find where to insert
        # Pattern: "def func_name(params):" or "def func_name(params) -> type:"
        # We need to add after closing paren and before ":"
        match = re.match(r'^(\s*async\s+)?def\s+\w+\s*\(', line)
        if not match:
            # The function def might span multiple lines
            # Look for the closing paren
            continue

        # Find the last '):' or ':' and add annotation before it
        if "):" in line and "->" not in line:
            new_line = line.replace("):", f"){suffix}:", 1)
            if line != new_line:
                fixes.append((idx, line, new_line))
                replacements += 1
        elif line.strip().endswith(":"):
            # Async: "async def func():" or multi-line
            # Try simpler approach: replace def line
            new_line = line.rstrip()
            if new_line.endswith(":") and not new_line.rstrip().endswith("):"):
                # Find the closing paren position
                pass  # Complex case, skip

    # Apply fixes
    lines = content.split("\n")
    for idx, original, new_line in sorted(fixes, key=lambda x: -x[0]):
        if lines[idx] == original:
            lines[idx] = new_line

    new_content = "\n".join(lines)

    # Ensure Any is imported if needed
    if replacements > 0:
        new_content = _ensure_typing_import(new_content, need_any=True)

    return new_content, replacements


def _ensure_typing_import(content: str, need_any: bool = True) -> str:
    """Ensure 'from typing import Any' is present when needed."""
    if not need_any:
        return content

    # Check if Any is already imported
    for line in content.split("\n"):
        if "Any" in line and ("from typing" in line or "import typing" in line):
            return content

    # Find existing typing import
    lines = content.split("\n")
    for i, line in enumerate(lines):
        m = re.match(r'^from typing import\s+(.*)', line)
        if m:
            existing = m.group(1)
            if "Any" not in existing:
                lines[i] = f"from typing import {existing.strip()}, Any"
            return "\n".join(lines)

    # No typing import exists; add one
    # Find import section end
    import_end = 0
    for i, line in enumerate(lines):
        if re.match(r'^(import |from )', line):
            import_end = i + 1

    lines.insert(import_end, "from typing import Any")
    return "\n".join(lines)
