"""Tests para timeout dual_verify + reasoning pillar + math micro-gate (mesa).

Mesa: lo primero que rompe en prod es brute sin timeout (hang/OOM);
sin reasoning_trace el R1 es inauditable; sin gate math no se prueba
reasoning real (MATH-500 fresco, no GSM8K contaminado).
"""

import pytest

from harness.validation.cp_spec_gate import check_reasoning
from harness.validation.dual_verify import dual_verify
from harness.validation.math_gate import (
    MATH_CASES,
    check_math,
)


def _slow_brute(x):
    """Brute que cuelga (loop)."""
    import time

    time.sleep(30)
    return x


def test_brute_timeout_is_mismatch() -> None:
    """Brute que excede timeout cuenta como mismatch (no cuelga)."""
    report = dual_verify(sorted, _slow_brute, [[3, 1]], timeout_s=0.5)
    assert report.passed is False
    assert len(report.mismatches) == 1
    assert "timeout" in str(report.mismatches[0][2]).lower()


def test_fast_timeout_is_mismatch() -> None:
    """Fast que excede timeout cuenta como mismatch."""
    report = dual_verify(_slow_brute, sorted, [[3, 1]], timeout_s=0.5)
    assert report.passed is False


def test_no_timeout_backward_compat() -> None:
    """Sin timeout_s el comportamiento no cambia (compat)."""
    report = dual_verify(sorted, sorted, [[2, 1]])
    assert report.passed is True


def test_reasoning_trace_valid() -> None:
    """Trace con verdict + pasos numerados pasa."""
    trace = "verdict: usar indice\n1. medir costo\n2. comparar\n3. decidir"
    report = check_reasoning(trace)
    assert report.passed is True


def test_reasoning_trace_no_verdict_fails() -> None:
    """Sin verdict falla (anti-hedging R1)."""
    report = check_reasoning("1. pensar\n2. dudar\n3. quizas")
    assert report.passed is False
    assert "verdict" in report.missing


def test_reasoning_trace_no_steps_fails() -> None:
    """Sin pasos numerados falla."""
    report = check_reasoning("verdict: ir")
    assert report.passed is False


def test_reasoning_empty_raises() -> None:
    """Vacio falla accionable."""
    from harness.validation.cp_spec_gate import check_reasoning as cr

    with pytest.raises(ValueError, match="WHAT"):
        cr("   ")


def test_math_gate_all_pass() -> None:
    """Casos exactos correctos pasan."""
    report = check_math({"2+2*2": "6", "7*8": "56"})
    assert report.passed is True
    assert report.score == 1.0


def test_math_gate_detects_error() -> None:
    """Respuesta erronea se detecta con indice."""
    report = check_math({"2+2*2": "8"})
    assert report.passed is False
    assert len(report.wrong) == 1


def test_math_cases_fresh_deterministic() -> None:
    """El micro-set es determinista y no vacio (20 casos exactos)."""
    assert len(MATH_CASES) >= 15
    assert all("=" not in str(v) for v in MATH_CASES.values())
