"""Tests TDD (spec-first) para AutoNudge (evolve_loop/nudge_system).

Contrato (spec):
- AutoNudge construye con vector_store y cognition inyectables (DI).
- tick() incrementa ticks; respeta intervalo salvo force=True.
- tick() con contexto valioso crea un nudge (stats.nudges_created++).
- tick() con contexto no valioso no crea nudge.
- force_nudge() fuerza la creación sin esperar intervalo.
- get_stats() devuelve métricas.

Invariantes:
- ticks nunca decrece.
- nudges_created solo crece con nudges reales.
"""
from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from harness.evolve_loop.nudge_system import AutoNudge


def _make_nudge(interval: int = 3600) -> AutoNudge:
    """Crea AutoNudge con mocks (DI)."""
    store = MagicMock()
    cognition = MagicMock()
    return AutoNudge(
        vector_store=store,
        cognition=cognition,
        interval_seconds=interval,
    )

class TestAutoNudgeContract:
    """Contrato principal del sistema de nudges."""

    def test_init_injects_dependencies(self) -> None:
        """Spec: vector_store y cognition se inyectan (no instancia reales)."""
        store = MagicMock()
        cognition = MagicMock()
        nudge = AutoNudge(vector_store=store, cognition=cognition, interval_seconds=60)
        assert nudge._store is store
        assert nudge._cognition is cognition

    def test_tick_increments_stats(self) -> None:
        """Spec: tick() incrementa ticks siempre."""
        nudge = _make_nudge(interval=3600)
        nudge.tick()
        stats = nudge.get_stats()
        assert stats["ticks"] >= 1

    def test_tick_within_interval_returns_none(self) -> None:
        """Spec: tick() sin force y dentro del intervalo devuelve None."""
        nudge = _make_nudge(interval=100000)
        nudge._last_nudge = time.time()  # recién nudged
        result = nudge.tick(force=False)
        assert result is None

    def test_tick_force_ignores_interval(self) -> None:
        """Spec: tick(force=True) ignora el intervalo."""
        nudge = _make_nudge(interval=100000)
        nudge._last_nudge = time.time()
        # force: pasa el check de intervalo
        with patch.object(nudge, "_collect_context", return_value=[]):
            nudge.tick(force=True)
        # No lanza, aunque no haya contexto

    def test_tick_without_context_returns_none(self) -> None:
        """Spec: sin contexto, tick no crea nudge."""
        nudge = _make_nudge(interval=0)
        with patch.object(nudge, "_collect_context", return_value=[]):
            result = nudge.tick(force=True)
        assert result is None
        assert nudge.get_stats()["nudges_created"] == 0

    def test_tick_with_low_score_returns_none(self) -> None:
        """Spec: contexto con score bajo no crea nudge."""
        nudge = _make_nudge(interval=0)
        ctx = [{"key": "value", "score": 0.01}]
        with patch.object(nudge, "_collect_context", return_value=ctx), \
             patch.object(nudge, "_evaluate_context", return_value=0.0):
            result = nudge.tick(force=True)
        assert result is None

    def test_tick_creates_nudge_with_valid_context(self) -> None:
        """Spec: contexto valioso crea un nudge."""
        nudge = _make_nudge(interval=0)
        ctx = [{"key": "k", "value": "v", "score": 0.9}]
        fake_nudge = {"domain": "test", "score": 0.9, "content": "x"}
        with patch.object(nudge, "_collect_context", return_value=ctx), \
             patch.object(nudge, "_evaluate_context", return_value=0.9), \
             patch.object(nudge, "_persist_nudge", return_value=fake_nudge), \
             patch.object(nudge, "_clean_old_nudges", return_value=0):
            result = nudge.tick(force=True)
        assert result is not None
        assert result["domain"] == "test"
        assert nudge.get_stats()["nudges_created"] == 1

    def test_force_nudge_method(self) -> None:
        """Spec: force_nudge() llama tick(force=True)."""
        nudge = _make_nudge(interval=3600)
        with patch.object(nudge, "tick", return_value=None) as mock_tick:
            nudge.force_nudge()
        mock_tick.assert_called_once_with(force=True)

    def test_get_stats_structure(self) -> None:
        """Spec: get_stats devuelve keys esperadas."""
        nudge = _make_nudge()
        stats = nudge.get_stats()
        assert "nudges_created" in stats
        assert "nudges_cleaned" in stats
        assert "ticks" in stats
        assert "errors" in stats


