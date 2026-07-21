"""
Migrador de bases de datos LanceDB entre versiones del harness.

REFACTOR: Ahora es un wrapper ligero que re-exporta desde módulos separados:
  - migrate_engine.py: Logica de migracion (DBMigrator)
  - migrate_cli.py: Interfaz CLI
  - migrate_discovery.py: Descubrimiento recursivo de colecciones

Modo de uso:
  1. Copia tu BD anterior a: harness/db/import/<nombre>/
  2. Ejecuta: python harness/db/migrate_db.py
  3. El script detecta, migra y confirma

O automaticamente al ejecutar: python harness/scripts/init.py
"""
from __future__ import annotations

from harness.db.migrate_cli import main  # noqa: F401
from harness.db.migrate_engine import DBMigrator  # noqa: F401

if __name__ == "__main__":
    main()
