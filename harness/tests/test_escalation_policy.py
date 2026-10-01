"""Tests TDD de la politica de escalado por verificacion (ADR-0102).

Cubren: verificador estructural (vacio/enano/degenerado/JSON), confianza
verbalizada (parseo y normalizacion), escalera de tiers y las tres salidas
de `decide` (accept/escalate/cloud).
"""

from __future__ import annotations

import pytest

from harness.model_router.escalation_policy import (
    TIER_LADDER,
    VERBALIZED_CONFIDENCE_THRESHOLD,
    decide,
    next_tier,
    parse_confidence,
    verify_structural,
)


@pytest.mark.parametrize(
    ("output", "expect_json", "ok", "verifier"),
    [
        ("respuesta util y suficientemente larga", False, True, "structural"),
        ("", False, False, "length"),
        ("   ", False, False, "length"),
        ("corto", False, False, "length"),
        ("aaaaaaaaaaaaaa", False, False, "degenerate"),
        ('{"clave": 1}', True, True, "structural"),
        ('{"clave": 1}', False, True, "structural"),
        ("esto no es json valido", True, False, "json"),
        ('{"a": 1,', True, False, "json"),
    ],
)
def test_verify_structural(output: str, expect_json: bool, ok: bool, verifier: str) -> None:
    """El verificador estructural clasifica contenido real vs invalido."""
    verdict = verify_structural(output, expect_json=expect_json)
    assert verdict.ok is ok
    assert verdict.verifier == verifier


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("confianza: 0.85", 0.85),
        ("Confianza: 85%", 0.85),
        ("confidence: 0.3", 0.3),
        ("sin metrica aqui", None),
        ("confianza: 1.5", None),
        ("confianza: -0.2", None),
    ],
)
def test_parse_confidence(output: str, expected: float | None) -> None:
    """Extrae confianza 0..1 y descarta valores fuera de rango."""
    assert parse_confidence(output) == expected


def test_next_tier_escalates_and_stops() -> None:
    """La escalera sube y devuelve None en el tope."""
    assert next_tier("fast") == "quality"
    assert next_tier("quality") == "coding"
    assert next_tier("coding") == "reasoning"
    assert next_tier("reasoning") is None
    assert TIER_LADDER == ("fast", "quality", "coding", "reasoning")


def test_decide_accepts_valid_output() -> None:
    """Salida valida sin confianza declarada se acepta."""
    decision = decide("fast", "respuesta util y completa")
    assert decision.action == "accept"
    assert decision.target_tier is None
    assert decision.verdict.ok is True


def test_decide_accepts_confident_output() -> None:
    """Salida valida con confianza alta se acepta."""
    out = "respuesta valida. confianza: 0.95"
    decision = decide("quality", out)
    assert decision.action == "accept"


def test_decide_escalates_low_confidence() -> None:
    """Confianza verbalizada bajo el umbral escala preventivamente."""
    out = "respuesta valida pero dudosa. confianza: 0.40"
    decision = decide("fast", out)
    assert decision.action == "escalate"
    assert decision.target_tier == "quality"
    assert "confianza" in decision.reason


def test_decide_escalates_invalid_output() -> None:
    """Salida degenerada escala al siguiente tier."""
    decision = decide("fast", "zzzzzzzzzzzzzz")
    assert decision.action == "escalate"
    assert decision.target_tier == "quality"


def test_decide_delegates_to_cloud_at_top() -> None:
    """En el tope de la flota, una salida invalida va a cloud."""
    decision = decide("reasoning", "")
    assert decision.action == "cloud"
    assert decision.target_tier is None


def test_decide_custom_threshold() -> None:
    """Umbral configurable cambia la decision (calibracion futura)."""
    out = "respuesta. confianza: 0.60"
    assert decide("fast", out, confidence_threshold=0.50).action == "accept"
    assert decide("fast", out, confidence_threshold=0.90).action == "escalate"


def test_threshold_documented() -> None:
    """El umbral inicial esta documentado y en rango."""
    assert 0.0 < VERBALIZED_CONFIDENCE_THRESHOLD < 1.0
