"""auto_fix_all constants — rutas y alcance de la correccion masiva.

Extraccion mecanica del modulo original
``harness/scripts/auto_fix_all.py`` (sin cambios de logica ni firmas).
"""
from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SCOPES = [
    PROJECT_ROOT / "harness",
    PROJECT_ROOT / ".opencode",
]

# Files to skip (auto-generated, vendor, etc.)
SKIP_FILES: set[str] = set()
