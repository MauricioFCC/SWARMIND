"""Tests TDD del gate de evidencia de fix (SpecBench / anti-pintar-verde).

Verifican que un fix solo pasa con spec + repro que fallaba antes y pasa
despues + cero debilitamientos de tests. Cada test puede fallar si el gate
pierde rigor (nada decorativo).
"""

from __future__ import annotations

from harness.validation.fix_evidence import (
    FixEvidenceReport,
    check_test_weakening,
    verify_fix_evidence,
)

SPEC_OK = "specs/demo.md"
REPRO = "harness/tests/test_demo.py::test_demo_bug"


def _write_spec(tmp_path, content: str = "# spec\ncriterio: x\n") -> str:
    """Escribe una spec valida en tmp y devuelve su ruta."""
    path = tmp_path / "demo.md"
    path.write_text(content, encoding="utf-8")
    return str(path)


GOOD_OLD = "def test_demo_bug():\n    assert compute(2) == 4\n"
GOOD_NEW = GOOD_OLD  # el fix no toca el test


def test_valid_fix_passes(tmp_path) -> None:
    """Fix valido (spec + repro fail->pass + tests intactos) pasa."""
    spec = _write_spec(tmp_path)
    report = verify_fix_evidence(
        spec_path=spec, repro_test=REPRO, failed_before=True,
        passed_after=True, old_test_text=GOOD_OLD, new_test_text=GOOD_NEW,
    )
    assert isinstance(report, FixEvidenceReport)
    assert report.passed is True
    assert report.reasons == ()


def test_missing_spec_fails(tmp_path) -> None:
    """Sin spec (o vacia) el gate falla."""
    report = verify_fix_evidence(
        spec_path=str(tmp_path / "no-existe.md"), repro_test=REPRO,
        failed_before=True, passed_after=True,
        old_test_text=GOOD_OLD, new_test_text=GOOD_NEW,
    )
    assert report.passed is False
    assert any("sin-spec" in r for r in report.reasons)

    spec = _write_spec(tmp_path, content="   \n")
    report = verify_fix_evidence(
        spec_path=spec, repro_test=REPRO, failed_before=True,
        passed_after=True, old_test_text=GOOD_OLD, new_test_text=GOOD_NEW,
    )
    assert report.passed is False
    assert any("sin-spec" in r for r in report.reasons)


def test_repro_must_fail_before(tmp_path) -> None:
    """Si el repro no fallaba antes, no hay evidencia de que el fix arregle."""
    spec = _write_spec(tmp_path)
    report = verify_fix_evidence(
        spec_path=spec, repro_test=REPRO, failed_before=False,
        passed_after=True, old_test_text=GOOD_OLD, new_test_text=GOOD_NEW,
    )
    assert report.passed is False
    assert any("sin-fallo-previo" in r for r in report.reasons)


def test_repro_must_pass_after(tmp_path) -> None:
    """Si el repro sigue fallando, el fix no sirve."""
    spec = _write_spec(tmp_path)
    report = verify_fix_evidence(
        spec_path=spec, repro_test=REPRO, failed_before=True,
        passed_after=False, old_test_text=GOOD_OLD, new_test_text=GOOD_NEW,
    )
    assert report.passed is False
    assert any("sigue-fallando" in r for r in report.reasons)


def test_removed_assert_is_weakening() -> None:
    """Eliminar un assert para pasar es pintar verde (SpecBench)."""
    old = "def test_x():\n    assert a == 1\n    assert b == 2\n"
    new = "def test_x():\n    assert a == 1\n"
    findings = check_test_weakening(old, new)
    assert findings != []
    assert any("eliminado" in f for f in findings)


def test_relaxed_comparison_is_weakening() -> None:
    """Relajar `==` a `in` es debilitamiento."""
    old = "def test_x():\n    assert status == 'ok'\n"
    new = "def test_x():\n    assert status in ('ok', 'casi')\n"
    findings = check_test_weakening(old, new)
    assert findings != []
    assert any("relaj" in f for f in findings)


def test_changed_literal_is_weakening() -> None:
    """Cambiar el literal esperado para pasar es pintar verde."""
    old = "def test_x():\n    assert total == 100\n"
    new = "def test_x():\n    assert total == 99\n"
    findings = check_test_weakening(old, new)
    assert findings != []


def test_adding_asserts_is_not_weakening() -> None:
    """Anadir aserciones nuevas endurece el test: permitido."""
    old = "def test_x():\n    assert a == 1\n"
    new = "def test_x():\n    assert a == 1\n    assert b == 2\n"
    assert check_test_weakening(old, new) == []


def test_weakening_fails_gate(tmp_path) -> None:
    """Un fix que debilita el test no pasa aunque todo lo demas este bien."""
    spec = _write_spec(tmp_path)
    report = verify_fix_evidence(
        spec_path=spec, repro_test=REPRO, failed_before=True,
        passed_after=True,
        old_test_text="def t():\n    assert x == 1\n",
        new_test_text="def t():\n    assert x in (1, 2, 3)\n",
    )
    assert report.passed is False
    assert any("debilitamiento" in r for r in report.reasons)


def test_reasons_are_actionable(tmp_path) -> None:
    """Las razones explican WHAT+WHERE para que el builder corrija."""
    report = verify_fix_evidence(
        spec_path="no-existe.md", repro_test=REPRO, failed_before=False,
        passed_after=False, old_test_text="", new_test_text="",
    )
    assert report.passed is False
    assert len(report.reasons) >= 2
    assert all("WHERE" in r for r in report.reasons)