class TestAutoNudgeInvariants:
    """Invariantes (spec-first)."""

    def test_ticks_never_decrease(self) -> None:
        """Invariante: ticks es monotónico creciente."""
        nudge = _make_nudge(interval=0)
        t0 = nudge.get_stats()["ticks"]
        nudge.tick(force=True)
        nudge.tick(force=True)
        t2 = nudge.get_stats()["ticks"]
        assert t2 >= t0

    def test_errors_tracked_not_crashing(self) -> None:
        """Invariante: errores en el pipeline no crashean tick."""
        nudge = _make_nudge(interval=0)
        with patch.object(nudge, "_collect_context", side_effect=RuntimeError("boom")):
            nudge.tick(force=True)  # no debe lanzar
        assert nudge.get_stats()["errors"] >= 0


class TestContextCollection:
    """_collect_context: parseo de metadata y tolerancia a fallos."""

    def test_busca_en_la_coleccion_de_cognicion(self) -> None:
        nudge = _make_nudge()
        nudge._store.search.return_value = []
        assert nudge._collect_context() == []
        assert nudge._store.search.call_args[0][0] == "asi_cognition_store"

    def test_parsea_metadata_string_json_y_dict(self) -> None:
        """Acepta metadata como dict, como JSON en str y como str ilegible."""
        nudge = _make_nudge()
        nudge._store.search.return_value = [
            {"metadata": '{"domain": "kernel", "content": "contexto"}'},
            {"metadata": {"domain": "cache"}},
            {"metadata": "no-es-json {{{"},
        ]
        contexto = nudge._collect_context()
        assert contexto[0]["domain"] == "kernel"
        assert contexto[1]["domain"] == "cache"
        assert contexto[2] == {}

    def test_fallo_del_store_no_propaga(self) -> None:
        """Un fallo del store se cuenta como error y devuelve contexto vacío."""
        nudge = _make_nudge()
        nudge._store.search.side_effect = RuntimeError("store caido")
        assert nudge._collect_context() == []
        assert nudge.get_stats()["errors"] == 1


class TestEvaluateContext:
    """_evaluate_context: score determinista 0..1 por factores."""

    def test_vacio_da_cero(self) -> None:
        assert AutoNudge._evaluate_context([]) == pytest.approx(0.0)

    def test_sin_factores_da_cero(self) -> None:
        assert AutoNudge._evaluate_context([{}, {"domain": "x"}]) == pytest.approx(0.0)

    def test_metricas_de_score(self) -> None:
        score = AutoNudge._evaluate_context([{"metrics": {"overall_score": 0.8}}])
        assert score == pytest.approx(0.8)

    def test_metricas_se_limitan_a_uno(self) -> None:
        score = AutoNudge._evaluate_context([{"metrics": {"overall_score": 9}}])
        assert score == pytest.approx(1.0)

    def test_metricas_no_numericas_se_ignoran(self) -> None:
        assert AutoNudge._evaluate_context(
            [{"metrics": {"overall_score": "alta"}}]
        ) == pytest.approx(0.0)

    def test_contenido_largo_aporta_punto_medio(self) -> None:
        # metrics ausente aporta 0.0 (overall_score por defecto) + 0.5 por
        # el contenido largo -> media 0.25
        score = AutoNudge._evaluate_context([{"content": "x" * 101}])
        assert score == pytest.approx(0.25)

    def test_varios_tags_aportan(self) -> None:
        score = AutoNudge._evaluate_context([{"tags": ["a", "b", "c"]}])
        assert score == pytest.approx(0.15)

    def test_promedia_todos_los_factores(self) -> None:
        score = AutoNudge._evaluate_context(
            [{"metrics": {"overall_score": 0.8}, "content": "y" * 150}]
        )
        assert score == pytest.approx((0.8 + 0.5) / 2)


