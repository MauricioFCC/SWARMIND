"""DB Migration Engine core — clase principal ``DBMigrator``.

Extraccion mecanica del modulo original
``harness/db/migrate_engine.py`` (sin cambios de logica ni firmas).
La clase compone los mixins por responsabilidad:

- ``_InspectMixin`` (inspect_mixin.py): scan_imports/detect_format/get_stats.
- ``_MigrateMixin`` (migrate_mixin.py): migrate/rollback/archivo.
"""
from __future__ import annotations

import logging
from typing import Any

from .constants import (
    DEFAULT_ARCHIVE_DIR,
    DEFAULT_IMPORT_DIR,
    DEFAULT_TARGET_DIR,
)
from .inspect_mixin import _InspectMixin
from .migrate_mixin import _MigrateMixin

logger = logging.getLogger("harness.db.migrate_engine")


class DBMigrator(_InspectMixin, _MigrateMixin):
    """
    Migrador de bases de datos LanceDB entre versiones del harness.

    Detecta BDs viejas en harness/db/import/, compara sus schemas contra
    el formato actual (LanceVectorStore.DEFAULT_COLLECTIONS) y migra los
    datos automaticamente, con backup previo y soporte de rollback.
    """

    def __init__(
        self,
        import_dir: str | None = None,
        target_dir: str | None = None,
        archive_dir: str | None = None,
    ) -> None:
        """Inicializa el migrador con directorios de import, target y archive."""
        self.import_dir = import_dir or DEFAULT_IMPORT_DIR
        self.target_dir = target_dir or DEFAULT_TARGET_DIR
        self.archive_dir = archive_dir or DEFAULT_ARCHIVE_DIR
        self._lancedb_module: Any = None  # lazy import
