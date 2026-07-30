"""Tests para reset_state.py — limpieza de estado del harness."""
from __future__ import annotations

from pathlib import Path

from harness.reset_state import (
    _allow_temp_dirs,
    empty_dir_keep_gitkeep,
    rm_dir,
    rm_file,
)

# Permitir directorios temporales en tests (seguridad: path traversal check)
_allow_temp_dirs()


class TestRmDir:
    def test_elimina_directorio_existente(self, tmp_path: Path) -> None:
        d = tmp_path / "testdir"
        d.mkdir()
        assert d.exists()
        rm_dir(d)
        assert not d.exists()

    def test_ignora_si_no_existe(self, tmp_path: Path) -> None:
        d = tmp_path / "no_existe"
        assert not d.exists()
        rm_dir(d)  # no debe fallar


class TestRmFile:
    def test_elimina_archivo_existente(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("data")
        assert f.exists()
        rm_file(f)
        assert not f.exists()

    def test_ignora_si_no_existe(self) -> None:
        f = Path("/ruta/inexistente/archivo.txt")
        rm_file(f)  # no debe fallar


class TestEmptyDirKeepGitkeep:
    def test_vacia_directorio_conservando_gitkeep(self, tmp_path: Path) -> None:
        d = tmp_path / "mydir"
        d.mkdir()
        gitkeep = d / ".gitkeep"
        gitkeep.write_text("")
        other = d / "data.txt"
        other.write_text("delete me")
        sub = d / "subdir"
        sub.mkdir()
        empty_dir_keep_gitkeep(d)
        assert gitkeep.exists()
        assert not other.exists()
        assert not sub.exists()

    def test_ignora_si_no_existe(self) -> None:
        empty_dir_keep_gitkeep(Path("/ruta/inexistente"))  # no debe fallar
