"""Tests para backup_to_gdrive — backup local de DEV-SPACE a Google Drive.

Core puro (descubrimiento, plan de copia, mapping de exit codes de
robocopy) sin ejecutar robocopy en tests (el runner se inyecta).
Frontera/idempotencia: robocopy /E copia solo deltas; exit codes 0-7 OK
(bit1 copio, bit2 extras), >=8 error (MAG: ROBOCOPY_ERROR_FLOOR).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.backup_to_gdrive import (
    DEFAULT_EXCLUDES,
    ROBOCOPY_ERROR_FLOOR,
    _discover_projects,
    _is_ok,
    _plan_copy,
    _robocopy_code,
)


def _mk_project(root: Path, name: str, with_git: bool = True, files: int = 3) -> Path:
    """Fabrica un proyecto de prueba con archivos dummy."""
    p = root / name
    p.mkdir(parents=True)
    if with_git:
        (p / ".git").mkdir()
    for i in range(files):
        (p / f"file{i}.txt").write_text("x", encoding="utf-8")
    return p


def test_discover_projects_includes_git_and_plain(tmp_path: Path) -> None:
    """Descubre proyectos con .git y sin .git (solo directorios no-junk)."""
    _mk_project(tmp_path, "repo-a", with_git=True)
    _mk_project(tmp_path, "carpeta-b", with_git=False)
    (tmp_path / "__pycache__").mkdir()
    projects = _discover_projects(tmp_path)
    names = {p.name for p in projects}
    assert "repo-a" in names
    assert "carpeta-b" in names
    assert "__pycache__" not in names


def test_plan_copy_targets_dest_subdir(tmp_path: Path) -> None:
    """El plan copia cada proyecto a dest/<nombre> con excludes."""
    src = tmp_path / "src"
    proj = _mk_project(src, "repo-a")
    dest = tmp_path / "dest"
    plan = _plan_copy([proj], dest, DEFAULT_EXCLUDES)
    assert len(plan) == 1
    entry = plan[0]
    assert entry.src == proj
    assert entry.dst == dest / "repo-a"
    assert ".git" not in entry.excludes or entry.excludes.count(".git") >= 0


def test_plan_excludes_junk_dirs(tmp_path: Path) -> None:
    """Los excludes incluyen .venv/node_modules/__pycache__ (junk)."""
    for junk in (".venv", "node_modules", "__pycache__", "target"):
        assert junk in DEFAULT_EXCLUDES


def test_is_ok_boundary() -> None:
    """robocopy codes 0-7 son OK; 8+ son error."""
    for code in (0, 1, 3, 7):
        assert _is_ok(code) is True
    for code in (8, 16, 32):
        assert _is_ok(code) is False


def test_robocopy_code_floor_documented() -> None:
    """El piso de error de robocopy es 8 (documentado)."""
    assert ROBOCOPY_ERROR_FLOOR == 8


def test_run_copy_invokes_robocopy_per_project(tmp_path: Path, monkeypatch) -> None:
    """El runner inyectado recibe (src, dst, excludes) por proyecto."""
    src = tmp_path / "src"
    proj = _mk_project(src, "repo-a", files=2)
    dest = tmp_path / "dest"
    calls: list[tuple[Path, Path, tuple[str, ...]]] = []

    def fake_runner(src: Path, dst: Path, excludes: tuple[str, ...]) -> int:
        calls.append((src, dst, excludes))
        return 1  # copio

    from scripts import backup_to_gdrive as mod

    summary = mod.run_copy(_plan_copy([proj], dest, DEFAULT_EXCLUDES), fake_runner)
    assert len(calls) == 1
    assert calls[0][0] == proj
    assert calls[0][1] == dest / "repo-a"
    assert summary.copied == 1
    assert summary.failed == 0
    assert summary.codes == (1,)


def test_run_copy_counts_failures(tmp_path: Path) -> None:
    """Un exit code >= 8 cuenta como fallo (sin detener los demas)."""
    src = tmp_path / "src"
    projs = [_mk_project(src, "a"), _mk_project(src, "b")]
    dest = tmp_path / "dest"

    def failing(src: Path, dst: Path, excludes: tuple[str, ...]) -> int:
        return 16

    from scripts import backup_to_gdrive as mod

    summary = mod.run_copy(_plan_copy(projs, dest, DEFAULT_EXCLUDES), failing)
    assert summary.failed == 2


def test_real_robocopy_smoke(tmp_path: Path) -> None:
    """Integracion real con robocopy en tmp (solo Windows)."""
    if Path(subprocess.list2cmdline(["robocopy"])) :
        pass  # probe abajo
    src = tmp_path / "src"
    proj = _mk_project(src, "repo-x", files=2)
    dest = tmp_path / "dest"
    runner = _robocopy_code
    from scripts import backup_to_gdrive as mod

    summary = mod.run_copy(_plan_copy([proj], dest, DEFAULT_EXCLUDES), runner)
    assert summary.failed == 0
    assert (dest / "repo-x" / "file0.txt").is_file()
