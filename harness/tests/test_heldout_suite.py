"""Tests TDD de la held-out suite (SpecBench: verificar contra lo no visto).

El gate corre nodos pytest reservados y solo acepta si todo lo oculto pasa.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.validation.heldout_suite import (
    HeldoutCase,
    HeldoutSuite,
    evaluate_fix,
    load_manifest,
)

PASS_FILE = """\
def test_alpha_ok():
    assert 1 + 1 == 2


def test_beta_ok():
    assert "x".upper() == "X"
"""

FAIL_FILE = """\
def test_gamma_broken():
    assert 1 + 1 == 3
"""


def _write(path: Path, name: str, content: str) -> str:
    """Escribe un archivo de tests en el repo fixture y devuelve su nombre."""
    (path / name).write_text(content, encoding="utf-8")
    return name


def test_passing_case_verdict_passed(tmp_path) -> None:
    """Caso con nodos verdes -> veredicto passed sin fallos listados."""
    name = _write(tmp_path, "test_ok.py", PASS_FILE)
    suite = HeldoutSuite(
        [HeldoutCase("demo-ok", (f"{name}::test_alpha_ok",), "caso sano")],
        repo_root=tmp_path,
    )
    (verdict,) = suite.run()
    assert verdict.passed is True
    assert verdict.failed_nodes == ()


def test_failing_case_lists_nodes(tmp_path) -> None:
    """Caso con un nodo rojo -> failed con el nodo listado."""
    name = _write(tmp_path, "test_bad.py", FAIL_FILE)
    suite = HeldoutSuite(
        [HeldoutCase("demo-bad", (f"{name}::test_gamma_broken",), "caso roto")],
        repo_root=tmp_path,
    )
    (verdict,) = suite.run()
    assert verdict.passed is False
    assert verdict.failed_nodes == (f"{name}::test_gamma_broken",)


def test_evaluate_fix_accept_only_when_all_hidden_pass() -> None:
    """ACCEPT solo con visible ok + todo lo oculto verde."""
    from harness.validation.heldout_suite import HeldoutVerdict

    ok_v = HeldoutVerdict("a", True, ())
    bad_v = HeldoutVerdict("b", False, ("test_x.py::test_y",))
    assert evaluate_fix(True, [ok_v]) == "ACCEPT"
    assert evaluate_fix(True, [ok_v, bad_v]) == "OVERFIT"
    assert evaluate_fix(False, [ok_v]) == "OVERFIT"


def test_evaluate_fix_incomplete_on_error(tmp_path) -> None:
    """Caso inexistente -> INCOMPLETE (no se pudo ejecutar)."""
    suite = HeldoutSuite(
        [HeldoutCase("demo-missing", ("test_nope.py::test_x",), "ausente")],
        repo_root=tmp_path,
    )
    (verdict,) = suite.run()
    assert verdict.passed is False
    assert evaluate_fix(True, [verdict]) == "INCOMPLETE"


def test_load_manifest_roundtrip(tmp_path) -> None:
    """El manifiesto se carga con id, nodos y descripcion."""
    manifest = tmp_path / "heldout_manifest.json"
    manifest.write_text(
        '[{"id": "m1", "node_ids": ["test_a.py::test_b"], '
        '"description": "demo"}]',
        encoding="utf-8",
    )
    (case,) = load_manifest(manifest)
    assert case.id == "m1"
    assert case.node_ids == ("test_a.py::test_b",)


def test_evaluate_fix_incomplete_without_cases() -> None:
    """Sin casos ocultos no hay oraculo: INCOMPLETE (evita el ACCEPT vacuo)."""
    assert evaluate_fix(True, []) == "INCOMPLETE"


def test_failed_nodes_exact_match_not_prefix(tmp_path) -> None:
    """Un nodo prefijo de otro NO se atribuye como fallido (igualdad exacta)."""
    (tmp_path / "test_pair.py").write_text(
        "def test_x():\n    assert True\n\n\n"
        "def test_x_extra():\n    assert False\n",
        encoding="utf-8",
    )
    suite = HeldoutSuite(
        [
            HeldoutCase(
                "prefix",
                ("test_pair.py::test_x", "test_pair.py::test_x_extra"),
                "colision de prefijos",
            )
        ],
        repo_root=tmp_path,
    )
    (verdict,) = suite.run()
    assert verdict.failed_nodes == ("test_pair.py::test_x_extra",)


def test_load_manifest_corrupt_raises_value_error(tmp_path) -> None:
    """Manifiesto corrupto -> ValueError accionable (no JSONDecodeError crudo)."""
    bad = tmp_path / "bad.json"
    bad.write_text("{no-json", encoding="utf-8")
    with pytest.raises(ValueError, match="manifiesto held-out invalido"):
        load_manifest(bad)


def test_manifest_not_imported_by_source() -> None:
    """Aislamiento: ningun .py de harness/ (salvo tests y el gate) toca el manifiesto."""
    repo_root = Path(__file__).resolve().parents[2]
    offenders: list[str] = []
    for path in (repo_root / "harness").rglob("*.py"):
        if "tests" in path.parts or path.name == "heldout_suite.py":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "heldout_manifest" in text:
            offenders.append(str(path.relative_to(repo_root)))
    assert offenders == []
