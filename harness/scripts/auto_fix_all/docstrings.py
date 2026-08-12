"""auto_fix_all docstrings — agregado de docstrings faltantes.

Extraccion mecanica del modulo original
``harness/scripts/auto_fix_all.py`` (sin cambios de logica ni firmas).
"""
from __future__ import annotations

import ast
import logging
import re

logger = logging.getLogger("harness.scripts.auto_fix_all")


# =============================================================================
# 3. Missing docstrings
# =============================================================================

SIMPLE_DOCSTRINGS: dict[str, str] = {
    "__init__": """Inicializa la instancia de la clase.""",
    "__str__": """Retorna representacion en string del objeto.""",
    "__repr__": """Retorna representacion oficial del objeto.""",
    "__len__": """Retorna la longitud del objeto.""",
    "__iter__": """Itera sobre los elementos del objeto.""",
    "__contains__": """Verifica si un elemento esta contenido.""",
}

def _should_skip_docstring(name: str) -> bool:
    """Skip private methods (but not dunders) for docstring generation."""
    return name.startswith("_") and not (name.startswith("__") and name.endswith("__"))


def _fix_missing_docstrings(content: str, filepath: str) -> tuple[str, int]:
    """Add simple docstrings to functions/classes that lack them."""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return content, 0

    lines = content.split("\n")
    replacements = 0
    fix_positions: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if ast.get_docstring(node):
                continue
            if _should_skip_docstring(node.name):
                continue

            name = node.name
            lineno = node.lineno
            if lineno is None or lineno < 1 or lineno > len(lines):
                continue

            idx = lineno - 1
            line = lines[idx]

            # Generate docstring based on function name
            if name in SIMPLE_DOCSTRINGS:
                doc = SIMPLE_DOCSTRINGS[name]
            else:
                # Convert snake_case to readable phrase
                readable = name.replace("_", " ").strip()
                doc = f"{readable[0].upper()}{readable[1:]}."

            # Find the body start after the def line and colon
            # Simple case: single-line def
            indent_match = re.match(r'^(\s*)', line)
            indent = indent_match.group(1) if indent_match else ""
            body_indent = indent + "    "

            # Check if next line is already indented (body exists)
            insertion_idx = idx + 1
            if insertion_idx < len(lines) and lines[insertion_idx].strip() in ("", "#"):
                insertion_idx += 1

            doc_line = f'{body_indent}"""{doc}"""'

            # Check if docstring already exists nearby
            nearby = "\n".join(lines[max(0, idx):min(len(lines), idx + 5)])
            if f'"""{doc[:10]}' in nearby:
                continue

            fix_positions.append((insertion_idx, doc_line))
            replacements += 1

        elif isinstance(node, ast.ClassDef):
            if ast.get_docstring(node):
                continue
            if node.name.startswith("_"):
                continue

            lineno = node.lineno
            if lineno is None or lineno < 1 or lineno > len(lines):
                continue

            idx = lineno - 1
            line = lines[idx]
            indent_match = re.match(r'^(\s*)', line)
            indent = indent_match.group(1) if indent_match else ""
            body_indent = indent + "    "

            readable = node.name.replace("_", " ").strip()
            doc = f"""{readable[0].upper()}{readable[1:]}."""

            insertion_idx = idx + 1
            if insertion_idx < len(lines) and lines[insertion_idx].strip() in ("", "#"):
                insertion_idx += 1

            # Check for existing docstring
            nearby = "\n".join(lines[max(0, idx):min(len(lines), idx + 5)])
            if f'"""{doc[:10]}' in nearby:
                continue

            doc_line = f'{body_indent}"""{doc}"""'
            fix_positions.append((insertion_idx, doc_line))
            replacements += 1

    # Apply fixes in reverse order to preserve line numbers
    for idx, doc_line in sorted(fix_positions, key=lambda x: -x[0]):
        lines.insert(idx, doc_line)

    return "\n".join(lines), replacements
