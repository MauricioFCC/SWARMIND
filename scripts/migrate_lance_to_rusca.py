"""Migra datos de LanceDB a RuscaDB y deja el central solo con RuscaDB.

Uso:
    python scripts/migrate_lance_to_rusca.py [--lance-path PATH] [--rusca-path PATH]
        [--dry-run] [--skip-volatile] [--archive-lance]

- ``--skip-volatile``: no migra ``semantic_cache``/``agent_workspace_logs``
  (caché regenerable; se recrea vacía en RuscaDB).
- ``--archive-lance``: tras migrar, mueve ``data/lancedb`` a
  ``<MEMORY_ROOT>/backups/lancedb_pre_rusca_<timestamp>`` (no borra: archiva)
  y deja ``data/lancedb/.gitkeep`` para compatibilidad de rutas.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import lancedb  # type: ignore[import-untyped]

from harness.memory_rag.ruscadb_store import RuscaDBStore

#: Colecciones volátiles: cache/logs regenerables, no se migran por default
#: con ``--skip-volatile``.
VOLATILE_COLLECTIONS: frozenset[str] = frozenset(
    {"semantic_cache", "agent_workspace_logs"}
)


def migrate(
    lance_path: str,
    rusca_path: str,
    dry_run: bool = False,
    skip_volatile: bool = False,
) -> dict[str, int]:
    """Migra las tablas LanceDB a colecciones RuscaDB.

    Args:
        lance_path: Directorio LanceDB de origen.
        rusca_path: Archivo RuscaDB de destino.
        dry_run: Solo reportar filas, sin escribir.
        skip_volatile: Excluir las colecciones de caché regenerable.

    Returns:
        Mapa nombre de colección -> filas migradas.
    """
    db = lancedb.connect(lance_path)
    tables = db.list_tables().tables if hasattr(db.list_tables(), "tables") else list(db.list_tables())
    store = None if dry_run else RuscaDBStore(db_path=rusca_path)
    counts: dict[str, int] = {}
    for tname in tables:
        if skip_volatile and tname in VOLATILE_COLLECTIONS:
            print("[skip-volatile] " + tname + ": no se migra (cache regenerable)")
            counts[tname] = 0
            continue
        tbl = db.open_table(tname)
        arrow_tbl = tbl.to_arrow()
        rows = arrow_tbl.to_pylist()
        n = len(rows)
        counts[tname] = n
        if dry_run:
            print("[dry-run] " + tname + ": " + str(n) + " rows")
            continue
        store.create_collection(tname)
        if not rows:
            print("created " + tname + ": 0 rows (schema)")
            continue
        vectors = []
        metadata_list = []
        for row in rows:
            vec = row.get("vector", None)
            if vec is None:
                vec = []
            else:
                vec = list(vec) if not isinstance(vec, list) else vec
            vectors.append(vec)
            meta = {}
            raw = row.get("metadata", None)
            if isinstance(raw, str):
                try:
                    meta = json.loads(raw)
                except json.JSONDecodeError:
                    meta = {"raw": raw}
            elif isinstance(raw, dict):
                meta = raw
            for col in row:
                if col not in ("vector", "metadata", "id"):
                    try:
                        meta[col] = row.get(col)
                    except Exception:  # noqa: BLE001, S110
                        pass
            metadata_list.append(meta)
        store.insert(tname, vectors, metadata_list)
        print("migrated " + tname + ": " + str(n) + " rows")
    if store is not None:
        store.close()
    return counts


def archive_lance(lance_path: str, memory_root: str) -> Path | None:
    """Archiva el directorio LanceDB bajo ``backups/`` y deja ``.gitkeep``.

    Args:
        lance_path: Directorio LanceDB a archivar.
        memory_root: Raíz de la memoria central (destino ``backups/``).

    Returns:
        Ruta del archivo creado, o ``None`` si no había directorio.
    """
    origen = Path(lance_path)
    if not origen.is_dir() or not any(origen.iterdir()):
        print("archive: nada que archivar en " + str(origen))
        return None
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    destino = Path(memory_root) / "backups" / f"lancedb_pre_rusca_{ts}"
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(origen), str(destino))
    origen.mkdir(parents=True, exist_ok=True)
    (origen / ".gitkeep").touch()
    print("archive: " + str(origen) + " -> " + str(destino))
    return destino


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lance-path", default=None)
    parser.add_argument("--rusca-path", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--skip-volatile",
        action="store_true",
        help="No migrar semantic_cache/agent_workspace_logs (cache regenerable)",
    )
    parser.add_argument(
        "--archive-lance",
        action="store_true",
        help="Archivar data/lancedb en backups/ tras migrar (dejar solo RuscaDB)",
    )
    args = parser.parse_args()

    from harness.memory_rag.memory_config import get_memory_config

    config = get_memory_config()
    lance_path = args.lance_path or config.lancedb_path
    rusca_path = args.rusca_path or config.ruscadb_path or "ruscadb.db"
    print("Lance path:", lance_path)
    print("Rusca path:", rusca_path)
    counts = migrate(
        lance_path,
        rusca_path,
        dry_run=args.dry_run,
        skip_volatile=args.skip_volatile,
    )
    print("Totals:", counts)
    if args.archive_lance and not args.dry_run:
        memory_root = Path(rusca_path).resolve().parent.parent
        archive_lance(lance_path, str(memory_root))



if __name__ == "__main__":
    main()