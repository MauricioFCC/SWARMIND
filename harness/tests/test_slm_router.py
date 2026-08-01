"""Tests para SlmRouter — SLM-first workers (ADR-0034, Idea 4).

Cubre: decisión determinista, whitelist SLM-friendly, escalación por confianza,
stats, fallback a frontier y preservación de planning en frontier.
"""

import pytest

from harness.orchestrator.slm_router import SlmRouter


class TestDecide:
    """Decisión de ruta slm|frontier."""

    def test_whitelisted_task_goes_slm(self):
        r = SlmRouter()
        assert r.decide("extraction", difficulty=1) == "slm"

    def test_reasoning_task_goes_frontier(self):
        r = SlmRouter()
        assert r.decide("planning", difficulty=3) == "frontier"

    def test_hard_difficulty_goes_frontier_even_if_whitelisted(self):
        r = SlmRouter(max_slm_difficulty=2)
        assert r.decide("classification", difficulty=4) == "frontier"

    def test_deterministic(self):
        r = SlmRouter()
        assert r.decide("extraction", 1) == r.decide("extraction", 1)

    def test_unknown_task_goes_frontier(self):
        r = SlmRouter()
        assert r.decide("unknown_weird_task", difficulty=1) == "frontier"


class TestExecute:
    """Ejecución con escalación por confianza."""

    def test_slm_executed_when_confident(self):
        calls = {"slm": 0, "frontier": 0}

        def slm_backend(payload):
            calls["slm"] += 1
            return {"result": "ok", "confidence": 0.95}

        def frontier_backend(payload):
            calls["frontier"] += 1
            return {"result": "ok", "confidence": 1.0}

        r = SlmRouter(slm_backend=slm_backend, frontier_backend=frontier_backend,
                      confidence_threshold=0.85)
        out = r.execute("extraction", 1, {"text": "x"})
        assert out["route"] == "slm"
        assert calls["slm"] == 1
        assert calls["frontier"] == 0

    def test_escalates_when_low_confidence(self):
        calls = {"slm": 0, "frontier": 0}

        def slm_backend(payload):
            calls["slm"] += 1
            return {"result": "mal", "confidence": 0.4}

        def frontier_backend(payload):
            calls["frontier"] += 1
            return {"result": "bien", "confidence": 1.0}

        r = SlmRouter(slm_backend=slm_backend, frontier_backend=frontier_backend,
                      confidence_threshold=0.85)
        out = r.execute("extraction", 1, {"text": "x"})
        assert out["route"] == "frontier"
        assert out["escalated"] is True
        assert calls["slm"] == 1
        assert calls["frontier"] == 1

    def test_frontier_route_skips_slm(self):
        calls = {"slm": 0, "frontier": 0}

        def slm_backend(payload):
            calls["slm"] += 1
            return {"confidence": 1.0}

        def frontier_backend(payload):
            calls["frontier"] += 1
            return {"result": "plan"}

        r = SlmRouter(slm_backend=slm_backend, frontier_backend=frontier_backend)
        out = r.execute("planning", 3, {"text": "x"})
        assert out["route"] == "frontier"
        assert calls["slm"] == 0
        assert calls["frontier"] == 1

    def test_missing_slm_backend_falls_back_to_frontier(self):
        calls = {"frontier": 0}

        def frontier_backend(payload):
            calls["frontier"] += 1
            return {"result": "ok", "confidence": 1.0}

        r = SlmRouter(slm_backend=None, frontier_backend=frontier_backend)
        out = r.execute("extraction", 1, {"text": "x"})
        assert out["route"] == "frontier"
        assert calls["frontier"] == 1


class TestStats:
    """Estadísticas de tráfico."""

    def test_stats_tracking(self):
        calls = {"slm": 0, "frontier": 0}

        def slm_backend(payload):
            calls["slm"] += 1
            return {"confidence": 0.9}

        def frontier_backend(payload):
            calls["frontier"] += 1
            return {"confidence": 1.0}

        r = SlmRouter(slm_backend=slm_backend, frontier_backend=frontier_backend)
        r.execute("extraction", 1, {})
        r.execute("extraction", 1, {})
        r.execute("planning", 3, {})
        s = r.stats()
        assert s["slm_requests"] == 2
        assert s["frontier_requests"] == 1
        assert s["escalations"] == 0
        assert s["slm_ratio"] == pytest.approx(2 / 3)

    def test_escalation_tracked(self):
        calls = {"slm": 0, "frontier": 0}

        def slm_backend(payload):
            calls["slm"] += 1
            return {"confidence": 0.2}

        def frontier_backend(payload):
            calls["frontier"] += 1
            return {"confidence": 1.0}

        r = SlmRouter(slm_backend=slm_backend, frontier_backend=frontier_backend)
        r.execute("extraction", 1, {})
        s = r.stats()
        assert s["escalations"] == 1
        assert s["slm_requests"] == 1
