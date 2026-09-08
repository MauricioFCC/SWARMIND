"""Tests para compaction calibrada (AgeMem) — ADR-0074.

Frontera (AgeMem 2026): ceiling/warn/critical con acciones diferenciadas
(summary en warn, filter+drop en critical), dedup coseno de turnos
repetidos y revision periodica. Complementa structured_compact (no lo
reemplaza): decide CUANDO y QUE hacer antes de llamarlo.
"""

import pytest

from harness.memory_rag.compaction_calibration import (
    DEFAULT_CRITICAL_RATIO,
    DEFAULT_TOKEN_CEILING,
    DEFAULT_WARN_RATIO,
    CompactionPolicy,
    compact_calibrated,
    estimate_tokens,
)


def _session(chars: int) -> str:
    """Fabrica una sesion con >= N chars (techo, no piso)."""
    line = "el agente leyo el archivo y escribio pruebas nuevas\n"
    repeats = (chars // len(line)) + 1
    return line * repeats


def test_estimate_tokens_char_ratio() -> None:
    """estimate_tokens usa ratio ~4 chars/token."""
    assert estimate_tokens("a" * 400) == 100


def test_under_warn_returns_original() -> None:
    """Sesion bajo warn: sin compaction, identica."""
    small = "x" * 1000
    out = compact_calibrated(small)
    assert out == small


def test_warn_zone_compacts_with_summary() -> None:
    """Zona warn: compaction suave (budget ratio warn)."""
    session = _session(8000)  # ~2000 tokens > warn (0.75 * 2000? ver ceiling)
    out = compact_calibrated(session)
    assert len(out) < len(session)


def test_critical_zone_more_aggressive() -> None:
    """Zona critical: ratio mas agresivo que warn."""
    policy = CompactionPolicy(token_ceiling=1000, warn_ratio=0.75, critical_ratio=0.90)
    warn_text = _session(3000)   # 750 tok < 900 (critical) -> warn
    crit_text = _session(5000)   # 1250 tok > 900 -> critical
    out_warn = compact_calibrated(warn_text, policy)
    out_crit = compact_calibrated(crit_text, policy)
    r_warn = len(out_warn) / len(warn_text)
    r_crit = len(out_crit) / len(crit_text)
    assert r_crit <= r_warn


def test_critical_boundary_exact_tokens(monkeypatch) -> None:
    """Sesion con tokens == critical_tokens exactos usa ratio critico (<=)."""
    captured: dict[str, float] = {}

    def _spy(text: str, budget_ratio: float = 0.6, min_chars: int = 50) -> str:
        captured["ratio"] = budget_ratio
        return "compacto"

    monkeypatch.setattr(
        "harness.memory_rag.compaction_calibration.structured_compact", _spy
    )
    # Fuerza la frontera exacta: tokens == ceiling * critical_ratio = 5400
    # Con '<=' exacto entra en la zona SUAVE (0.7); '<' lo mandaria a la
    # agresiva (0.4) — la asercion mata ese mutante.
    monkeypatch.setattr(
        "harness.memory_rag.compaction_calibration.estimate_tokens", lambda t: 5400
    )
    compact_calibrated("x" * 100, CompactionPolicy(token_ceiling=6000))
    assert captured["ratio"] == 0.7


def test_dedup_repeated_lines() -> None:
    """Lineas identicas consecutivas se colapsan (dedup coseno-like exacto)."""
    session = "linea repetida\n" * 100
    out = compact_calibrated(session, CompactionPolicy(token_ceiling=10**9))
    assert out.count("linea repetida") <= 3


def test_invalid_policy_raises() -> None:
    """warn >= critical o ratios fuera de rango fallan accionable."""
    with pytest.raises(ValueError, match="WHAT"):
        CompactionPolicy(warn_ratio=0.95, critical_ratio=0.75)
    with pytest.raises(ValueError, match="WHAT"):
        CompactionPolicy(warn_ratio=1.2)


def test_constants_documented() -> None:
    """Defaults AgeMem: ceiling 6000, warn 0.75, critical 0.90."""
    assert DEFAULT_TOKEN_CEILING == 6000
    assert DEFAULT_WARN_RATIO == 0.75
    assert DEFAULT_CRITICAL_RATIO == 0.90
