"""Tests del feedback scorer (Item 1 — memoria-optimality).

Cubre los contratos 1-6 de docs/specs/memory-optimality.md: escritura de
``skill_effectiveness``/``agent_performance`` (colecciones de valor) tras el
hook post-run ``AgentDispatcher.record_skill_outcome``, con DI de vector
store. Usa el fixture ``mem_store`` (backend RAM, sin ``lancedb``) para no
tocar la memoria central real.
"""

from __future__ import annotations

import json

from harness.common import fallback_embedding
from harness.evolve_loop.feedback_scorer import (
    ROW_EMBED_DIM,
    run_report,
    score_outcome,
)

COLL_AGENT = "agent_performance"
COLL_SKILL = "skill_effectiveness"


def _rows(store, coll: str) -> list[dict]:
    """Cuenta filas de una coleccion via search con embedding de consulta."""
    vec = fallback_embedding("consulta", dim=ROW_EMBED_DIM)
    return store.search(coll, vec, top_k=50)


class TestScoreOutcome:
    def test_writes_both_collections(self, mem_store) -> None:
        """Con skill_name y agent_role escribe en AMBAS colecciones de valor."""
        ok = score_outcome(
            mem_store, "skill-x", success=True, agent_role="builder",
            metrics={"latency_ms": 120},
        )
        assert ok is True
        assert len(_rows(mem_store, COLL_AGENT)) >= 1
        assert len(_rows(mem_store, COLL_SKILL)) >= 1

    def test_skill_only_when_no_agent_role(self, mem_store) -> None:
        """Sin agent_role solo escribe skill_effectiveness (no performance)."""
        score_outcome(mem_store, "skill-y", success=False)
        assert len(_rows(mem_store, COLL_SKILL)) >= 1
        assert len(_rows(mem_store, COLL_AGENT)) == 0

    def test_noop_when_store_none(self) -> None:
        """store=None => no-op que devuelve False sin lanzar (contrato 1)."""
        assert score_outcome(None, "skill-z", success=True) is False

    def test_degrading_soft_when_store_raises(self) -> None:
        """Si el store lanza, NO propaga: devuelve False (contrato 4)."""

        class _Broken:
            def list_collections(self):
                raise RuntimeError("boom")

            def create_collection(self, *_a, **_k):
                raise RuntimeError("boom")

        assert score_outcome(_Broken(), "skill-w", success=True) is False

    def test_row_fields(self, mem_store) -> None:
        """La fila carry agent_role, success, ts y metrics serializables."""
        score_outcome(
            mem_store, "skill-f", success=True, agent_role="tester",
            metrics={"n": 1},
        )
        meta = _rows(mem_store, COLL_AGENT)[0]["metadata"]
        if isinstance(meta, str):
            meta = json.loads(meta)
        assert meta["agent_role"] == "tester"
        assert meta["success"] is True
        assert meta["ts"]  # ISO-8601 no vacio


class TestRunReport:
    def test_run_report_counts_rows(self, mem_store) -> None:
        """run_report cuenta filas por coleccion de valor (Item 2)."""
        score_outcome(mem_store, "skill-r", success=True, agent_role="dev")
        report = run_report(mem_store)
        assert report[COLL_AGENT] >= 1
        assert report[COLL_SKILL] >= 1


class TestDispatcherIntegration:
    def test_record_skill_outcome_writes_value_collections(self, mem_store) -> None:
        """End-to-end (contrato 6): record_skill_outcome puebla AMBAS."""
        from harness.orchestrator.agent_dispatcher import AgentDispatcher

        dispatcher = AgentDispatcher(vector_store=mem_store)
        dispatcher.record_skill_outcome(
            "skill-int", success=True, agent_role="builder"
        )
        assert len(_rows(mem_store, COLL_SKILL)) >= 1
        assert len(_rows(mem_store, COLL_AGENT)) >= 1

    def test_record_skill_outcome_backward_compatible(self, mem_store) -> None:
        """Sin agent_role (firma vieja) sigue funcionando y escribe skill."""
        from harness.orchestrator.agent_dispatcher import AgentDispatcher

        dispatcher = AgentDispatcher(vector_store=mem_store)
        dispatcher.record_skill_outcome("skill-bc", success=False)
        assert len(_rows(mem_store, COLL_SKILL)) >= 1
