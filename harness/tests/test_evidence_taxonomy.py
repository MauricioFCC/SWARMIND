"""Tests de evidence_taxonomy — O/M/I/H/S/U y promocion gobernada (ADR-0054)."""
from __future__ import annotations

import pytest

from harness.context.evidence_taxonomy import (
    UNRESOLVED,
    Claim,
    EvidenceClass,
    can_promote,
    downgrade,
    promote,
)


class TestEvidenceClass:
    """Escalera de fuerza U < S < H < I < M < O."""

    def test_ordering_is_strength_ascending(self) -> None:
        assert (
            EvidenceClass.UNKNOWN
            < EvidenceClass.SPECULATION
            < EvidenceClass.HYPOTHESIS
            < EvidenceClass.INFERRED
            < EvidenceClass.MEASURED
            < EvidenceClass.OBSERVED
        )

    def test_codes_match_atlas(self) -> None:
        expected = {
            EvidenceClass.OBSERVED: "O",
            EvidenceClass.MEASURED: "M",
            EvidenceClass.INFERRED: "I",
            EvidenceClass.HYPOTHESIS: "H",
            EvidenceClass.SPECULATION: "S",
            EvidenceClass.UNKNOWN: "U",
        }
        for cls, code in expected.items():
            assert cls.code == code

    def test_unresolved_is_unknown(self) -> None:
        assert UNRESOLVED is EvidenceClass.UNKNOWN


class TestClaim:
    """Claim inmutable con validacion fail-fast."""

    def test_valid_claim_with_refs(self) -> None:
        claim = Claim(
            text="El cache reduce tokens 38%",
            evidence_class=EvidenceClass.MEASURED,
            evidence_refs=("benchmark-2026-08",),
        )
        assert claim.evidence_class.code == "M"

    def test_empty_text_raises(self) -> None:
        with pytest.raises(ValueError, match="texto del claim"):
            Claim(text="  ", evidence_class=EvidenceClass.UNKNOWN)

    def test_high_class_without_refs_raises(self) -> None:
        with pytest.raises(ValueError, match="evidence_refs"):
            Claim(text="afirmacion", evidence_class=EvidenceClass.OBSERVED)

    def test_unknown_claim_needs_no_refs(self) -> None:
        claim = Claim(text="pregunta abierta", evidence_class=UNRESOLVED)
        assert claim.evidence_refs == ()

    def test_claim_is_frozen(self) -> None:
        claim = Claim(text="x", evidence_class=EvidenceClass.UNKNOWN)
        with pytest.raises(AttributeError):
            claim.text = "y"  # type: ignore[misc]


class TestPromotion:
    """Promocion: un escalon por llamada, exige evidencia nueva."""

    def test_promote_one_step(self) -> None:
        assert promote(EvidenceClass.HYPOTHESIS, "medicion nueva") is (
            EvidenceClass.INFERRED
        )

    def test_promote_requires_new_evidence(self) -> None:
        with pytest.raises(ValueError, match="evidencia nueva"):
            promote(EvidenceClass.SPECULATION, "")

    def test_promote_rejects_whitespace_evidence(self) -> None:
        with pytest.raises(ValueError, match="evidencia nueva"):
            promote(EvidenceClass.SPECULATION, "   ")

    def test_cannot_skip_ladder_steps(self) -> None:
        # can_promote solo permite +1; saltar de S a M es ilegal.
        assert not can_promote(EvidenceClass.SPECULATION, EvidenceClass.MEASURED)

    def test_observed_is_ceiling(self) -> None:
        with pytest.raises(ValueError, match="tope"):
            promote(EvidenceClass.OBSERVED, "lo que sea")

    def test_can_promote_boundaries(self) -> None:
        assert can_promote(EvidenceClass.UNKNOWN, EvidenceClass.SPECULATION)
        assert not can_promote(EvidenceClass.OBSERVED, EvidenceClass.OBSERVED)


class TestDowngrade:
    """Degradacion honesta ante evidencia refutada."""

    def test_downgrade_one_step(self) -> None:
        assert downgrade(EvidenceClass.MEASURED) is EvidenceClass.INFERRED

    def test_downgrade_floor_is_unknown(self) -> None:
        assert downgrade(UNRESOLVED) is UNRESOLVED
