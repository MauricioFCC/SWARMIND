"""Tests para fanout_gate — anti-sobre-descomposicion (ADR-0075).

Frontera (arXiv 2602.07787 Minitap + EECS-2026-123): si el baseline
single-agent ya logra >= 80% de exito, descomponer en fan-out ANADE
ruido (redes no estructuradas amplifican errores hasta 17.2x). El gate
decide si vale la pena fan-out con un probe de 1 pasada.
"""

import pytest

from harness.orchestrator.fanout_gate import (
    FANOUT_NOISE_AMPLIFICATION,
    SINGLE_AGENT_THRESHOLD,
    FanoutDecision,
    should_fanout,
)


def test_below_threshold_fans_out() -> None:
    """Baseline debil (< 80%) -> fan-out vale la pena."""
    decision = should_fanout(baseline_success=0.6)
    assert decision is FanoutDecision.FANOUT


def test_at_threshold_skips_fanout() -> None:
    """Baseline fuerte (>= 80%) -> single-agent sin fan-out."""
    assert should_fanout(baseline_success=0.8) is FanoutDecision.SINGLE
    assert should_fanout(baseline_success=0.95) is FanoutDecision.SINGLE


def test_override_forces_fanout() -> None:
    """force=True vence al gate (escape hatch del operador)."""
    assert should_fanout(baseline_success=0.95, force=True) is FanoutDecision.FANOUT


def test_invalid_success_raises() -> None:
    """success fuera de [0,1] falla accionable."""
    with pytest.raises(ValueError, match="WHAT"):
        should_fanout(baseline_success=1.2)
    with pytest.raises(ValueError, match="WHAT"):
        should_fanout(baseline_success=-0.1)


def test_constants_documented() -> None:
    """Constantes de frontera: 0.8 threshold, 17.2x amplificacion."""
    assert SINGLE_AGENT_THRESHOLD == 0.8
    assert FANOUT_NOISE_AMPLIFICATION == 17.2


def test_decision_is_frozen() -> None:
    """FanoutDecision es un enum (inmutable)."""
    with pytest.raises(AttributeError):
        FanoutDecision.SINGLE = "x"  # type: ignore[misc]
