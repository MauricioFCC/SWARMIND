"""Tests de conclusion_gate — checklist adversarial de 10 ataques (ADR-0054)."""
from __future__ import annotations

import pytest

from harness.validation.conclusion_gate import (
    ADVERSARIAL_CHECKS,
    CHECK_COUNTEREXAMPLE,
    CHECK_GOODHART,
    ConclusionGate,
    Verdict,
)


def _all_pass() -> dict[str, bool]:
    """Resultados donde la conclusion sobrevive a todos los ataques."""
    return dict.fromkeys(ADVERSARIAL_CHECKS, True)


class TestChecklist:
    """El checklist canonico del Atlas."""

    def test_exactly_ten_checks(self) -> None:
        assert len(ADVERSARIAL_CHECKS) == 10

    def test_no_duplicates(self) -> None:
        assert len(set(ADVERSARIAL_CHECKS)) == 10


class TestSubmit:
    """ConclusionGate.submit: sin omisiones silenciosas."""

    def test_accept_when_survives_all_attacks(self) -> None:
        result = ConclusionGate().submit("C", _all_pass())
        assert result.accepted
        assert result.verdict is Verdict.ACCEPT
        assert result.confidence_factor == 1.0

    def test_revise_when_fails_one_attack(self) -> None:
        results = _all_pass()
        results[CHECK_COUNTEREXAMPLE] = False
        result = ConclusionGate().submit("C", results)
        assert not result.accepted
        assert result.verdict is Verdict.REVISE_CONFIDENCE
        assert result.failed_checks == (CHECK_COUNTEREXAMPLE,)
        assert result.confidence_factor == pytest.approx(0.85)

    def test_confidence_factor_scales_with_failures(self) -> None:
        results = _all_pass()
        results[CHECK_GOODHART] = False
        results[CHECK_COUNTEREXAMPLE] = False
        result = ConclusionGate().submit("C", results)
        assert result.confidence_factor == pytest.approx(0.70)

    def test_empty_conclusion_raises(self) -> None:
        with pytest.raises(ValueError, match="conclusion esta vacia"):
            ConclusionGate().submit("  ", _all_pass())

    def test_missing_check_raises(self) -> None:
        results = _all_pass()
        del results[CHECK_GOODHART]
        with pytest.raises(ValueError, match="faltan resultados"):
            ConclusionGate().submit("C", results)

    def test_unknown_check_raises(self) -> None:
        results = _all_pass()
        results["ataque_inventado"] = True
        with pytest.raises(ValueError, match="desconocidos"):
            ConclusionGate().submit("C", results)

    def test_result_is_frozen(self) -> None:
        result = ConclusionGate().submit("C", _all_pass())
        with pytest.raises(AttributeError):
            result.verdict = Verdict.REVISE_CONFIDENCE  # type: ignore[misc]
