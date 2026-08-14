"""
Tests para el mapa de dependencias src<->tests (TDAD, arXiv 2603.17973).

El TestDependencyMap analiza via AST que tests importan cada archivo de src
para inyectar contexto al agente ("si cambias X, corre estos tests").

Cubre: build del mapa, tests_for, imports_from (import / from-import / dotted),
render markdown, coverage_stats, exclusion de directorios de maquinaria,
manejo de AST roto sin abortar, y summary() de DependencyEntry.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from harness.orchestrator.workflows.test_dependency_map import (
    DependencyEntry,
    TestDependencyMap,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def project_tree(tmp_path: Path) -> Path:
    """Estructura de proyecto de prueba: src con 2 modulos y 2 tests.

    - src/agent_bus.py  -> cubierto por tests/test_agent_bus.py
    - src/helper.py     -> sin ningun test que lo importe
    - tests/test_util.py -> test sin dependencia de src
    """
    src = tmp_path / "src"
    tests = tmp_path / "tests"
    src.mkdir()
    tests.mkdir()

    (src / "agent_bus.py").write_text(
        "class AgentBus:\n"
        "    def post(self) -> str:\n"
        "        return 'ok'\n",
        encoding="utf-8",
    )
    (src / "helper.py").write_text(
        "def helper() -> int:\n"
        "    return 1\n",
        encoding="utf-8",
    )
    (tests / "test_agent_bus.py").write_text(
        "from agent_bus import AgentBus\n"
        "\n"
        "def test_post() -> None:\n"
        "    assert AgentBus().post() == 'ok'\n",
        encoding="utf-8",
    )
    (tests / "test_util.py").write_text(
        "def test_util() -> None:\n"
        "    assert True\n",
        encoding="utf-8",
    )
    return tmp_path


def _find_entry(
    entries: tuple[DependencyEntry, ...], marker: str
) -> DependencyEntry:
    """Busca una entrada del mapa cuyo src_path contenga marker."""
    for entry in entries:
        if marker in entry.src_path:
            return entry
    raise AssertionError(f"No se encontro entrada con {marker!r} en {entries}")


# ---------------------------------------------------------------------------
# build(): deteccion de cobertura
# ---------------------------------------------------------------------------


def test_build_detects_test_for_src(project_tree: Path) -> None:
    """build() crea una entrada para agent_bus.py cubierta por test_agent_bus.py."""
    mapa = TestDependencyMap(project_tree)

    entries = mapa.build()
    entry = _find_entry(entries, "agent_bus.py")

    assert len(entry.test_paths) == 1
    assert "test_agent_bus.py" in entry.test_paths[0]
    assert "test_util.py" not in entry.test_paths[0]


def test_build_records_imported_names(project_tree: Path) -> None:
    """build() registra los simbolos que el test importa desde el src."""
    mapa = TestDependencyMap(project_tree)

    entry = _find_entry(mapa.build(), "agent_bus.py")

    assert "AgentBus" in entry.imported_names


def test_module_without_tests_is_omitted(project_tree: Path) -> None:
    """Un src sin ningun test que lo importe no genera entrada en build()."""
    mapa = TestDependencyMap(project_tree)

    entries = mapa.build()

    assert all("helper.py" not in entry.src_path for entry in entries)


def test_build_accepts_str_root(project_tree: Path) -> None:
    """__init__ acepta root como str o Path."""
    mapa = TestDependencyMap(str(project_tree))

    entries = mapa.build()

    assert len(entries) >= 1
    assert "agent_bus.py" in entries[0].src_path


# ---------------------------------------------------------------------------
# tests_for(): consulta de cobertura para inyectar al agente
# ---------------------------------------------------------------------------


def test_tests_for_returns_covering_tests(project_tree: Path) -> None:
    """tests_for('.../agent_bus.py') devuelve los tests que lo cubren."""
    mapa = TestDependencyMap(project_tree)

    result = mapa.tests_for(str(project_tree / "src" / "agent_bus.py"))

    assert len(result) == 1
    assert "test_agent_bus.py" in result[0]


def test_tests_for_uncovered_returns_empty(project_tree: Path) -> None:
    """tests_for() de un src sin cobertura devuelve tupla vacia."""
    mapa = TestDependencyMap(project_tree)

    result = mapa.tests_for(str(project_tree / "src" / "helper.py"))

    assert result == ()


def test_tests_for_missing_file_raises_what_why_where(project_tree: Path) -> None:
    """tests_for() con archivo inexistente lanza error WHAT+WHY+WHERE."""
    mapa = TestDependencyMap(project_tree)

    with pytest.raises(FileNotFoundError) as excinfo:
        mapa.tests_for(str(project_tree / "src" / "missing.py"))

    message = str(excinfo.value)
    assert "WHAT" in message
    assert "WHY" in message
    assert "WHERE" in message


# ---------------------------------------------------------------------------
# _imports_from(): extraccion de imports via AST
# ---------------------------------------------------------------------------


def test_imports_from_plain_import(tmp_path: Path) -> None:
    """_imports_from detecta 'import agent_bus'."""
    sample = tmp_path / "sample.py"
    sample.write_text("import agent_bus\n", encoding="utf-8")
    mapa = TestDependencyMap(tmp_path)

    assert mapa._imports_from(sample, "agent_bus") == {"agent_bus"}


def test_imports_from_import_alias(tmp_path: Path) -> None:
    """_imports_from usa el asname cuando existe ('import agent_bus as ab')."""
    sample = tmp_path / "sample.py"
    sample.write_text("import agent_bus as ab\n", encoding="utf-8")
    mapa = TestDependencyMap(tmp_path)

    assert mapa._imports_from(sample, "agent_bus") == {"ab"}


def test_imports_from_from_import(tmp_path: Path) -> None:
    """_imports_from detecta 'from agent_bus import X'."""
    sample = tmp_path / "sample.py"
    sample.write_text("from agent_bus import AgentBus\n", encoding="utf-8")
    mapa = TestDependencyMap(tmp_path)

    assert mapa._imports_from(sample, "agent_bus") == {"AgentBus"}


def test_imports_from_dotted_import(tmp_path: Path) -> None:
    """_imports_from detecta 'import harness.orchestrator.agent_bus'."""
    sample = tmp_path / "sample.py"
    sample.write_text("import harness.orchestrator.agent_bus\n", encoding="utf-8")
    mapa = TestDependencyMap(tmp_path)

    names = mapa._imports_from(sample, "agent_bus")

    assert "harness.orchestrator.agent_bus" in names


def test_imports_from_from_dotted_import(tmp_path: Path) -> None:
    """_imports_from detecta 'from harness.orchestrator.agent_bus import X'."""
    sample = tmp_path / "sample.py"
    sample.write_text(
        "from harness.orchestrator.agent_bus import AgentBus\n", encoding="utf-8"
    )
    mapa = TestDependencyMap(tmp_path)

    assert mapa._imports_from(sample, "agent_bus") == {"AgentBus"}


# ---------------------------------------------------------------------------
# render(): skill estatico markdown para el agente
# ---------------------------------------------------------------------------


def test_render_contains_table_and_corre(project_tree: Path) -> None:
    """render() produce la tabla markdown con la forma 'corre: test_a.py'."""
    mapa = TestDependencyMap(project_tree)

    rendered = mapa.render()

    assert "| src | tests |" in rendered
    assert "corre:" in rendered
    assert "test_agent_bus.py" in rendered


# ---------------------------------------------------------------------------
# coverage_stats(): metricas agregadas
# ---------------------------------------------------------------------------


def test_coverage_stats_counts(project_tree: Path) -> None:
    """coverage_stats() reporta total_src, with/without tests y total_tests."""
    mapa = TestDependencyMap(project_tree)

    stats = mapa.coverage_stats()

    assert stats["total_src"] == 2
    assert stats["src_with_tests"] == 1
    assert stats["src_without_tests"] == 1
    assert stats["total_tests"] == 2


# ---------------------------------------------------------------------------
# Exclusion de directorios de maquinaria
# ---------------------------------------------------------------------------


def test_iter_python_files_excludes_junk_dirs(project_tree: Path) -> None:
    """_iter_python_files no recorre __pycache__, venv ni node_modules."""
    cached = project_tree / "src" / "__pycache__" / "cached.py"
    cached.parent.mkdir(parents=True)
    cached.write_text("cached = 1\n", encoding="utf-8")
    site = project_tree / ".venv" / "lib" / "site.py"
    site.parent.mkdir(parents=True)
    site.write_text("installed = 2\n", encoding="utf-8")
    node = project_tree / "node_modules" / "pkg" / "index.py"
    node.parent.mkdir(parents=True)
    node.write_text("npm = 3\n", encoding="utf-8")
    mapa = TestDependencyMap(project_tree)

    files = mapa._iter_python_files(project_tree)

    assert len(files) == 2  # agent_bus.py + helper.py
    assert all("__pycache__" not in str(path) for path in files)
    assert all(".venv" not in str(path) for path in files)
    assert all("node_modules" not in str(path) for path in files)


def test_find_test_files_both_patterns(project_tree: Path) -> None:
    """_find_test_files localiza test_*.py y *_test.py."""
    (project_tree / "tests" / "suite_util_test.py").write_text(
        "def test_suite() -> None:\n    pass\n", encoding="utf-8"
    )
    mapa = TestDependencyMap(project_tree)

    names = {path.name for path in mapa._find_test_files()}

    assert "test_agent_bus.py" in names
    assert "suite_util_test.py" in names


# ---------------------------------------------------------------------------
# Tolerancia a errores
# ---------------------------------------------------------------------------


def test_broken_ast_does_not_abort_analysis(
    project_tree: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Un test con AST invalido genera warning pero build() no aborta."""
    (project_tree / "tests" / "test_broken.py").write_text(
        "def roto(:\n", encoding="utf-8"
    )
    mapa = TestDependencyMap(project_tree)

    with caplog.at_level(
        logging.WARNING,
        logger="harness.orchestrator.workflows.test_dependency_map",
    ):
        entries = mapa.build()

    entry = _find_entry(entries, "agent_bus.py")
    assert "test_broken.py" not in entry.test_paths[0]
    assert any("AST" in record.getMessage() for record in caplog.records)


# ---------------------------------------------------------------------------
# DependencyEntry: summary legible
# ---------------------------------------------------------------------------


def test_dependency_entry_summary_is_readable() -> None:
    """summary() produce un resumen legible con src, tests y simbolos."""
    entry = DependencyEntry(
        src_path="src/agent_bus.py",
        test_paths=("tests/test_agent_bus.py",),
        imported_names=("AgentBus",),
    )

    summary = entry.summary()

    assert "agent_bus.py" in summary
    assert "test_agent_bus.py" in summary
    assert "AgentBus" in summary
