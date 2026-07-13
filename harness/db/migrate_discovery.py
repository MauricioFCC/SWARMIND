"""
DB Migration Discovery — Descubrimiento recursivo de colecciones y schemas.

Extraído de migrate_db.py para separar concerns.

Patrón RECURSIVO:
  - discover_collections_recursive(): descubre colecciones LanceDB recursivamente
  - detect_format(): compara schemas entre versiones
  - probe_db(): inspecciona una base de datos
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Recursive discovery
# ---------------------------------------------------------------------------


def discover_collections_recursive(db_path: str) -> List[str]:
    """
    Descubre colecciones LanceDB recursivamente.

    Args:
        db_path: Ruta a la base de datos LanceDB

    Returns:
        Lista de nombres de colecciones
    """
    lancedb = _try_import_lancedb()
    if lancedb is None:
        return []

    try:
        db = lancedb.connect(db_path)
        return list(db.list_tables().tables)
    except Exception:
        return []


def _try_import_lancedb():
    """Safely attempt to import lancedb; return None on failure."""
    try:
        import lancedb  # type: ignore[import-untyped]
        return lancedb
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------


def detect_format(
    db_path: str,
    current_collections: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Inspecciona una base LanceDB y la compara con las colecciones actuales.

    Args:
        db_path: Ruta a la base de datos LanceDB
        current_collections: Dict de colecciones actuales (DEFAULT_COLLECTIONS)

    Returns:
        Dict con status, collections, differences
    """
    result: Dict[str, Any] = {
        "status": "compatible",
        "collections": [],
        "differences": [],
    }

    lancedb = _try_import_lancedb()
    if lancedb is None:
        return {
            "status": "unknown",
            "collections": [],
            "differences": ["LanceDB no instalado"],
        }

    try:
        db = lancedb.connect(db_path)
    except Exception as exc:
        return {
            "status": "unknown",
            "collections": [],
            "differences": [f"No se pudo abrir la BD: {exc}"],
        }

    old_tables = set(db.list_tables().tables)
    new_tables = set(current_collections.keys())

    result["collections"] = sorted(old_tables)

    # Colecciones que ya no existen en el schema actual
    removed = old_tables - new_tables
    if removed:
        result["differences"].append(
            "Colecciones obsoletas (ya no existen en schema actual): "
            f"{', '.join(sorted(removed))}"
        )
        result["status"] = "needs_migration"

    # Verificar que las colecciones compartidas se pueden leer
    for name in sorted(old_tables & new_tables):
        try:
            tbl = db.open_table(name)
            _ = tbl.head(1).to_pylist()
        except Exception as exc:
            result["differences"].append(
                f"'{name}': error al leer datos: {exc}"
            )
            result["status"] = "unknown"

    # Colecciones nuevas que no existian
    new_only = new_tables - old_tables
    if new_only:
        result["differences"].append(
            f"Nuevas colecciones a crear: {', '.join(sorted(new_only))}"
        )

    return result


# ---------------------------------------------------------------------------
# DB probing
# ---------------------------------------------------------------------------


def probe_db(path: str) -> Optional[Dict[str, Any]]:
    """
    Intenta abrir path como base LanceDB.
    Si tiene tablas, devuelve metadatos; si no, None.
    """
    lancedb = _try_import_lancedb()
    if lancedb is None:
        return None

    try:
        db = lancedb.connect(path)
        tables = db.list_tables().tables
        if not tables:
            return None

        size = sum(f.stat().st_size for f in Path(path).rglob("*") if f.is_file())
        return {
            "path": path,
            "name": os.path.basename(path),
            "collections": tables,
            "estimated_size": size,
            "estimated_size_human": _human_size(size),
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _human_size(size_bytes: int) -> str:
    """Formatea bytes a representacion legible."""
    if size_bytes == 0:
        return "0 B"
    units = ("B", "KB", "MB", "GB")
    size = float(size_bytes)
    for unit in units:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"
