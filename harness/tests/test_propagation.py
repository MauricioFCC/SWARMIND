"""Tests del motor de propagación incremental (scripts/propagation.py).

WHAT: manifiesto (fast path), content-addressing (solo escribe cambios),
atomicidad (sin temporales), exclusiones y no seguimiento de symlinks.

WHY: la propagación anterior copiaba todo el árbol en cada commit; este motor
debe ser idempotente, barato en la segunda pasada y seguro ante fallos.

WHERE: harness/tests — árboles temporales, sin tocar el global real.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(1, str(_SCRIPTS))

import propagation as prop


def _tree(root: Path) -> Path:
    """Crea un árbol fuente con dos archivos y un bytecode."""
    (root / "sub").mkdir(parents=True)
    (root / "a.txt").write_text("uno", encoding="utf-8")
    (root / "sub" / "b.txt").write_text("dos", encoding="utf-8")
    (root / "sub" / "__pycache__").mkdir()
    (root / "sub" / "__pycache__" / "b.pyc").write_bytes(b"bytecode")
    return root


def test_copia_inicial_y_manifiesto(tmp_path: Path) -> None:
    """La primera pasada copia todo lo no excluido y escribe el manifiesto."""
    src = _tree(tmp_path / "src")
    dst = tmp_path / "dst"
    manifest = prop.manifest_for(dst, "tree")
    stats = prop.sync_tree(src, dst, excludes=("__pycache__", "*.pyc"), manifest_path=manifest)
    assert stats.copied == 2
    assert (dst / "a.txt").read_text(encoding="utf-8") == "uno"
    assert not (dst / "sub" / "__pycache__").exists()
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert set(data["files"]) == {"a.txt", "sub/b.txt"}


def test_segunda_pasada_no_escribe(tmp_path: Path) -> None:
    """Con el manifiesto, la segunda pasada es fast path: 0 escrituras."""
    src = _tree(tmp_path / "src")
    dst = tmp_path / "dst"
    manifest = prop.manifest_for(dst, "tree")
    prop.sync_tree(src, dst, manifest_path=manifest)
    stats = prop.sync_tree(src, dst, manifest_path=manifest)
    assert stats.copied == 0
    assert stats.updated == 0
    assert stats.unchanged == 3


def test_cambio_de_contenido_actualiza(tmp_path: Path) -> None:
    """Un cambio real se copia y se contabiliza como updated."""
    src = _tree(tmp_path / "src")
    dst = tmp_path / "dst"
    manifest = prop.manifest_for(dst, "tree")
    prop.sync_tree(src, dst, manifest_path=manifest)
    target = src / "a.txt"
    target.write_text("OTRO", encoding="utf-8")
    os.utime(target, (target.stat().st_atime, target.stat().st_mtime + 5))
    stats = prop.sync_tree(src, dst, manifest_path=manifest)
    assert stats.updated == 1
    assert (dst / "a.txt").read_text(encoding="utf-8") == "OTRO"


def test_dry_run_no_escribe(tmp_path: Path) -> None:
    """--dry-run planifica pero no crea el destino."""
    src = _tree(tmp_path / "src")
    dst = tmp_path / "dst"
    stats = prop.sync_tree(src, dst, dry_run=True)
    assert stats.scanned == 3
    assert not dst.exists()


def test_sin_temporales_tras_copiar(tmp_path: Path) -> None:
    """La copia atómica no deja ficheros .tmp en el destino."""
    src = _tree(tmp_path / "src")
    dst = tmp_path / "dst"
    prop.sync_tree(src, dst)
    assert not list(dst.rglob("*.tmp-*"))


def test_sync_file_idempotente(tmp_path: Path) -> None:
    """sync_file no escribe si el contenido ya es idéntico."""
    source = tmp_path / "a.txt"
    target = tmp_path / "b.txt"
    source.write_text("igual", encoding="utf-8")
    target.write_text("igual", encoding="utf-8")
    assert prop.sync_file(source, target) is False
    source.write_text("distinto", encoding="utf-8")
    assert prop.sync_file(source, target) is True
    assert target.read_text(encoding="utf-8") == "distinto"


def test_symlink_no_se_sigue(tmp_path: Path) -> None:
    """Un symlink dentro del árbol no se propaga (anti escape)."""
    src = tmp_path / "src"
    src.mkdir()
    outside = tmp_path / "secreto.txt"
    outside.write_text("fuera", encoding="utf-8")
    try:
        (src / "link.txt").symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks no disponibles en este sistema")
    dst = tmp_path / "dst"
    prop.sync_tree(src, dst)
    assert not (dst / "link.txt").exists()


def test_manifiesto_corrupto_se_ignora(tmp_path: Path) -> None:
    """Un manifiesto ilegible no rompe el sync (se trata como vacío)."""
    manifest = tmp_path / "m.json"
    manifest.write_text("{no json", encoding="utf-8")
    assert prop.load_manifest(manifest) == {}


def test_excludes_por_nombre_y_ruta(tmp_path: Path) -> None:
    """Los patrones excluyen por nombre de parte o por ruta POSIX."""
    assert prop.is_excluded("a/__pycache__/x.pyc", ("__pycache__",))
    assert prop.is_excluded("db/datos.lance", ("db/*.lance",))
    assert not prop.is_excluded("db/esquema.sql", ("db/*.lance",))
