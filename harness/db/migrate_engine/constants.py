"""DB Migration Engine constants — rutas por defecto y colecciones actuales.

Extraccion mecanica del modulo original
``harness/db/migrate_engine.py`` (sin cambios de logica ni firmas).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths (resolved relative to this file's location)
# ---------------------------------------------------------------------------

HARNESS_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_IMPORT_DIR = str(HARNESS_DIR / "db" / "import")
DEFAULT_TARGET_DIR = str(HARNESS_DIR / "db" / "lancedb")
DEFAULT_ARCHIVE_DIR = str(HARNESS_DIR / "db" / "_archived")


def _get_current_collections() -> dict[str, Any]:
    """Lazy-import DEFAULT_COLLECTIONS to avoid circular imports at module level."""
    from harness.memory_rag.lance_vector_store import DEFAULT_COLLECTIONS
    return DEFAULT_COLLECTIONS
