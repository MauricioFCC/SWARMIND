"""Tests TDD para scripts/tdad_select.py — selección de tests impactados (TDAD minimal).

Cubre el selector TDAD (arXiv:2603.17973) de SWARMIND:
  - parseo de imports con ast (absolutos, relativos, externos, sintaxis inválida)
  - mapeo módulo -> test directo test_<modulo>.py
  - transitividad A->B->C (reverse BFS sobre el grafo de dependencias)
  - deduplicación y orden estable (idempotencia)
  - CLI con --dry-run / --run / --exit-code (monkeypatch + capsys)
  - archivo sin test asociado (aviso, sin error) y ruta inexistente (WHAT+WHY+WHERE)

Tests puros: tmp_path para el pseudo-repo, sin red, sin LanceDB.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# scripts/ está fuera de harness/ -> se agrega al path de import (SEG: insert(1))
_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(1, str(_SCRIPTS))

import tdad_select as ts

_REPO_ROOT = Path(__file__).resolve().parents[2]


# ===========================================================================
# Helpers
# ===========================================================================


def _make_repo(tmp_path: Path) -> tuple[Path, Path]:
    """Crea un pseudo-repo harness/ con módulos a, b (importa a), c (importa b)."""
    harness_dir = tmp_path / "harness"
    tests_dir = harness_dir / "tests"
    tests_dir.mkdir(parents=True)
    (harness_dir / "a.py").write_text("def fa(): return 1\n", encoding="utf-8")
    (harness_dir / "b.py").write_text("import a\n", encoding="utf-8")
    (harness_dir / "c.py").write_text("import b\n", encoding="utf-8")
    (tests_dir / "test_a.py").write_text("def test_a(): pass\n", encoding="utf-8")
    (tests_dir / "test_b.py").write_text("def test_b(): pass\n", encoding="utf-8")
    (tests_dir / "test_c.py").write_text("def test_c(): pass\n", encoding="utf-8")
    return harness_dir, tests_dir


# ===========================================================================
# module_name_for
# ===========================================================================


def test_module_name_for_archivo_raiz(tmp_path: Path) -> None:
    """Archivo en la raíz de harness/ -> módulo dotted con el stem."""
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir(parents=True)
    (harness_dir / "common.py").write_text("", encoding="utf-8")

    assert ts.module_name_for(harness_dir / "common.py", harness_dir) == "common"


def test_module_name_for_anidado_y_init(tmp_path: Path) -> None:
    """Módulo anidado y __init__.py de paquete -> nombres dotted correctos."""
    harness_dir = tmp_path / "harness"
    pkg = harness_dir / "orchestrator"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "planner.py").write_text("", encoding="utf-8")
    (harness_dir / "__init__.py").write_text("", encoding="utf-8")

    assert ts.module_name_for(pkg / "planner.py", harness_dir) == "orchestrator.planner"
    assert ts.module_name_for(pkg / "__init__.py", harness_dir) == "orchestrator"
    assert ts.module_name_for(harness_dir / "__init__.py", harness_dir) == "harness"


def test_module_name_for_fuera_de_harness(tmp_path: Path) -> None:
    """Archivo fuera de harness/ -> None (script, docs, etc.)."""
    harness_dir = tmp_path / "harness"
    outside = tmp_path / "other.py"
    outside.write_text("", encoding="utf-8")

    assert ts.module_name_for(outside, harness_dir) is None


# ===========================================================================
# parse_imports
# ===========================================================================


def test_parse_imports_absolutos_y_externos() -> None:
    """Imports absolutos con prefijo harness. y externos -> solo los internos."""
    source = "import numpy\nfrom harness.a import x\nfrom harness.b import y\n"
    known = {"a", "b", "harness"}
    top = {"a", "b"}

    internal = ts.parse_imports(source, "mod", known, top)

    assert internal == {"a", "b"}


def test_parse_imports_relativos() -> None:
    """Imports relativos (nivel 1 y 2) -> resolución contra el módulo actual."""
    source = "from .layers import _X\nfrom ..common import helper\n"
    known = {"pkg.sub.layers", "pkg.common"}
    top = {"pkg"}

    internal = ts.parse_imports(source, "pkg.sub.mod", known, top)

    assert internal == {"pkg.sub.layers", "pkg.common"}


def test_parse_imports_from_dot_import_paquete() -> None:
    """from . import <alias> en un __init__ -> el alias como submódulo."""
    source = "from . import registry\n"
    known = {"pkg.registry", "pkg"}
    top = {"pkg"}

    internal = ts.parse_imports(source, "pkg", known, top)

    assert internal == {"pkg.registry"}


def test_parse_imports_solo_externos_devuelve_vacio() -> None:
    """Imports solo de stdlib/terceros -> conjunto vacío (sin aristas falsas)."""
    source = "import os\nimport numpy as np\nfrom typing import Any\n"
    known = {"a"}
    top = {"a"}

    assert ts.parse_imports(source, "mod", known, top) == set()


def test_parse_imports_harness_sin_modulo_raiz() -> None:
    """import harness sin nodo raíz en el grafo -> sin aristas (None-safe)."""
    assert ts.parse_imports("import harness\n", "mod", {"a"}, {"a"}) == set()


def test_parse_imports_sintaxis_invalida_raise() -> None:
    """Source con SyntaxError -> ValueError con causa (WHAT+WHY+WHERE)."""
    with pytest.raises(ValueError, match="sintaxis inválida"):
        ts.parse_imports("def broken(:", "mod", set(), set())


# ===========================================================================
# Grafo: build / reverse / transitividad
# ===========================================================================


def test_build_dependency_graph_excluye_tests(tmp_path: Path) -> None:
    """El grafo solo contiene módulos de harness/ (excluye tests y __pycache__)."""
    harness_dir, tests_dir = _make_repo(tmp_path)
    (tests_dir / "__pycache__").mkdir(exist_ok=True)

    deps, known, top = ts.build_dependency_graph(harness_dir, tests_dir)

    assert set(deps) == {"a", "b", "c"}
    assert deps["b"] == {"a"}
    assert deps["c"] == {"b"}
    assert known == {"a", "b", "c"}
    assert top == {"a", "b", "c"}


def test_build_dependency_graph_archivo_sintaxis_invalida_resiliente(tmp_path: Path) -> None:
    """Módulo con sintaxis inválida -> warning + nodo vacío (sin crash)."""
    harness_dir = tmp_path / "harness"
    tests_dir = harness_dir / "tests"
    tests_dir.mkdir(parents=True)
    (harness_dir / "ok.py").write_text("import os\n", encoding="utf-8")
    (harness_dir / "broken.py").write_text("def broken(:\n", encoding="utf-8")

    deps, known, _top = ts.build_dependency_graph(harness_dir, tests_dir)

    assert deps["broken"] == set()
    assert deps["ok"] == set()
    assert "broken" in known


def test_reverse_dependencies_invierte_grafo() -> None:
    """Grafo inverso: módulo -> módulos que lo importan."""
    deps = {"a": set(), "b": {"a"}, "c": {"a", "b"}}

    dependents = ts.reverse_dependencies(deps)

    assert dependents["a"] == {"b", "c"}
    assert dependents["b"] == {"c"}
    assert "c" not in dependents


def test_transitive_dependents_bfs() -> None:
    """Transitividad: dependents(a)={b,d} -> BFS alcanza c (vía b)."""
    dependents = {"a": {"b", "d"}, "b": {"c"}}

    result = ts.transitive_dependents("a", dependents)

    assert result == {"b", "c", "d"}


def test_transitive_dependents_sin_dependientes() -> None:
    """Módulo sin dependientes -> conjunto vacío."""
    assert ts.transitive_dependents("solitary", {}) == set()


def test_transitive_dependents_con_ciclo() -> None:
    """Grafo con ciclo (a->b->a) -> BFS termina (a es alcanzable desde sí mismo)."""
    dependents = {"a": {"b"}, "b": {"a", "c"}}

    result = ts.transitive_dependents("a", dependents)

    assert result == {"a", "b", "c"}


def test_top_level_modules_detecta_paquetes(tmp_path: Path) -> None:
    """Paquete (directorio con __init__.py) y módulo -> ambos en top_level."""
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir(parents=True)
    (harness_dir / "mod.py").write_text("", encoding="utf-8")
    (harness_dir / "pkg").mkdir()
    (harness_dir / "pkg" / "__init__.py").write_text("", encoding="utf-8")

    assert ts._top_level_modules(harness_dir) == {"mod", "pkg"}


# ===========================================================================
# direct_test_for
# ===========================================================================


def test_direct_test_for_existente_y_faltante(tmp_path: Path) -> None:
    """Test directo existente -> Path; faltante -> None."""
    harness_dir, tests_dir = _make_repo(tmp_path)

    assert ts.direct_test_for(harness_dir / "a.py", tests_dir) == tests_dir / "test_a.py"
    assert ts.direct_test_for(harness_dir / "c.py", tests_dir) == tests_dir / "test_c.py"
    assert ts.direct_test_for(tmp_path / "ghost.py", tests_dir) is None


def test_direct_test_for_init_usa_nombre_paquete(tmp_path: Path) -> None:
    """__init__.py -> test_<nombre_paquete>.py."""
    harness_dir, tests_dir = _make_repo(tmp_path)
    pkg = harness_dir / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (tests_dir / "test_pkg.py").write_text("def test_pkg(): pass\n", encoding="utf-8")

    assert ts.direct_test_for(pkg / "__init__.py", tests_dir) == tests_dir / "test_pkg.py"


# ===========================================================================
# select_tests
# ===========================================================================


def test_select_tests_directo_y_transitivo(tmp_path: Path) -> None:
    """a.py modificado -> test_a (directo) + test_b/test_c (transitivos)."""
    harness_dir, tests_dir = _make_repo(tmp_path)
    deps, _known, _top = ts.build_dependency_graph(harness_dir, tests_dir)
    dependents = ts.reverse_dependencies(deps)

    selected, warnings = ts.select_tests(
        [harness_dir / "a.py"], dependents, tests_dir, harness_dir
    )

    assert selected == [tests_dir / "test_a.py", tests_dir / "test_b.py", tests_dir / "test_c.py"]
    assert warnings == []


def test_select_tests_deduplicacion_y_orden(tmp_path: Path) -> None:
    """a y b modificados: test_c impactado por ambos -> una sola vez, orden estable."""
    harness_dir, tests_dir = _make_repo(tmp_path)
    dependents = ts.reverse_dependencies(
        ts.build_dependency_graph(harness_dir, tests_dir)[0]
    )

    selected, _ = ts.select_tests(
        [harness_dir / "a.py", harness_dir / "b.py"], dependents, tests_dir, harness_dir
    )

    assert selected == [tests_dir / "test_a.py", tests_dir / "test_b.py", tests_dir / "test_c.py"]
    assert len(selected) == len(set(selected))


def test_select_tests_sin_test_asociado_avisa(tmp_path: Path) -> None:
    """Módulo sin test directo ni transitivo -> aviso, selección vacía (sin error)."""
    harness_dir = tmp_path / "harness"
    tests_dir = harness_dir / "tests"
    tests_dir.mkdir(parents=True)
    (harness_dir / "z.py").write_text("def fz(): return 2\n", encoding="utf-8")

    selected, warnings = ts.select_tests([harness_dir / "z.py"], {}, tests_dir, harness_dir)

    assert selected == []
    assert len(warnings) == 1
    assert "sin test asociado" in warnings[0]


def test_select_tests_archivo_test_modificado_es_seleccionado(tmp_path: Path) -> None:
    """Un test modificado -> él mismo (sin duplicarlo vía grafo)."""
    harness_dir, tests_dir = _make_repo(tmp_path)
    dependents = ts.reverse_dependencies(ts.build_dependency_graph(harness_dir, tests_dir)[0])

    selected, _ = ts.select_tests(
        [tests_dir / "test_a.py"], dependents, tests_dir, harness_dir
    )

    assert selected == [tests_dir / "test_a.py"]


def test_select_tests_no_python_avisa(tmp_path: Path) -> None:
    """Archivo no .py -> aviso 'no aplica', sin selección."""
    harness_dir, tests_dir = _make_repo(tmp_path)
    readme = tmp_path / "README.md"
    readme.write_text("# docs\n", encoding="utf-8")

    selected, warnings = ts.select_tests([readme], {}, tests_dir, harness_dir)

    assert selected == []
    assert "no es código Python" in warnings[0]


# ===========================================================================
# collect_modified_files
# ===========================================================================


def test_collect_modified_files_explicitos(tmp_path: Path) -> None:
    """Rutas explícitas existentes -> rutas absolutas resueltas contra el repo."""
    harness_dir, _ = _make_repo(tmp_path)

    files = ts.collect_modified_files([str(harness_dir / "a.py")], None, tmp_path)

    assert files == [harness_dir / "a.py"]


def test_collect_modified_files_inexistente_raise(tmp_path: Path) -> None:
    """Ruta inexistente -> ValueError con WHAT+WHY+WHERE."""
    with pytest.raises(ValueError, match="archivo inexistente"):
        ts.collect_modified_files(["no_existe.py"], None, tmp_path)


def test_collect_modified_files_sin_entrada_raise(tmp_path: Path) -> None:
    """Sin archivos ni --base -> ValueError accionable."""
    with pytest.raises(ValueError, match="sin entrada"):
        ts.collect_modified_files([], None, tmp_path)


def test_collect_modified_files_con_base_delega_git(monkeypatch: pytest.MonkeyPatch) -> None:
    """Con --base, collect delega en _files_from_git_diff."""
    fake = [Path("/repo/harness/a.py")]
    monkeypatch.setattr(ts, "_files_from_git_diff", lambda base, root: fake)

    files = ts.collect_modified_files([], "origin/main", Path("/repo"))

    assert files == fake


def test_files_from_git_diff_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """git diff exitoso -> paths resueltos contra la raíz del repo."""

    class _FakeResult:
        returncode = 0
        stdout = "harness/a.py\nharness/tests/test_a.py\n"
        stderr = ""

    monkeypatch.setattr(ts.subprocess, "run", lambda *a, **k: _FakeResult())

    files = ts._files_from_git_diff("origin/main", tmp_path)

    assert files == [tmp_path / "harness/a.py", tmp_path / "harness/tests/test_a.py"]


def test_files_from_git_diff_error_raise(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """git falla (ref inexistente) -> ValueError con detalle del stderr."""

    class _FakeResult:
        returncode = 128
        stdout = ""
        stderr = "fatal: not a git repository"

    monkeypatch.setattr(ts.subprocess, "run", lambda *a, **k: _FakeResult())

    with pytest.raises(ValueError, match="git diff contra 'origin/main' falló"):
        ts._files_from_git_diff("origin/main", tmp_path)


# ===========================================================================
# run_pytest
# ===========================================================================


def test_run_pytest_devuelve_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    """run_pytest propaga el exit code de pytest y recibe los paths."""

    class _FakeResult:
        returncode = 5

    captured: dict[str, list[str]] = {}

    def _fake_run(cmd: list[str], **_: object) -> _FakeResult:
        captured["cmd"] = cmd
        return _FakeResult()

    monkeypatch.setattr(ts.subprocess, "run", _fake_run)

    code = ts.run_pytest([Path("harness/tests/test_a.py")], Path("."))

    assert code == 5
    assert captured["cmd"][:3] == [sys.executable, "-m", "pytest"]
    assert captured["cmd"][3] == str(Path("harness/tests/test_a.py"))


def test_run_pytest_error_oserror(monkeypatch: pytest.MonkeyPatch) -> None:
    """OSError al lanzar pytest -> RuntimeError (WHAT+WHY+WHERE)."""

    def _boom(*_: object, **__: object) -> None:
        raise OSError("pytest no está instalado")

    monkeypatch.setattr(ts.subprocess, "run", _boom)

    with pytest.raises(RuntimeError, match="no se pudo ejecutar pytest"):
        ts.run_pytest([Path("test_x.py")], Path("."))


# ===========================================================================
# CLI (main) — dry-run / run / exit-code / errores
# ===========================================================================


def _patch_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    modified: list[Path],
    selected: list[Path],
    warnings: list[str] | None = None,
) -> None:
    """Reemplaza la pipeline de main por valores deterministas (hermético)."""
    monkeypatch.setattr(ts, "collect_modified_files", lambda *a, **k: modified)
    monkeypatch.setattr(ts, "build_dependency_graph", lambda *a, **k: ({}, {"a"}, {"a"}))
    monkeypatch.setattr(ts, "reverse_dependencies", lambda deps: {})
    monkeypatch.setattr(ts, "select_tests", lambda *a, **k: (selected, warnings or []))


def test_cli_dry_run_lista_tests(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """main con --dry-run imprime los tests seleccionados y sale con 0."""
    test_path = _REPO_ROOT / "harness" / "tests" / "test_a.py"
    _patch_pipeline(monkeypatch, modified=[_REPO_ROOT / "harness" / "a.py"], selected=[test_path])

    code = ts.main(["--dry-run", "harness/a.py"])

    assert code == ts._EXIT_OK
    assert "test_a.py" in capsys.readouterr().out


def test_cli_exit_code_con_sin_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """--exit-code con cambios sin tests -> exit 1 (conveniente para CI)."""
    _patch_pipeline(monkeypatch, modified=[_REPO_ROOT / "harness" / "z.py"], selected=[], warnings=["sin test"])

    assert ts.main(["--exit-code", "harness/z.py"]) == ts._EXIT_NO_TESTS


def test_cli_run_ejecuta_pytest(monkeypatch: pytest.MonkeyPatch) -> None:
    """--run ejecuta pytest con los tests seleccionados y devuelve su exit code."""
    test_path = _REPO_ROOT / "harness" / "tests" / "test_a.py"
    _patch_pipeline(monkeypatch, modified=[_REPO_ROOT / "harness" / "a.py"], selected=[test_path])
    received: list[list[Path]] = []
    monkeypatch.setattr(ts, "run_pytest", lambda paths, cwd: (received.append(paths) or 0))

    code = ts.main(["--run", "harness/a.py"])

    assert code == 0
    assert received[0] == [test_path]


def test_cli_run_error_pytest(monkeypatch: pytest.MonkeyPatch) -> None:
    """--run con RuntimeError interno -> exit 2 (WHAT+WHY+WHERE)."""
    test_path = _REPO_ROOT / "harness" / "tests" / "test_a.py"
    _patch_pipeline(monkeypatch, modified=[_REPO_ROOT / "harness" / "a.py"], selected=[test_path])

    def _boom(paths: list[Path], cwd: Path) -> int:
        raise RuntimeError("boom")

    monkeypatch.setattr(ts, "run_pytest", _boom)

    assert ts.main(["--run", "harness/a.py"]) == ts._EXIT_ERROR


def test_cli_ruta_inexistente_retorna_error() -> None:
    """Ruta inexistente en CLI -> exit 2 con error legible (pipeline real)."""
    assert ts.main(["zz_no_existe.py"]) == ts._EXIT_ERROR


def test_cli_sin_archivos_modificados(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sin archivos modificados (--base, diff vacío) -> exit 0 informativo."""
    _patch_pipeline(monkeypatch, modified=[], selected=[])

    assert ts.main(["--base", "origin/main"]) == ts._EXIT_OK
