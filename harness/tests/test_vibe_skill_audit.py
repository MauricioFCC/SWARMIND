"""Tests para vibe_review_gate + skill_audit_pipeline (ADR-0089, 2do analisis).

Vibe-reviewing (CodeRabbit: codigo IA trae 8x fallos perf, 2.7x sec):
Deep Scan + 2o agente filtro antes de merge. Skill-auditor Cloudflare
6 fases: recon->caza->validacion->verificacion->salida->reporte.
"""

import pytest

from harness.orchestrator.skill_audit_pipeline import (
    AuditPhase,
    run_skill_audit,
)
from harness.validation.vibe_review_gate import (
    VibeReport,
    vibe_review_gate,
)


def _perf_clean(diff: str) -> list[str]:
    """Fake perf scan sin hallazgos."""
    return []


def _perf_dirty(diff: str) -> list[str]:
    """Fake perf scan con 1 hallazgo."""
    return ["N+1 query en loop"]


def _sec_clean(diff: str) -> list[str]:
    """Fake sec scan sin hallazgos."""
    return []


def _second_agent_approves(diff: str) -> bool:
    """Segundo agente aprueba."""
    return True


def _second_agent_rejects(diff: str) -> bool:
    """Segundo agente rechaza."""
    return False


def test_vibe_clean_passes() -> None:
    """Diff limpio + 2o agente aprueba -> PASS."""
    report = vibe_review_gate(
        "diff: fix typo", _perf_clean, _sec_clean, _second_agent_approves
    )
    assert isinstance(report, VibeReport)
    assert report.passed is True
    assert report.perf_findings == ()
    assert report.sec_findings == ()


def test_vibe_perf_finding_blocks() -> None:
    """Hallazgo perf (8x) bloquea aunque el 2o agente apruebe."""
    report = vibe_review_gate(
        "diff: loop con query", _perf_dirty, _sec_clean, _second_agent_approves
    )
    assert report.passed is False
    assert len(report.perf_findings) == 1


def test_vibe_second_agent_veto_blocks() -> None:
    """Veto del 2o agente bloquea (filtro independiente)."""
    report = vibe_review_gate(
        "diff: ok", _perf_clean, _sec_clean, _second_agent_rejects
    )
    assert report.passed is False
    assert report.second_agent_approved is False


def test_vibe_empty_diff_raises() -> None:
    """Diff vacio falla accionable."""
    with pytest.raises(ValueError, match="WHAT"):
        vibe_review_gate("", _perf_clean, _sec_clean, _second_agent_approves)


def test_audit_phases_in_order() -> None:
    """Las 6 fases corren en orden y el reporte las lista."""
    calls: list[str] = []

    def make_phase(name):
        def _fn(skill: str) -> list[str]:
            calls.append(name)
            return [f"{name}-ok"]

        return _fn

    fns = {phase: make_phase(phase.value) for phase in AuditPhase}
    report = run_skill_audit("security-audit", fns)
    assert [p for p in report.phases] == [p.value for p in AuditPhase]
    assert calls == [p.value for p in AuditPhase]
    assert report.passed is True


def test_audit_phase_failure_blocks() -> None:
    """Fase que retorna hallazgos criticos bloquea con la fase indicada."""
    def _bad(skill: str) -> list[str]:
        return ["CRITICAL: sin schema"]

    fns = {AuditPhase.RECON: (lambda s: []), AuditPhase.HUNT: _bad,
           AuditPhase.VALIDATE: (lambda s: []), AuditPhase.VERIFY: (lambda s: []),
           AuditPhase.OUTPUT: (lambda s: []), AuditPhase.REPORT: (lambda s: [])}
    report = run_skill_audit("x", fns)
    assert report.passed is False
    assert report.blocked_at == AuditPhase.HUNT.value


def test_audit_unknown_skill_raises() -> None:
    """Skill vacia falla accionable."""
    with pytest.raises(ValueError, match="WHAT"):
        run_skill_audit("", {})
