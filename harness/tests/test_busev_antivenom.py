"""Tests para evidence_search + antivenom_filter + sprt_governor (ADR-0087).

BUSEV: 4 estrategias en paralelo (academica/oficial/critica/comunidad),
ciegas 1+1 por defecto (escala a 4 solo con contradiccion o decision
irreversible), matriz converge/condiciona, SIFT-1 vigencia <18m tech,
claim-trace con IDs. Antiveneno 4 cortes: spam/autoridad, doc vieja,
vendor sin metodo, predatorio sin venue. SPRT: score-juez por ronda +
umbral calibrado + cap duro.
"""

import pytest

from harness.orchestrator.evidence_search import (
    EvidenceMatrix,
    evidence_search,
)
from harness.orchestrator.sprt_governor import (
    GovernorDecision,
    SPRTGovernor,
)
from harness.validation.antivenom_filter import (
    SourceVerdict,
    antivenom_check,
)


def _strategy_fn(findings):
    """Fabrica estrategia que retorna hallazgos fijos."""

    def _fn(question: str) -> list[dict]:
        return findings

    return _fn


def test_evidence_default_two_strategies() -> None:
    """Por defecto 1+1 ciegas (investiga + refuta), no las 4."""
    matrix = evidence_search(
        "SSE vs WebSocket?",
        strategies={
            "academica": _strategy_fn([{"id": "A1", "claim": "SSE gana fan-out", "converges": True}]),
            "critica": _strategy_fn([{"id": "C1", "claim": "proxies bufferizan", "converges": False}]),
        },
    )
    assert isinstance(matrix, EvidenceMatrix)
    assert len(matrix.rows) == 2
    assert matrix.rows[0].source_id == "A1"


def test_evidence_scales_to_four_on_contradiction() -> None:
    """Con contradiccion real o decision irreversible: escala a 4."""
    matrix = evidence_search(
        "migrar de base de datos?",
        strategies={
            "a": _strategy_fn([{"id": "A1", "claim": "x", "converges": True}]),
            "b": _strategy_fn([{"id": "B1", "claim": "no-x", "converges": True}]),
            "c": _strategy_fn([{"id": "C1", "claim": "x con matiz", "converges": False}]),
            "d": _strategy_fn([{"id": "D1", "claim": "x en prod", "converges": True}]),
        },
        escalate=True,
    )
    assert len(matrix.rows) == 4


def test_evidence_empty_question_raises() -> None:
    """Pregunta vacia falla accionable."""
    with pytest.raises(ValueError, match="WHAT"):
        evidence_search("", strategies={})


def test_antivenom_spam_cut() -> None:
    """Blog anonimo sin metodo -> V1 spam (descartar numero, conservar idea)."""
    out = antivenom_check(
        url="https://blog-anonimo.xyz/surreal-10x",
        has_method=False, months_old=2, is_vendor=False, venue=None,
    )
    assert out.passed is False
    assert "V1" in out.failed_cut or "spam" in out.reason.lower() or "autoridad" in out.reason.lower()


def test_antivenom_stale_doc() -> None:
    """Doc tech >18m -> V2 vigencia (revalidar)."""
    out = antivenom_check(
        url="https://tutorial.com/sse-2019", has_method=True,
        months_old=80, is_vendor=False, venue="blog",
    )
    assert out.passed is False


def test_antivenom_vendor_without_method() -> None:
    """Vendor sin metodo reproducible -> V3 (direccion si, cifra no)."""
    out = antivenom_check(
        url="https://vendor.com/benchmark", has_method=False,
        months_old=1, is_vendor=True, venue="vendor",
    )
    assert out.passed is False


def test_antivenom_predatory() -> None:
    """Sin venue verificable -> V4 (no entra al veredicto)."""
    out = antivenom_check(
        url="https://revista-dudosa.io/paper", has_method=True,
        months_old=1, is_vendor=False, venue=None,
    )
    assert out.passed is False


def test_antivenom_clean_source_passes() -> None:
    """Fuente con metodo + vigente + venue -> PASS."""
    out = antivenom_check(
        url="https://arxiv.org/abs/2605.19193", has_method=True,
        months_old=3, is_vendor=False, venue="arXiv",
    )
    assert isinstance(out, SourceVerdict)
    assert out.passed is True


def test_sprt_stops_on_threshold() -> None:
    """Score >= umbral -> STOP (parada por acuerdo)."""
    gov = SPRTGovernor(threshold=0.8, max_rounds=2)
    out = gov.observe(0.85)
    assert out is GovernorDecision.STOP


def test_sprt_continues_below_threshold() -> None:
    """Score bajo umbral y con rondas -> CONTINUE."""
    gov = SPRTGovernor(threshold=0.8, max_rounds=2)
    out = gov.observe(0.5)
    assert out is GovernorDecision.CONTINUE


def test_sprt_hard_cap() -> None:
    """Agotadas las rondas -> STOP por cap (aunque no haya acuerdo)."""
    gov = SPRTGovernor(threshold=0.99, max_rounds=2)
    gov.observe(0.5)
    out = gov.observe(0.5)
    assert out is GovernorDecision.STOP


def test_sprt_boundary_exact_threshold() -> None:
    """Score == umbral exacto TAMBIEN para (gate >=)."""
    gov = SPRTGovernor(threshold=0.8, max_rounds=2)
    assert gov.observe(0.8) is GovernorDecision.STOP


def test_sprt_invalid_config_raises() -> None:
    """Umbral fuera de (0,1) o max_rounds <1 falla accionable."""
    with pytest.raises(ValueError, match="WHAT"):
        SPRTGovernor(threshold=1.5, max_rounds=2)
    with pytest.raises(ValueError, match="WHAT"):
        SPRTGovernor(threshold=0.8, max_rounds=0)
