"""Tests de ``scripts/backup_memory.py`` con RuscaDB como backend nativo.

Contratos cubiertos:
  1. El backup se crea cuando SOLO existe RuscaDB (LanceDB archivada/vacia):
     antes el script abortaba y la memoria general quedaba sin respaldo.
  2. La restauracion copia los artefactos de ``backup/ruscadb/`` al central.
  3. ``_list_backups`` ordena por timestamp del nombre (no alfabeticamente),
     para que la rotacion con prefijos mixtos no borre backups recientes.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import backup_memory


@pytest.fixture()
def mem_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Apunta los globals del script a una raiz de memoria temporal."""
    (tmp_path / "data" / "lancedb").mkdir(parents=True)
    (tmp_path / "data" / "lancedb" / ".gitkeep").write_text("", encoding="utf-8")
    (tmp_path / "backups").mkdir()
    monkeypatch.setattr(backup_memory, "_MEMORY_ROOT", tmp_path)
    monkeypatch.setattr(backup_memory, "_RUSCA_DB", tmp_path / "data" / "ruscadb.db")
    monkeypatch.setattr(backup_memory, "_DB_DIR", tmp_path / "data" / "lancedb")
    monkeypatch.setattr(backup_memory, "_BACKUP_ROOT", tmp_path / "backups")
    monkeypatch.setattr(backup_memory, "_CONFIG_FILE", tmp_path / ".swarmind_config.json")
    monkeypatch.setattr(
        backup_memory,
        "_load_config",
        lambda: {
            "backup_enabled": True,
            "backup_interval_hours": 0,
            "backup_cadence": "manual",
            "backup_keep": 5,
        },
    )
    return tmp_path


def _escribir_ruscadb(root: Path, contenido: bytes = b"ruscadb-vivo") -> None:
    """Crea un ``data/ruscadb.db`` con contenido (no vacio = presente)."""
    db = root / "data" / "ruscadb.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_bytes(contenido)
    (db.parent / "ruscadb.wal").write_bytes(b"wal")
    (db.parent / "ruscadb.manifest.json").write_text("{}", encoding="utf-8")


def test_backup_con_solo_ruscadb(mem_root: Path) -> None:
    """Sin colecciones LanceDB, el backup de RuscaDB se crea igual."""
    _escribir_ruscadb(mem_root)

    ok = backup_memory._do_backup(force=True)

    assert ok is True
    backups = sorted((mem_root / "backups").glob("ruscadb_*"))
    assert len(backups) == 1, "No se creo el backup de RuscaDB"
    copia = backups[0] / "ruscadb"
    assert (copia / "ruscadb.db").read_bytes() == b"ruscadb-vivo"
    assert (copia / "ruscadb.wal").is_file()
    assert (copia / "ruscadb.manifest.json").is_file()


def test_backup_sin_ruscadb_ni_lancedb_no_hace_nada(mem_root: Path) -> None:
    """Sin ningun backend con datos, el backup se omite con warning."""
    assert backup_memory._do_backup(force=True) is False
    assert not list((mem_root / "backups").glob("*_*"))


def test_backup_incluye_ruscadb_y_lancedb_legado(mem_root: Path) -> None:
    """Instalacion mixta: se respaldan ambos backends en un solo directorio."""
    _escribir_ruscadb(mem_root)
    tabla = mem_root / "data" / "lancedb" / "rag_chunks.lance"
    (tabla / "data").mkdir(parents=True)
    (tabla / "data" / "fragment.bin").write_bytes(b"x")

    ok = backup_memory._do_backup(force=True)

    assert ok is True
    backup = next((mem_root / "backups").glob("ruscadb_*"))
    assert (backup / "ruscadb" / "ruscadb.db").is_file()
    assert (backup / "lancedb" / "rag_chunks.lance").is_dir()


def test_restore_ruscadb(mem_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Restaurar ``backup/ruscadb`` reemplaza el central con la copia."""
    _escribir_ruscadb(mem_root, contenido=b"viejo")
    backup = mem_root / "backups" / "ruscadb_20260101_000000" / "ruscadb"
    backup.mkdir(parents=True)
    (backup / "ruscadb.db").write_bytes(b"nuevo")
    (backup / "ruscadb.wal").write_bytes(b"wal-nuevo")
    monkeypatch.setattr(backup_memory, "_do_backup", lambda *a, **k: True)

    ok = backup_memory._restore(backup.parent)

    assert ok is True
    assert (mem_root / "data" / "ruscadb.db").read_bytes() == b"nuevo"


def test_restore_rechaza_backup_sin_backends(mem_root: Path) -> None:
    """Un directorio vacio no es un backup valido."""
    vacio = mem_root / "backups" / "ruscadb_20260101_000000"
    vacio.mkdir(parents=True)

    assert backup_memory._restore(vacio) is False


def test_list_backups_ordena_por_timestamp(mem_root: Path) -> None:
    """Prefijos mixtos: manda la fecha, no el orden alfabetico."""
    for nombre in (
        "lancedb_20260103_000000",
        "ruscadb_20260101_000000",
        "ruscadb_20260102_000000",
    ):
        (mem_root / "backups" / nombre).mkdir(parents=True)

    nombres = [p.name for p in backup_memory._list_backups()]

    assert nombres == [
        "lancedb_20260103_000000",
        "ruscadb_20260102_000000",
        "ruscadb_20260101_000000",
    ]
