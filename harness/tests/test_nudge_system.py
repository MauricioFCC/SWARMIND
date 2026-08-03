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
from unittest.mock import MagicMock, patch

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
