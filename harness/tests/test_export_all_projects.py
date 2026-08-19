"""Tests TDD del script universal de export a Drive (export_all_projects.py).

Cubre la lógica del script con rutas TEMPORALES (tmp_path) — nunca toca el
Drive real ni rutas personales. Verifica:
  - Descubrimiento universal de proyectos (git, estructura, mín. archivos).
  - Protección de ZIPs externos (no matchean patrón de proyecto).
  - Limpieza de ZIPs antiguos dejando solo el más reciente por fecha.
  - Filtro no-git (excluye .venv, node_modules, caches).
  - Git: solo archivos commiteados/no ignorados.

Requiere git disponible y la política ADR-0035 (rutas portables).
"""
from __future__ import annotations

import subprocess
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(1, str(ROOT))

import scripts.export_all_projects as export_mod


@pytest.fixture()
def env_isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Aísla DEV_SPACE y EXPORT_BASE en directorios temporales.

    Args:
        tmp_path: Directorio temporal de pytest.
        monkeypatch: Fixture para parchear módulo/entorno.

    Returns:
        Tupla (dev_space, export_base) temporales.
    """
    dev_space = tmp_path / "dev"
    export_base = tmp_path / "exports"
    dev_space.mkdir()
    export_base.mkdir()
    monkeypatch.setattr(export_mod, "DEV_SPACE", dev_space)
    monkeypatch.setattr(export_mod, "EXPORT_BASE", export_base)
    return dev_space, export_base


def _make_git_repo(root: Path) -> None:
    """Inicializa un repo git con un archivo commiteado y uno sin commitear.

    Args:
        root: Ruta donde inicializar el repo.
    """
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True, capture_output=True)
    (root / "tracked.py").write_text("x = 1\n", encoding="utf-8")
    (root / "untracked.py").write_text("y = 2\n", encoding="utf-8")
    (root / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    (root / "ignored.txt").write_text("zzz\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)
    (root / "new_file.py").write_text("z = 3\n", encoding="utf-8")


class TestIsProjectDir:
    """Criterio universal de proyecto (sin hardcode de nombres)."""

    def test_git_repo_is_project(self, tmp_path: Path) -> None:
        """Un dir con .git/ es proyecto aunque tenga 1 archivo."""
        repo = tmp_path / "repo"
        _make_git_repo(repo)
        assert export_mod._is_project_dir(repo) is True

    def test_dir_with_subdirs_is_project(self, tmp_path: Path) -> None:
        """Un dir con estructura (subdirectorios) es proyecto."""
        proj = tmp_path / "proj"
        (proj / "src").mkdir(parents=True)
        assert export_mod._is_project_dir(proj) is True

    def test_many_files_is_project(self, tmp_path: Path) -> None:
        """Un dir con >= MIN_PROJECT_FILES archivos es proyecto."""
        proj = tmp_path / "proj"
        proj.mkdir()
        for i in range(export_mod.MIN_PROJECT_FILES):
            (proj / f"f{i}.py").write_text("x = 1\n", encoding="utf-8")
        assert export_mod._is_project_dir(proj) is True

    def test_single_file_dir_is_not_project(self, tmp_path: Path) -> None:
        """Un dir trivial (1 archivo suelto, sin git/estructura) NO es proyecto."""
        data = tmp_path / "data"
        data.mkdir()
        (data / "settings.json").write_text("{}\n", encoding="utf-8")
        assert export_mod._is_project_dir(data) is False

    def test_hidden_dir_is_not_project(self, tmp_path: Path) -> None:
        """Un dir oculto (prefijo .) NO es proyecto."""
        hidden = tmp_path / ".cache"
        hidden.mkdir()
        assert export_mod._is_project_dir(hidden) is False


class TestDiscoverProjects:
    """Descubrimiento universal: nuevos proyectos se detectan solos."""

    def test_discovers_mixed_projects(self, env_isolated: tuple[Path, Path]) -> None:
        """Detecta git repos y dirs con estructura; omite trivia/ocultos."""
        dev_space, _ = env_isolated
        _make_git_repo(dev_space / "repo_a")
        (dev_space / "proj_b" / "src").mkdir(parents=True)
        (dev_space / "proj_b" / "src" / "main.py").write_text("x = 1\n", encoding="utf-8")
        (dev_space / "data").mkdir()
        (dev_space / "data" / "settings.json").write_text("{}\n", encoding="utf-8")
        (dev_space / ".hidden").mkdir()

        tags = [tag for tag, _ in export_mod.discover_projects()]
        assert "repo_a" in tags
        assert "proj_b" in tags
        assert "data" not in tags
        assert ".hidden" not in tags

    def test_new_project_detected_automatically(self, env_isolated: tuple[Path, Path]) -> None:
        """Añadir un proyecto nuevo NO requiere editar el script."""
        dev_space, _ = env_isolated
        (dev_space / "nuevo_proyecto" / "src").mkdir(parents=True)
        tags = [tag for tag, _ in export_mod.discover_projects()]
        assert "nuevo_proyecto" in tags


class TestGitTrackedFiles:
    """Solo archivos commiteados/no ignorados."""

    def test_lists_committed_and_untracked_no_ignored(self, tmp_path: Path) -> None:
        """Incluye tracked + untracked; excluye .gitignore-ignored."""
        repo = tmp_path / "repo"
        _make_git_repo(repo)
        files = export_mod.git_tracked_files(repo)
        assert "tracked.py" in files
        assert "new_file.py" in files
        assert "ignored.txt" not in files

    def test_non_repo_returns_empty(self, tmp_path: Path) -> None:
        """Un dir sin git devuelve lista vacía (sin lanzar)."""
        plain = tmp_path / "plain"
        plain.mkdir()
        assert export_mod.git_tracked_files(plain) == []


class TestFilterProjectFiles:
    """Filtro no-git: excluye venv, node_modules y caches."""

    def test_excludes_venv_and_node_modules(self, tmp_path: Path) -> None:
        """Los dirs pesados se excluyen del filtro no-git."""
        proj = tmp_path / "proj"
        (proj / ".venv" / "Lib").mkdir(parents=True)
        (proj / ".venv" / "Lib" / "x.py").write_text("x\n", encoding="utf-8")
        (proj / "node_modules" / "pkg").mkdir(parents=True)
        (proj / "node_modules" / "pkg" / "i.js").write_text("i\n", encoding="utf-8")
        (proj / "src").mkdir()
        (proj / "src" / "main.py").write_text("m\n", encoding="utf-8")

        files = export_mod.filter_project_files(proj)
        assert "src/main.py" in files
        assert not any("venv" in f or "node_modules" in f for f in files)

    def test_excludes_pyc(self, tmp_path: Path) -> None:
        """Los .pyc se excluyen del filtro."""
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "a.py").write_text("a\n", encoding="utf-8")
        (proj / "a.pyc").write_bytes(b"x")
        files = export_mod.filter_project_files(proj)
        assert "a.py" in files
        assert "a.pyc" not in files


class TestCleanupOldZips:
    """Limpieza: solo el más reciente por fecha; externos intactos."""

    def _create_zip(self, export_base: Path, name: str) -> None:
        """Crea un ZIP vacío con el nombre dado."""
        with zipfile.ZipFile(export_base / name, "w") as zf:
            zf.writestr("dummy.txt", "x")

    def test_keeps_newest_removes_old(self, env_isolated: tuple[Path, Path]) -> None:
        """Dos ZIPs del mismo proyecto: queda el de fecha más reciente."""
        _, export_base = env_isolated
        self._create_zip(export_base, "repo_2026-08-08.zip")
        self._create_zip(export_base, "repo_2026-08-09.zip")

        removed = export_mod.cleanup_old_zips("repo")
        assert removed == 1
        assert (export_base / "repo_2026-08-08.zip").exists() is False
        assert (export_base / "repo_2026-08-09.zip").exists() is True

    def test_external_zips_untouched(self, env_isolated: tuple[Path, Path]) -> None:
        """ZIPs ajenos (sin patrón de proyecto) NUNCA se tocan."""
        _, export_base = env_isolated
        self._create_zip(export_base, "repo_2026-08-09.zip")
        self._create_zip(export_base, "LITISCOL_SCRAP.zip")
        self._create_zip(export_base, "LUMINA LANG.zip")
        self._create_zip(export_base, "PRIVATE_PUSH.zip")

        export_mod.cleanup_old_zips("repo")
        assert (export_base / "LITISCOL_SCRAP.zip").exists()
        assert (export_base / "LUMINA LANG.zip").exists()
        assert (export_base / "PRIVATE_PUSH.zip").exists()

    def test_legacy_tag_zips_not_touched(self, env_isolated: tuple[Path, Path]) -> None:
        """ZIPs de tags que ya no existen (proyectos viejos) no se borran."""
        _, export_base = env_isolated
        self._create_zip(export_base, "CQE_2026-07-24.zip")
        self._create_zip(export_base, "SWARMIND_2026-08-09.zip")

        export_mod.cleanup_old_zips("SWARMIND")
        assert (export_base / "CQE_2026-07-24.zip").exists()
        assert (export_base / "SWARMIND_2026-08-09.zip").exists()

    def test_no_matching_returns_zero(self, env_isolated: tuple[Path, Path]) -> None:
        """Sin ZIPs del proyecto: no elimina nada."""
        _, export_base = env_isolated
        self._create_zip(export_base, "otro_2026-08-09.zip")
        assert export_mod.cleanup_old_zips("repo") == 0


class TestPortablePaths:
    """ADR-0035: rutas portables sin info personal hardcodeada."""

    def test_script_source_has_no_personal_path(self) -> None:
        """El fuente del script no contiene rutas personales reales."""
        source = (ROOT / "scripts" / "export_all_projects.py").read_text(encoding="utf-8")
        assert "C:\\Users\\" not in source
        assert "/home/" not in source
        assert "/Users/" not in source

    def test_uses_env_vars_with_fallback(self) -> None:
        """Las rutas se resuelven con env vars (fallback Path.home())."""
        source = (ROOT / "scripts" / "export_all_projects.py").read_text(encoding="utf-8")
        assert "os.environ.get" in source
        assert "SWARMIND_EXPORT_BASE" in source
        assert "DEV_SPACE_ROOT" in source
        assert "Path.home()" in source

    def test_today_is_utc_iso(self) -> None:
        """TODAY es fecha ISO en UTC (sin timezone local)."""
        assert datetime.now(UTC).date().isoformat() == export_mod.TODAY
        # formato YYYY-MM-DD estricto
        parts = export_mod.TODAY.split("-")
        assert len(parts) == 3 and all(p.isdigit() for p in parts)
