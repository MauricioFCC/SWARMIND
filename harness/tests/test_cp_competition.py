"""Tests para cp_spec_gate + dual_verify — competición aplicada (ADR-0080).

CP moderno (arXiv 2506.22954 + Wonda ICML 2026): el 44% de fallos LLM es
design (28.6%) + boundary (15.5%) — prevenible con checklist ANTES de
codear (edges + invariants + BigO + constraints I/O). Y dual verification:
solución vs brute-force de referencia confirma corrección sin OJ externo.
"""

import pytest

from harness.validation.cp_spec_gate import (
    REQUIRED_CHECKLIST,
    check_spec,
)
from harness.validation.dual_verify import (
    DualReport,
    dual_verify,
)


def _full_spec() -> dict:
    """Spec completa con los 4 pilares del checklist."""
    return {
        "edges": ["lista vacia", "n=1", "duplicados", "overflow int"],
        "invariants": ["suma parcial monotona", "indices dentro de rango"],
        "complexity": "O(n log n) tiempo, O(n) espacio",
        "io_constraints": "n <= 10^5, enteros 32-bit",
    }


def test_full_spec_passes() -> None:
    """Spec con los 4 pilares pasa el gate."""
    report = check_spec(_full_spec())
    assert report.passed is True
    assert report.missing == ()


def test_missing_pillars_listed() -> None:
    """Cada pilar ausente/vacio se reporta por nombre."""
    report = check_spec({"edges": ["vacio"]})
    assert report.passed is False
    assert "invariants" in report.missing
    assert "complexity" in report.missing
    assert "io_constraints" in report.missing


def test_empty_strings_do_not_count() -> None:
    """Strings vacios o solo-espacios no cuentan como pilar."""
    spec = _full_spec()
    spec["complexity"] = "   "
    report = check_spec(spec)
    assert report.passed is False
    assert "complexity" in report.missing


def test_checklist_has_four_pillars() -> None:
    """El checklist son exactamente los 4 pilares (documentado)."""
    assert REQUIRED_CHECKLIST == (
        "edges", "invariants", "complexity", "io_constraints",
    )


def test_non_dict_raises() -> None:
    """Spec no-dict falla accionable."""
    with pytest.raises(TypeError, match="WHAT"):
        check_spec(["edges"])  # type: ignore[arg-type]


def test_dual_verify_all_match() -> None:
    """Fast vs brute identicos en todos los casos -> pass."""
    fast = lambda xs: sorted(xs)
    brute = lambda xs: sorted(xs)
    cases = [[], [3, 1, 2], [5, 5, 1]]
    report = dual_verify(fast, brute, cases)
    assert isinstance(report, DualReport)
    assert report.passed is True
    assert report.mismatches == ()
    assert report.cases == 3


def test_dual_verify_catches_bug() -> None:
    """Fast con bug en un caso -> mismatch con indice y valores."""
    fast = lambda xs: xs  # bug: no ordena
    brute = lambda xs: sorted(xs)
    report = dual_verify(fast, brute, [[], [2, 1]])
    assert report.passed is False
    assert len(report.mismatches) == 1
    idx, got, expected = report.mismatches[0]
    assert idx == 1 and got == [2, 1] and expected == [1, 2]


def test_dual_verify_exception_counts_as_mismatch() -> None:
    """Excepcion del fast cuenta como mismatch (no crashea)."""
    def boom(xs):
        raise ValueError("x")

    report = dual_verify(boom, sorted, [[3, 1]])
    assert report.passed is False
    assert len(report.mismatches) == 1


def test_dual_verify_empty_cases() -> None:
    """Sin casos retorna pass vacuo con 0 casos (documentado)."""
    report = dual_verify(sorted, sorted, [])
    assert report.passed is True
    assert report.cases == 0
