"""Tests para canon_audit (supply-chain) + transcribe_discipline + governance (ADR-0089).

Triple audit (GenTrust/Socket/Snyk): URLs del canon PEC verificadas
(vivas + https). AssemblyAI 2-pasos: verbatim + rewrite con nombres,
numeros y fechas exactos. Governance 4 tests: pausa, decision-log,
watcher, vocero.
"""

import pytest

from harness.orchestrator.governance_checks import (
    GOVERNANCE_TESTS,
    governance_checklist,
)
from harness.orchestrator.transcribe_discipline import (
    transcribe_instruction,
)
from harness.validation.canon_audit import (
    CanonReport,
    audit_urls,
)


def _status_ok(url: str) -> int:
    """Fake HTTP 200 para todo."""
    return 200


def _status_mixed(url: str) -> int:
    """Fake: URLs con 'viejo' dan 404."""
    return 404 if "viejo" in url else 200


def test_canon_all_alive() -> None:
    """Todas las URLs vivas -> PASS."""
    report = audit_urls(["https://a.io", "https://b.io"], _status_ok)
    assert isinstance(report, CanonReport)
    assert report.passed is True
    assert report.dead == ()


def test_canon_dead_listed() -> None:
    """URLs muertas se listan (PEC con links rotos degrada)."""
    report = audit_urls(
        ["https://ok.io", "https://viejo.io/doc"], _status_mixed
    )
    assert report.passed is False
    assert report.dead == ("https://viejo.io/doc",)


def test_canon_non_https_rejected() -> None:
    """HTTP sin S se marca (canon exige https)."""
    report = audit_urls(["http://inseguro.io"], _status_ok)
    assert report.passed is False


def test_canon_empty_raises() -> None:
    """Lista vacia falla accionable."""
    with pytest.raises(ValueError, match="WHAT"):
        audit_urls([], _status_ok)


def test_transcribe_instruction_exactness() -> None:
    """La instruccion exige nombres/numeros/fechas exactos."""
    text = transcribe_instruction()
    lowered = text.lower()
    assert "nombres" in lowered
    assert "meros" in lowered  # numeros
    assert "fechas" in lowered
    assert "verbatim" in lowered


def test_transcribe_two_steps() -> None:
    """Los 2 pasos estan declarados (verbatim + rewrite)."""
    text = transcribe_instruction()
    assert "1" in text and "2" in text


def test_governance_four_tests() -> None:
    """Los 4 tests de governance existen (pausa/log/watcher/vocero)."""
    assert GOVERNANCE_TESTS == ("pausa", "decision-log", "watcher", "vocero")
    assert len(governance_checklist()) == 4


def test_governance_checklist_actionable() -> None:
    """Cada test trae pregunta accionable."""
    for name, question in governance_checklist():
        assert question.strip().endswith("?")
