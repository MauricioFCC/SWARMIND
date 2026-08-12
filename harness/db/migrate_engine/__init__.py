"""DB Migration Engine — Logica central de migracion de bases de datos LanceDB.

Antes: harness/db/migrate_engine.py (538 lineas).
Ahora: paquete ``harness/db/migrate_engine/``:

- ``constants.py``: rutas por defecto y ``_get_current_collections``.
- ``inspect_mixin.py``: mixin ``_InspectMixin`` (scan/detect/stats).
- ``migrate_mixin.py``: mixin ``_MigrateMixin`` (migrate/rollback/core).
- ``core.py``: clase ``DBMigrator`` (estado + __init__).

Este ``__init__.py`` re-exporta TODOS los simbolos publicos del modulo
original para mantener backward-compat:

    from harness.db.migrate_engine import DBMigrator

Regla AGR: cada archivo del paquete queda por debajo de 500 lineas.
"""
from __future__ import annotations

from .constants import (
    DEFAULT_ARCHIVE_DIR,
    DEFAULT_IMPORT_DIR,
    DEFAULT_TARGET_DIR,
    HARNESS_DIR,
)
from .constants import (
    _get_current_collections as _get_current_collections,
)
from .core import DBMigrator

__all__ = [
    "DEFAULT_ARCHIVE_DIR",
    "DEFAULT_IMPORT_DIR",
    "DEFAULT_TARGET_DIR",
    "HARNESS_DIR",
    "DBMigrator",
]
