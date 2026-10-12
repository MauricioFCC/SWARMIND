"""Tests TDD para TriageSLM — triage SLM con cascada a DifficultyRouter (FR-C1).

RED primero (ADR-0103 / WS-C): fija el contrato de ``TriageResult``/``TriageSLM``
(DI del small model, validacion 1..5 y fallback determinista). 0 LLM real: el
small model es un callable inyectado (mock).

Criterios (AAA, 1 test = 1 criterio):
  (a) JSON valido -> TriageResult correcto.
  (b) complexity fuera de rango -> fallback.
  (c) callable lanza -> fallback usa DifficultyRouter (traduccion de nivel).
  (d) JSON malformado -> fallback.
  (e) fallback nunca lanza (incluso texto vacio o router caido).
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from harness.orchestrator.difficulty_router import (
    ComplexityFeatures,
    ComplexityLevel,
    DifficultyRouter,
    PipelineType,
    RoutingDecision,
)
from harness.orchestrator.triage_slm import TriageResult, TriageSLM

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _decision(level: ComplexityLevel) -> RoutingDecision:
    """Construye un RoutingDecision determinista para el nivel dado.

    Args:
        level: Nivel de complejidad a envolver.

    Returns:
        RoutingDecision con pipeline DEEP y features vacias.
    """
    return RoutingDecision("t", level, PipelineType.DEEP, 0.9, ComplexityFeatures())


# ===========================================================================
# (a) JSON valido
# ===========================================================================


class TestValidJSON:
    """El small model devuelve JSON valido y en rango."""

    def test_valid_json_string(self) -> None:
        """JSON string valido -> TriageResult con campos exactos."""
        raw = '{"intent": "backend", "complexity": 4}'
        callable_ = MagicMock(return_value=raw)

        result = TriageSLM(small_model_callable=callable_).triage("crear api")

        assert result == TriageResult(intent="backend", complexity=4, raw=raw)
        callable_.assert_called_once_with("crear api")

    def test_dict_return_is_accepted(self) -> None:
        """Un dict directo tambien es una respuesta valida."""
        result = TriageSLM(
            small_model_callable=lambda _text: {"intent": "ops", "complexity": 2}
        ).triage("t")

        assert result.intent == "ops"
        assert result.complexity == 2
        assert result.raw == ""

    def test_intent_is_stripped(self) -> None:
        """El intent se normaliza (sin espacios sobrantes)."""
        result = TriageSLM(
            small_model_callable=lambda _t: '{"intent": "  ops  ", "complexity": 1}'
        ).triage("t")

        assert result.intent == "ops"


# ===========================================================================
# (b) complexity fuera de rango
# ===========================================================================


class TestOutOfRange:
    """Complexity fuera de 1..5 cae al fallback determinista."""

    @pytest.mark.parametrize("complexity", [0, 6, -1, 99])
    def test_out_of_range_falls_back(
        self, monkeypatch: pytest.MonkeyPatch, complexity: int
    ) -> None:
        """Valor fuera de rango -> fallback (no se recorta silenciosamente)."""
        monkeypatch.setattr(
            DifficultyRouter, "route", lambda _self, _m: _decision(ComplexityLevel.MODERATE)
        )
        raw = json.dumps({"intent": "x", "complexity": complexity})

        result = TriageSLM(small_model_callable=lambda _t: raw).triage("t")

        assert result.complexity == 3  # MODERATE -> 3
        assert result.raw == ""

    def test_bool_complexity_falls_back(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``True`` es int en Python pero NO es una complejidad valida."""
        monkeypatch.setattr(
            DifficultyRouter, "route", lambda _self, _m: _decision(ComplexityLevel.SIMPLE)
        )
        raw = json.dumps({"intent": "x", "complexity": True})

        result = TriageSLM(small_model_callable=lambda _t: raw).triage("t")

        assert result.complexity == 2  # SIMPLE -> 2

    @pytest.mark.parametrize("payload", ['{"complexity": 3}', '{"intent": "", "complexity": 3}'])
    def test_missing_or_empty_fields_fall_back(
        self, monkeypatch: pytest.MonkeyPatch, payload: str
    ) -> None:
        """Sin intent o con intent vacio -> fallback."""
        monkeypatch.setattr(
            DifficultyRouter, "route", lambda _self, _m: _decision(ComplexityLevel.TRIVIAL)
        )

        result = TriageSLM(small_model_callable=lambda _t: payload).triage("t")

        assert result.complexity == 1  # TRIVIAL -> 1


# ===========================================================================
# (c) callable lanza -> fallback por DifficultyRouter
# ===========================================================================


class TestCallableFailure:
    """Una excepcion del SLM activa la cascada determinista."""

    def test_callable_raises_uses_difficulty_router(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """RuntimeError del SLM -> fallback traduce el nivel del router."""
        captured: dict[str, str] = {}

        def fake_route(_self: DifficultyRouter, message: str) -> RoutingDecision:
            captured["message"] = message
            return _decision(ComplexityLevel.VERY_COMPLEX)

        monkeypatch.setattr(DifficultyRouter, "route", fake_route)

        def boom(_text: str) -> str:
            raise RuntimeError("SLM down")

        result = TriageSLM(small_model_callable=boom).triage("tarea compleja")

        assert captured["message"] == "tarea compleja"
        assert result.complexity == 5  # VERY_COMPLEX -> 5
        assert result.intent == "very_complex"
        assert result.raw == ""


# ===========================================================================
# (d) JSON malformado
# ===========================================================================


class TestMalformedJSON:
    """JSON invalido no se propaga: cae al fallback."""

    @pytest.mark.parametrize("payload", ["not-json", "{oops", "", "[]", "42"])
    def test_malformed_falls_back(
        self, monkeypatch: pytest.MonkeyPatch, payload: str
    ) -> None:
        """Payload no-dict/JSON roto -> fallback (COMPLEX -> 4)."""
        monkeypatch.setattr(
            DifficultyRouter, "route", lambda _self, _m: _decision(ComplexityLevel.COMPLEX)
        )

        result = TriageSLM(small_model_callable=lambda _t: payload).triage("t")

        assert result.complexity == 4  # COMPLEX -> 4


# ===========================================================================
# (e) fallback nunca lanza
# ===========================================================================


class TestFallbackNeverRaises:
    """``fallback`` es publico y defensivo."""

    def test_no_callable_uses_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sin small model, ``triage`` delega en el fallback."""
        monkeypatch.setattr(
            DifficultyRouter, "route", lambda _self, _m: _decision(ComplexityLevel.TRIVIAL)
        )

        result = TriageSLM().triage("")

        assert result.complexity == 1
        assert isinstance(result.raw, str)

    def test_fallback_empty_text(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Texto vacio no lanza; devuelve un TriageResult valido."""
        monkeypatch.setattr(
            DifficultyRouter, "route", lambda _self, _m: _decision(ComplexityLevel.SIMPLE)
        )

        result = TriageSLM().fallback("")

        assert 1 <= result.complexity <= 5
        assert result.intent

    def test_fallback_router_failure_is_contained(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Si el propio router falla, el fallback devuelve un valor de reserva."""
        def boom(_self: DifficultyRouter, _m: str) -> RoutingDecision:
            raise RuntimeError("router down")

        monkeypatch.setattr(DifficultyRouter, "route", boom)

        result = TriageSLM().fallback("cualquier cosa")

        assert 1 <= result.complexity <= 5
        assert result.intent
        assert result.raw == ""
