"""Tests para SpeculativeToolExecutor — PASTE-lite (ADR-0034, Idea 6).

Cubre: PatternLearner aprende patrones, predict top-k, dry_run no ejecuta,
políticas de seguridad (nada side-effect sin registro), confirm lossless.
"""

import pytest

from harness.orchestrator.speculative_tool_exec import (
    FORBIDDEN_TOOLS,
    PatternLearner,
    SpeculativeToolExecutor,
)


class TestPatternLearner:
    """Aprendizaje de patrones (tool_actual -> tool_siguiente)."""

    def test_learns_frequencies(self):
        pl = PatternLearner()
        pl.observe("read_file", "search_code")
        pl.observe("read_file", "search_code")
        pl.observe("read_file", "edit_file")
        preds = pl.predict("read_file")
        # top-1 = search_code (2 ocurrencias)
        assert preds[0][0] == "search_code"
        assert preds[0][1] == pytest.approx(2 / 3)

    def test_predict_unknown_tool(self):
        pl = PatternLearner()
        assert pl.predict("never_seen") == []

    def test_top_k_limits(self):
        pl = PatternLearner()
        for nxt in ["a", "b", "c", "d"]:
            pl.observe("t", nxt)
        preds = pl.predict("t", k=2)
        assert len(preds) == 2

    def test_observe_none_next(self):
        pl = PatternLearner()
        pl.observe("final_tool", None)  # No debe romper.
        assert pl.predict("final_tool") == []


class TestEligibility:
    """Políticas de seguridad para tools especulables."""

    def test_default_nothing_eligible(self):
        ex = SpeculativeToolExecutor()
        assert ex.is_eligible("read_file") is False

    def test_registered_tool_eligible(self):
        ex = SpeculativeToolExecutor(eligible={"read_file", "search"})
        assert ex.is_eligible("read_file") is True

    def test_forbidden_tools_never_eligible(self):
        ex = SpeculativeToolExecutor(eligible={"write_file", "delete", "deploy"})
        for tool in ["write_file", "delete", "deploy"]:
            assert ex.is_eligible(tool) is False

    def test_forbidden_tools_constant(self):
        assert "write" in FORBIDDEN_TOOLS
        assert "delete" in FORBIDDEN_TOOLS
        assert "execute" in FORBIDDEN_TOOLS
        assert "send" in FORBIDDEN_TOOLS
        assert "deploy" in FORBIDDEN_TOOLS
        assert "update" in FORBIDDEN_TOOLS


class TestSpeculativeExecution:
    """Ejecución especulativa con dry-run y aislamiento."""

    def test_dry_run_does_not_execute(self):
        executed = []

        def executor(tool, params=None):
            executed.append(tool)
            return f"result-{tool}"

        ex = SpeculativeToolExecutor(eligible={"search"}, dry_run=True)
        ex.run_speculative("read_file", executor)
        assert executed == []

    def test_non_dry_run_executes_eligible(self):
        executed = []

        def executor(tool, params=None):
            executed.append(tool)
            return f"result-{tool}"

        learner = PatternLearner()
        learner.observe("read_file", "search")
        ex = SpeculativeToolExecutor(learner=learner, eligible={"search"},
                                     dry_run=False)
        results = ex.run_speculative("read_file", executor)
        assert "search" in executed
        assert "search" in results

    def test_speculative_results_isolated_until_confirm(self):
        executed = []

        def executor(tool, params=None):
            executed.append(tool)
            return f"result-{tool}"

        learner = PatternLearner()
        learner.observe("read_file", "search")
        ex = SpeculativeToolExecutor(learner=learner, eligible={"search"},
                                     dry_run=False)
        results = ex.run_speculative("read_file", executor)
        # Los resultados especulativos viven en un store provisional aislado.
        assert "search" in results
        assert ex._pending.get("search") == "result-search"
        # confirm() entrega UNA sola vez (pop): la segunda llamada es None.
        assert ex.confirm("search") == "result-search"
        assert ex.confirm("search") is None

    def test_confirm_returns_cached_result(self):
        executed = []

        def executor(tool, params=None):
            executed.append(tool)
            return f"result-{tool}"

        learner = PatternLearner()
        learner.observe("read_file", "search")
        ex = SpeculativeToolExecutor(learner=learner, eligible={"search"},
                                     dry_run=False)
        ex.run_speculative("read_file", executor)
        assert ex.confirm("search") == "result-search"

    def test_confirm_after_no_speculation_returns_none(self):
        ex = SpeculativeToolExecutor(eligible={"search"}, dry_run=False)
        assert ex.confirm("search") is None

    def test_predict_uses_learner(self):
        pl = PatternLearner()
        pl.observe("read_file", "search")
        pl.observe("read_file", "search")
        ex = SpeculativeToolExecutor(learner=pl, eligible={"search"})
        preds = ex.predict("read_file")
        assert preds[0][0] == "search"

    def test_stats(self):
        ex = SpeculativeToolExecutor(eligible={"search"}, dry_run=False)

        def executor(tool, params=None):
            return "x"

        ex.run_speculative("read_file", executor)
        s = ex.stats()
        assert s["speculative_runs"] >= 1
        assert "hits" in s
