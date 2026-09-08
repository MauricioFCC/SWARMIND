"""Tests para batch_vote — votacion k-en-1 con parametro n (ADR-0073).

Frontera (arXiv 2604.13717): usar el parametro n de la API para k
completos cobra el INPUT una sola vez (vs k llamadas = input kx) y
permite criteria+ensembling (+11.9pp). Verifica: 1 llamada para k votos,
costo de input cobrado 1x, mayoria con quorum, fallback a k llamadas
secuenciales cuando el proveedor no soporta n>1, y fail-fast.
"""

import pytest

from harness.orchestrator.batch_vote import (
    batch_vote,
    estimate_savings,
)


def _complete_fn_n(answers: list[str]):
    """Fabrica de complete_fn que soporta n (retorna n respuestas en 1 llamada)."""
    calls: list[int] = []

    def _fn(prompt: str, n: int) -> list[str]:
        calls.append(n)
        return answers[:n]

    _fn.calls = calls  # type: ignore[attr-defined]
    return _fn


def _complete_fn_single(answers: list[str]):
    """Fabrica de complete_fn sin soporte n (1 respuesta por llamada)."""
    calls: list[int] = []

    def _fn(prompt: str, n: int) -> list[str]:
        calls.append(n)
        return [answers[min(len(calls) - 1, len(answers) - 1)]]

    _fn.calls = calls  # type: ignore[attr-defined]
    return _fn


def test_one_call_for_k_votes() -> None:
    """k votos salen de UNA llamada con n=k (input cobrado 1x)."""
    fn = _complete_fn_n(["a", "a", "b"])
    result = batch_vote("pregunta", fn, k=3, input_tokens=100, output_tokens=50)
    assert fn.calls == [3]
    assert result.votes == ("a", "a", "b")
    assert result.majority == "a"
    assert result.input_calls == 1


def test_majority_and_quorum() -> None:
    """Mayoria simple respetando quorum; empate retorna None."""
    fn = _complete_fn_n(["x", "y"])
    tied = batch_vote("q", fn, k=2, input_tokens=10, output_tokens=10)
    assert tied.majority is None
    assert tied.quorum_met is False


def test_cost_input_charged_once() -> None:
    """El costo cobrado usa input una vez + output por cada voto."""
    fn = _complete_fn_n(["a", "a", "b"])
    result = batch_vote("q", fn, k=3, input_tokens=100, output_tokens=10)
    # input 1x + output 3x
    assert result.effective_input_tokens == 100
    assert result.effective_output_tokens == 30


def test_fallback_to_single_calls_when_n_unsupported() -> None:
    """Si n>1 retorna 1 sola respuesta, hace k llamadas secuenciales."""
    fn = _complete_fn_single(["a", "a", "b", "a"])
    result = batch_vote("q", fn, k=3, input_tokens=100, output_tokens=10)
    assert len(fn.calls) == 3
    assert result.votes == ("a", "a", "b")
    assert result.majority == "a"
    assert result.input_calls == 3


def test_estimate_savings_reports_ratio() -> None:
    """estimate_savings calcula el ahorro de input (1x vs kx)."""
    assert estimate_savings(k=5) == pytest.approx(0.80)
    assert estimate_savings(k=1) == pytest.approx(0.0)


def test_invalid_k_raises() -> None:
    """k < 1 falla con ValueError accionable."""
    fn = _complete_fn_n(["a"])
    with pytest.raises(ValueError, match="WHAT"):
        batch_vote("q", fn, k=0, input_tokens=1, output_tokens=1)


def test_empty_prompt_raises() -> None:
    """Prompt vacio falla con ValueError accionable."""
    fn = _complete_fn_n(["a"])
    with pytest.raises(ValueError, match="WHAT"):
        batch_vote("   ", fn, k=3, input_tokens=1, output_tokens=1)


def test_result_is_frozen() -> None:
    """BatchVoteResult es inmutable."""
    fn = _complete_fn_n(["a"])
    result = batch_vote("q", fn, k=1, input_tokens=1, output_tokens=1)
    with pytest.raises(AttributeError):
        result.majority = "x"  # type: ignore[misc]
