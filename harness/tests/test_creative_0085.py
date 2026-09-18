"""Tests para voto con stakes + trajectory audit + TTL cognition (ADR-0085).

Frontera: wagering mechanisms (arXiv 2607.04389: stake = ventaja esperada;
deliberative consensus DEGRADA a 76% por sycophancy -> voto independiente,
nunca debate) + Ouroboros trajectory audits (vetar acceso a verifier/tests;
auto-zero) + CL-Bench (metadata temporal/dominio + TTL; 0.2301 vs 0.1855).
"""

import pytest

from harness.memory_rag.cue_ledger import CueLedger
from harness.orchestrator.batch_vote import (
    stake_weighted_vote,
)
from harness.validation.trajectory_audit import (
    AUDIT_RULES,
    audit_trajectory,
)


def test_stake_weighted_vote_beats_flat_majority() -> None:
    """2 votos debiles vs 1 fuerte calibrado: gana el fuerte."""
    out = stake_weighted_vote(
        votes=("a", "a", "b"),
        stakes=(0.3, 0.3, 0.95),
    )
    assert out.winner == "b"
    assert out.total_stake == pytest.approx(1.55)


def test_stake_weighted_tie_breaks_by_stake() -> None:
    """Empate 1-1: gana el de mayor stake (sin debate sycophant)."""
    out = stake_weighted_vote(votes=("x", "y"), stakes=(0.4, 0.9))
    assert out.winner == "y"


def test_stake_invalid_raises() -> None:
    """Stakes fuera de [0,1] o longitudes distintas fallan accionable."""
    with pytest.raises(ValueError, match="WHAT"):
        stake_weighted_vote(votes=("a", "b"), stakes=(0.5,))
    with pytest.raises(ValueError, match="WHAT"):
        stake_weighted_vote(votes=("a",), stakes=(1.5,))


def test_audit_flags_verifier_access() -> None:
    """Acceso a tests/verifier/oracle en la traza -> flag + auto-zero."""
    trace = [
        {"agent": "builder", "action": "edit", "target": "harness/x.py"},
        {"agent": "builder", "action": "read", "target": "tests/test_x.py"},
    ]
    report = audit_trajectory(trace)
    assert report.score == 0.0
    assert any("verifier" in f.lower() or "test" in f.lower() for f in report.flags)


def test_audit_clean_trace_passes() -> None:
    """Traza sin accesos prohibidos -> score 1.0, sin flags."""
    trace = [
        {"agent": "builder", "action": "edit", "target": "harness/x.py"},
        {"agent": "guardian", "action": "verify", "target": "harness/x.py"},
    ]
    report = audit_trajectory(trace)
    assert report.score == 1.0
    assert report.flags == ()


def test_audit_rules_documented() -> None:
    """Las reglas de auditoria estan documentadas (verifier/tests/oracle)."""
    joined = " ".join(AUDIT_RULES).lower()
    assert "test" in joined and "verifier" in joined


def test_cue_ttl_expires() -> None:
    """Cue con TTL vencido se poda en inject (CL-Bench: anti-stale)."""
    now = [1000.0]
    ledger = CueLedger(clock=lambda: now[0])
    ledger.register("hecho viejo", source="x.md", ttl_s=60.0)
    now[0] += 120.0
    index = ledger.inject("s1")
    assert "hecho viejo" not in index
    assert ledger.pruned_expired >= 1


def test_cue_without_ttl_lives() -> None:
    """Cue sin TTL no expira (compat hacia atras)."""
    now = [1000.0]
    ledger = CueLedger(clock=lambda: now[0])
    ledger.register("hecho vivo", source="x.md")
    now[0] += 10_000.0
    assert "hecho vivo" in ledger.inject("s1")