class TestPersistNudge:
    """_persist_nudge: contrato con cognition_sync y errores internos."""

    def test_persist_llama_a_add_lesson(self) -> None:
        nudge = _make_nudge()
        nudge._cognition.add_lesson.return_value = SimpleNamespace(id="L-1")
        contexto = [
            {
                "domain": "kernel",
                "tags": ["mutacion", "ratchet"],
                "content": "Contenido suficientemente largo para entrar en el resumen",
            }
        ]
        resultado = nudge._persist_nudge(contexto, 0.9)

        assert resultado["id"] == "L-1"
        assert resultado["score"] == pytest.approx(0.9)
        assert resultado["domain"] == "nudge.auto"
        assert resultado["context_items"] == 1

        kwargs = nudge._cognition.add_lesson.call_args.kwargs
        assert kwargs["domain"] == "nudge.auto"
        assert set(kwargs["tags"]) >= {"mutacion", "ratchet", "nudge", "auto-persist"}
        assert kwargs["metrics"]["nudge_score"] == pytest.approx(0.9)
        assert kwargs["metrics"]["context_items"] == 1
        assert "Auto-nudge (score: 0.90)" in kwargs["content"]
        assert "kernel" in kwargs["content"]

    def test_contexto_vacio_usa_placeholder_y_id_desconocido(self) -> None:
        nudge = _make_nudge()
        nudge._cognition.add_lesson.return_value = None
        resultado = nudge._persist_nudge([], 0.5)

        assert resultado["id"] == "unknown"
        kwargs = nudge._cognition.add_lesson.call_args.kwargs
        assert "No specific context" in kwargs["content"]
        assert "general" in kwargs["content"]

    def test_fallo_de_cognicion_se_atrapa(self) -> None:
        nudge = _make_nudge()
        nudge._cognition.add_lesson.side_effect = RuntimeError("cognition rota")
        resultado = nudge._persist_nudge([{"content": "x" * 40}], 0.7)
        assert resultado["error"] == "cognition rota"
        assert nudge.get_stats()["errors"] == 1

    def test_clean_old_nudges_es_placeholder(self) -> None:
        assert _make_nudge()._clean_old_nudges() == 0


class TestTickTolerancia:
    """tick(): cada fase fallida se registra y no rompe el loop."""

    def test_fallo_de_evaluacion_no_propaga(self) -> None:
        nudge = _make_nudge(interval=0)
        with (
            patch.object(nudge, "_collect_context", return_value=[{"a": 1}]),
            patch.object(nudge, "_evaluate_context", side_effect=ValueError("mal")),
        ):
            assert nudge.tick(force=True) is None
        assert nudge.get_stats()["errors"] == 1

    def test_fallo_de_persist_no_propaga(self) -> None:
        nudge = _make_nudge(interval=0)
        nudge._cognition.add_lesson.side_effect = RuntimeError("rota")
        with (
            patch.object(nudge, "_collect_context", return_value=[{"a": 1}]),
            patch.object(nudge, "_evaluate_context", return_value=0.9),
        ):
            resultado = nudge.tick(force=True)
        assert isinstance(resultado, dict)
        assert "error" in resultado
        assert nudge.get_stats()["errors"] == 1

    def test_tick_persiste_contexto_valioso(self) -> None:
        nudge = _make_nudge(interval=3600)
        nudge._cognition.add_lesson.return_value = SimpleNamespace(id="L-9")
        with patch.object(
            nudge,
            "_collect_context",
            return_value=[
                {"domain": "kernel", "content": "z" * 150, "metrics": {"overall_score": 0.9}}
            ],
        ):
            resultado = nudge.tick(force=True)
        assert resultado["id"] == "L-9"
        assert nudge.get_stats()["nudges_created"] == 1
        # el intervalo queda marcado: el siguiente tick no reintenta
        with patch.object(nudge, "_collect_context", return_value=[{"a": 1}]):
            assert nudge.tick() is None
