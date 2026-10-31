"""Migra datos de LanceDB a RuscaDB.

Uso:
    python scripts/migrate_lance_to_rusca.py [--lance-path PATH] [--rusca-path PATH] [--dry-run]

Lee todas las tablas de LanceDB y las replica en RuscaDB (escalares + vector).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import lancedb  # type: ignore[import-untyped]

from harness.memory_rag.ruscadb_store import RuscaDBStore


def migrate(lance_path: str, rusca_path: str, dry_run: bool = False) -> dict[str, int]:
    db = lancedb.connect(lance_path)
    tables = db.list_tables().tables if hasattr(db.list_tables(), "tables") else list(db.list_tables())
    store = None if dry_run else RuscaDBStore(db_path=rusca_path)
    counts: dict[str, int] = {}
    for tname in tables:
        tbl = db.open_table(tname)
        arrow_tbl = tbl.to_arrow()
        rows = arrow_tbl.to_pylist()
        n = len(rows)
        counts[tname] = n
        if dry_run:
            print("[dry-run] " + tname + ": " + str(n) + " rows")
            continue
        store.create_collection(tname)
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
        if vectors:
            store.insert(tname, vectors, metadata_list)
        print("migrated " + tname + ": " + str(n) + " rows")
    return counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lance-path", default=None)
    parser.add_argument("--rusca-path", default="ruscadb.db")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    lance_path = args.lance_path
    if lance_path is None:
        # default from memory config
        try:
            from harness.memory_rag.memory_config import get_memory_config
            lance_path = get_memory_config().lancedb_path
        except Exception:  # noqa: BLE001
            lance_path = "harness/db/lancedb"
    print("Lance path:", lance_path)
    print("Rusca path:", args.rusca_path)
    counts = migrate(lance_path, args.rusca_path, dry_run=args.dry_run)
    print("Totals:", counts)


if __name__ == "__main__":
    main()