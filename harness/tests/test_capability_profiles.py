"""Tests para capability_profiles — routing por capacidades (ADR-0085/0086).

Mesa (2-1, hibrido): perfiles estaticos con scores por benchmark +
calibracion online (EWMA trust via veredictos) + fallback congelado.
Router: score = dot(caps, weights) * trust; conf >= 0.65 -> local.
"""

import pytest

from harness.model_router.capability_profiles import (
    LOCAL_CONFIDENCE,
    CapabilityProfile,
    classify_task,
    load_profiles,
    route_by_capability,
)


def _profiles():
    """Tres perfiles de prueba (coder/reasoner/fast)."""
    return (
        CapabilityProfile("coder-9b", 9.0, "Q4",
                          {"coding": 0.9, "reasoning": 0.6}, trust=1.0),
        CapabilityProfile("reason-9b", 9.0, "Q4",
                          {"coding": 0.6, "reasoning": 0.9}, trust=1.0),
        CapabilityProfile("tiny-2b", 2.0, "Q8",
                          {"coding": 0.5, "reasoning": 0.5}, trust=1.0),
    )


def test_classify_coding_task() -> None:
    """Tarea de codigo pesa coding (implementar/pytest/refactor)."""
    weights = classify_task("implementar funcion con pytest y refactor")
    assert weights["coding"] > weights["reasoning"]


def test_classify_reasoning_task() -> None:
    """Tarea de diseno pesa reasoning (arquitectura/tradeoffs)."""
    weights = classify_task("disenar arquitectura con tradeoffs")
    assert weights["reasoning"] > weights["coding"]


def test_route_picks_best_capability() -> None:
    """Codigo -> coder-9b; diseno -> reason-9b (dot x trust)."""
    coder = route_by_capability("implementar test", _profiles())
    assert coder.model_id == "coder-9b"
    assert coder.confidence >= LOCAL_CONFIDENCE
    designer = route_by_capability("disenar arquitectura", _profiles())
    assert designer.model_id == "reason-9b"


def test_low_confidence_goes_cloud() -> None:
    """Scores bajos en todo -> cloud (conf < 0.65)."""
    weak = (
        CapabilityProfile("weak", 1.0, "Q8", {"coding": 0.2}, trust=0.5),
    )
    out = route_by_capability("implementar compilador", weak)
    assert out.model_id == "cloud"
    assert out.confidence < LOCAL_CONFIDENCE


def test_trust_calibration() -> None:
    """Veredictos ajustan trust (EWMA 0.9/0.1)."""
    profiles = _profiles()
    coder = next(p for p in profiles if p.model_id == "coder-9b")
    bad = coder.calibrate(success=False)
    assert bad.trust == pytest.approx(0.9)
    good = bad.calibrate(success=True)
    assert good.trust == pytest.approx(0.9 * 0.9 + 0.1)


def test_profile_is_frozen() -> None:
    """CapabilityProfile es inmutable (calibrate retorna copia)."""
    coder = _profiles()[0]
    assert coder.calibrate(success=True) is not coder


def test_load_builtin_profiles(tmp_path) -> None:
    """Sin YAML: perfiles builtin de los instalados (flota 2026-09-21: 6+1 standby)."""
    profiles = load_profiles(None)
    ids = {p.model_id for p in profiles}
    assert len(profiles) >= 6
    assert any("Qwen3.8" in i or "qwen" in i.lower() for i in ids)
    assert any("Bonsai" in i for i in ids)


def test_local_confidence_constant() -> None:
    """Umbral local documentado en 0.65."""
    assert LOCAL_CONFIDENCE == 0.65
