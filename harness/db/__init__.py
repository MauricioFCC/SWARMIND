"""
Harness DB — Persistencia y migración de bases de datos LanceDB.

Subpackages:
- import/     : Punto de entrada para BDs legacy a migrar
- lancedb/    : Base de datos LanceDB activa (en .gitignore)
- _archived/  : Colecciones obsoletas archivadas durante migración
"""

from .migrate_db import DBMigrator

__all__ = [
    "DBMigrator",
]
