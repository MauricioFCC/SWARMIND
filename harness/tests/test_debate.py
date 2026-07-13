"""
Tests for DebateOrchestrator — multi-agent debate with consolidation strategies.

Verifies:
  - Three strategy implementations (CONSENSUS, CRITIQUE, DELIBERATION)
  - Data structures (DebateRound, DebateResult, DebateStrategy enum)
  - Integration with TaskPlanner (debate template)
  - Integration with TaskOrchestrator (debate routing)
  - Edge cases (empty task, 2 agents, 3 agents, confidence)
"""

from __future__ import annotations

import json
import pytest
from dataclasses import asdict
from enum import Enum
from typing import Any, Dict, List

from harness.orchestrator.debate_orchestrator import (
    DebateOrchestrator,
    DebateResult,
    DebateRound,
    DebateStrategy,
    DispatchFn,
)
from harness.orchestrator.task_planner import (
    TaskPlanner,
    SUBTASK_TEMPLATES,
)
from harness.orchestrator.task_orchestrator import TaskOrchestrator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def orchestrator():
    """DebateOrchestrator instance without vector store (memory-only)."""
    return DebateOrchestrator(vector_store=None)


@pytest.fixture
def mock_dispatch() -> DispatchFn:
    """Factory that returns a deterministic dispatch function."""
    def _dispatch(agent: str, task: str, context: Dict[str, Any]) -> str:
        responses = {
            "builder": (
                "Propongo implementar usando Rust con Axum. "
                "La arquitectura debe ser modular con endpoints REST claros."
            ),
            "scientist": (
                "Recomiendo evaluar opciones: Rust vs Go. "
                "Estudios muestran que Rust tiene mejor rendimiento en I/O."
            ),
            "guardian": (
                "Debemos asegurar calidad con tests unitarios, "
                "seguridad OWASP y documentación completa."
            ),
            "coordinator": (
                "Síntesis: usar Rust con Axum, con tests y documentación. "
                "La decisión final considera todas las perspectivas."
            ),
        }
        return responses.get(
            agent,
            f"[{agent}] Análisis para: {task[:60]}...",
        )
    return _dispatch


@pytest.fixture
def task_orch():
    """TaskOrchestrator instance (memory-only)."""
    return TaskOrchestrator()


# ---------------------------------------------------------------------------
# Strategy Enum
# ---------------------------------------------------------------------------


class TestDebateStrategy:
    """Verify the DebateStrategy enum."""

    def test_strategy_values(self):
        assert DebateStrategy.CONSENSUS.value == "consensus"
        assert DebateStrategy.CRITIQUE.value == "critique"
        assert DebateStrategy.DELIBERATION.value == "deliberation"

    def test_strategy_members(self):
        names = {m.name for m in DebateStrategy}
        assert names == {"CONSENSUS", "CRITIQUE", "DELIBERATION"}

    def test_strategy_from_string(self):
        assert DebateStrategy("consensus") == DebateStrategy.CONSENSUS
        assert DebateStrategy("critique") == DebateStrategy.CRITIQUE
        assert DebateStrategy("deliberation") == DebateStrategy.DELIBERATION

    def test_strategy_is_enum(self):
        assert issubclass(DebateStrategy, str)
        assert issubclass(DebateStrategy, Enum)  # noqa: F821


# ---------------------------------------------------------------------------
# DebateRound
# ---------------------------------------------------------------------------


class TestDebateRound:
    """Verify the DebateRound dataclass."""

    def test_default_creation(self):
        r = DebateRound(round_num=1)
        assert r.round_num == 1
        assert r.agent_outputs == {}
        assert r.critique_feedback == {}
        assert r.synthesis == ""
        assert r.confidence == 0.0

    def test_to_dict(self):
        r = DebateRound(
            round_num=2,
            agent_outputs={"builder": "code", "scientist": "research"},
            critique_feedback={"guardian": "needs tests"},
            synthesis="final output",
            confidence=0.85,
        )
        d = r.to_dict()
        assert d["round_num"] == 2
        assert d["agent_outputs"]["builder"] == "code"
        assert d["critique_feedback"]["guardian"] == "needs tests"
        assert d["synthesis"] == "final output"
        assert d["confidence"] == 0.85


# ---------------------------------------------------------------------------
# DebateResult
# ---------------------------------------------------------------------------


class TestDebateResult:
    """Verify the DebateResult dataclass and serialization."""

    def test_default_creation(self):
        result = DebateResult(
            session_id="test-123",
            task="Design API",
            strategy=DebateStrategy.CONSENSUS,
        )
        assert result.session_id == "test-123"
        assert result.task == "Design API"
        assert result.strategy == DebateStrategy.CONSENSUS
        assert result.rounds == []
        assert result.final_answer == ""
        assert result.confidence == 0.0
        assert result.agent_agreement == 0.0

    def test_serialization(self):
        result = DebateResult(
            session_id="ser-test",
            task="Test task",
            strategy=DebateStrategy.CRITIQUE,
            rounds=[
                DebateRound(round_num=1, agent_outputs={"a1": "out1"}, confidence=0.5),
            ],
            final_answer="out1",
            confidence=0.5,
            agent_agreement=0.8,
            metadata={"agents": ["a1", "a2"]},
        )
        d = result.to_dict()
        assert d["session_id"] == "ser-test"
        assert d["strategy"] == "critique"
        assert len(d["rounds"]) == 1
        assert d["final_answer"] == "out1"
        assert d["confidence"] == 0.5
        assert d["agent_agreement"] == 0.8
        assert d["metadata"]["agents"] == ["a1", "a2"]

    def test_round_metadata_in_result(self):
        """DebateRound metadata is preserved in the result's round list."""
        r1 = DebateRound(
            round_num=1,
            agent_outputs={"builder": "answer A", "scientist": "answer B"},
            critique_feedback={},
            synthesis="",
            confidence=0.6,
        )
        result = DebateResult(
            session_id="meta-test",
            task="Meta test",
            strategy=DebateStrategy.CONSENSUS,
            rounds=[r1],
            final_answer="answer A",
            confidence=0.6,
            agent_agreement=0.5,
            metadata={"num_agents": 2, "agents": ["builder", "scientist"]},
        )
        assert result.metadata["num_agents"] == 2
        assert result.rounds[0].confidence == 0.6
        assert result.rounds[0].agent_outputs["builder"] == "answer A"

    def test_json_serializable(self):
        """Result dict should be JSON-serializable."""
        result = DebateResult(
            session_id="json-test",
            task="JSON test",
            strategy=DebateStrategy.DELIBERATION,
            rounds=[
                DebateRound(round_num=1, agent_outputs={"a": "x"}, confidence=0.9),
            ],
            final_answer="x",
            confidence=0.9,
            agent_agreement=1.0,
        )
        json_str = json.dumps(result.to_dict())
        parsed = json.loads(json_str)
        assert parsed["session_id"] == "json-test"
        assert parsed["strategy"] == "deliberation"
        assert len(parsed["rounds"]) == 1


# ---------------------------------------------------------------------------
# DebateOrchestrator — CONSENSUS strategy
# ---------------------------------------------------------------------------


class TestConsensusStrategy:
    """Verify the CONSENSUS debate strategy."""

    def test_consensus_basic(self, orchestrator, mock_dispatch):
        """All agents produce answers, then vote."""
        result = orchestrator.debate(
            task="Design API architecture",
            agents=["builder", "scientist", "guardian"],
            strategy=DebateStrategy.CONSENSUS,
            dispatch_fn=mock_dispatch,
        )
        assert result.strategy == DebateStrategy.CONSENSUS
        assert len(result.rounds) >= 1
        assert len(result.final_answer) > 0
        assert result.confidence >= 0.0
        assert result.agent_agreement >= 0.0

    def test_consensus_with_2_agents(self, orchestrator, mock_dispatch):
        """Consensus works with only 2 agents."""
        result = orchestrator.debate(
            task="Evaluate tech stack",
            agents=["builder", "scientist"],
            strategy=DebateStrategy.CONSENSUS,
            dispatch_fn=mock_dispatch,
        )
        assert len(result.rounds) >= 1
        assert result.metadata["num_agents"] == 2
        assert result.final_answer != ""

    def test_consensus_with_3_agents(self, orchestrator, mock_dispatch):
        """Consensus works with 3 agents (standard case)."""
        result = orchestrator.debate(
            task="Design system architecture",
            agents=["builder", "scientist", "guardian"],
            strategy=DebateStrategy.CONSENSUS,
            dispatch_fn=mock_dispatch,
        )
        assert result.metadata["num_agents"] == 3
        assert len(result.rounds) >= 1
        assert result.final_answer != ""

    def test_consensus_confidence_high(self, orchestrator):
        """When agents agree closely, confidence should be high."""
        def agreeing_dispatch(agent, task, context):
            return "Usar Rust con Axum para la API."

        result = orchestrator.debate(
            task="Pick framework",
            agents=["builder", "scientist", "guardian"],
            strategy=DebateStrategy.CONSENSUS,
            max_rounds=1,
            dispatch_fn=agreeing_dispatch,
        )
        # All agents said the same thing → high agreement
        assert result.agent_agreement >= 0.9
        assert result.confidence >= 0.9

    def test_consensus_confidence_low(self, orchestrator):
        """When agents disagree, confidence should be low."""
        def disagreeing_dispatch(agent, task, context):
            responses = {
                "builder": "Usar Rust con Axum.",
                "scientist": "Usar Go con Gin.",
                "guardian": "Usar Python con FastAPI.",
            }
            return responses.get(agent, "Opción neutral.")

        result = orchestrator.debate(
            task="Pick framework",
            agents=["builder", "scientist", "guardian"],
            strategy=DebateStrategy.CONSENSUS,
            max_rounds=1,
            dispatch_fn=disagreeing_dispatch,
        )
        # All different → low agreement (< 0.3 threshold)
        assert result.agent_agreement < 0.5

    def test_consensus_max_rounds(self, orchestrator, mock_dispatch):
        """max_rounds=1 produces only 1 round (no conference phase)."""
        result = orchestrator.debate(
            task="Quick decision",
            agents=["builder", "guardian"],
            strategy=DebateStrategy.CONSENSUS,
            max_rounds=1,
            dispatch_fn=mock_dispatch,
        )
        assert len(result.rounds) == 1

    def test_consensus_max_rounds_2(self, orchestrator, mock_dispatch):
        """max_rounds=2 adds a conference/voting round."""
        result = orchestrator.debate(
            task="Decision with review",
            agents=["builder", "guardian"],
            strategy=DebateStrategy.CONSENSUS,
            max_rounds=2,
            dispatch_fn=mock_dispatch,
        )
        assert len(result.rounds) == 2


# ---------------------------------------------------------------------------
# DebateOrchestrator — CRITIQUE strategy
# ---------------------------------------------------------------------------


class TestCritiqueStrategy:
    """Verify the CRITIQUE debate strategy."""

    def test_critique_basic(self, orchestrator, mock_dispatch):
        """Primary agent answers, secondary critiques."""
        result = orchestrator.debate(
            task="Design authentication system",
            agents=["builder", "guardian"],
            strategy=DebateStrategy.CRITIQUE,
            dispatch_fn=mock_dispatch,
        )
        assert result.strategy == DebateStrategy.CRITIQUE
        assert len(result.rounds) >= 2
        assert result.final_answer != ""

    def test_critique_with_2_agents(self, orchestrator, mock_dispatch):
        """Critique works with exactly 2 agents (primary + critic)."""
        result = orchestrator.debate(
            task="Review architecture proposal",
            agents=["builder", "guardian"],
            strategy=DebateStrategy.CRITIQUE,
            max_rounds=2,
            dispatch_fn=mock_dispatch,
        )
        assert result.metadata["num_agents"] == 2
        assert result.metadata["primary_agent"] == "builder"
        assert result.metadata["critic_agent"] == "guardian"

    def test_critique_refinement(self, orchestrator, mock_dispatch):
        """With max_rounds=3, primary agent refines after critique."""
        result = orchestrator.debate(
            task="Design DB schema",
            agents=["builder", "guardian"],
            strategy=DebateStrategy.CRITIQUE,
            max_rounds=3,
            dispatch_fn=mock_dispatch,
        )
        assert len(result.rounds) == 3


# ---------------------------------------------------------------------------
# DebateOrchestrator — DELIBERATION strategy
# ---------------------------------------------------------------------------


class TestDeliberationStrategy:
    """Verify the DELIBERATION debate strategy."""

    def test_deliberation_basic(self, orchestrator, mock_dispatch):
        """Sequential debate where each agent builds on previous."""
        result = orchestrator.debate(
            task="Design system architecture",
            agents=["builder", "scientist", "coordinator"],
            strategy=DebateStrategy.DELIBERATION,
            dispatch_fn=mock_dispatch,
        )
        assert result.strategy == DebateStrategy.DELIBERATION
        assert len(result.rounds) >= 2
        assert result.final_answer != ""

    def test_deliberation_with_3_agents(self, orchestrator, mock_dispatch):
        """Deliberation with 3 agents produces 3 rounds."""
        result = orchestrator.debate(
            task="Design deployment pipeline",
            agents=["builder", "scientist", "guardian"],
            strategy=DebateStrategy.DELIBERATION,
            max_rounds=3,
            dispatch_fn=mock_dispatch,
        )
        assert result.metadata["num_agents"] == 3
        assert len(result.rounds) == 3
        # Each round should have a different agent's output
        agents_in_rounds = set()
        for r in result.rounds:
            agents_in_rounds.update(r.agent_outputs.keys())
        assert len(agents_in_rounds) == 3


# ---------------------------------------------------------------------------
# Edge cases & validation
# ---------------------------------------------------------------------------


class TestDebateEdgeCases:
    """Verify edge case handling."""

    def test_empty_task_raises(self, orchestrator, mock_dispatch):
        """Empty task should raise ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            orchestrator.debate(
                task="",
                agents=["builder", "guardian"],
                dispatch_fn=mock_dispatch,
            )

    def test_single_agent_raises(self, orchestrator, mock_dispatch):
        """Single agent should raise ValueError (need at least 2)."""
        with pytest.raises(ValueError, match="at least 2 agents"):
            orchestrator.debate(
                task="Design API",
                agents=["builder"],
                dispatch_fn=mock_dispatch,
            )

    def test_default_dispatch_works(self, orchestrator):
        """Without dispatch_fn, the default fallback should work."""
        result = orchestrator.debate(
            task="Evaluate options",
            agents=["builder", "scientist"],
            strategy=DebateStrategy.CONSENSUS,
            max_rounds=1,
        )
        assert result.final_answer != ""
        assert result.confidence >= 0.0

    def test_strategy_enum_value(self):
        """All strategy enum values are valid strings."""
        assert DebateStrategy.CONSENSUS in DebateStrategy
        assert DebateStrategy.CRITIQUE in DebateStrategy
        assert DebateStrategy.DELIBERATION in DebateStrategy


# ---------------------------------------------------------------------------
# Consolidate
# ---------------------------------------------------------------------------


class TestConsolidate:
    """Verify the consolidate() helper."""

    def test_consolidate_returns_final_answer(self, orchestrator, mock_dispatch):
        """consolidate() should return the final_answer from the result."""
        result = orchestrator.debate(
            task="Design API",
            agents=["builder", "guardian"],
            strategy=DebateStrategy.CONSENSUS,
            max_rounds=1,
            dispatch_fn=mock_dispatch,
        )
        consolidated = orchestrator.consolidate(result)
        assert consolidated == result.final_answer
        assert len(consolidated) > 0

    def test_consolidate_empty_result(self, orchestrator):
        """consolidate() on an empty result returns empty string."""
        result = DebateResult(
            session_id="empty",
            task="",
            strategy=DebateStrategy.CONSENSUS,
        )
        assert orchestrator.consolidate(result) == ""


# ---------------------------------------------------------------------------
# Integration with TaskPlanner
# ---------------------------------------------------------------------------


class TestDebateTemplateInPlanner:
    """Verify the debate template exists and works in TaskPlanner."""

    def test_debate_template_exists(self):
        """SUBTASK_TEMPLATES should contain a 'debate' entry."""
        assert "debate" in SUBTASK_TEMPLATES

    def test_debate_template_structure(self):
        """Debate template should have proper structure."""
        tpl = SUBTASK_TEMPLATES["debate"]
        assert "triggers" in tpl
        assert "description" in tpl
        assert "subtasks" in tpl
        assert len(tpl["subtasks"]) >= 4

    def test_debate_template_triggers(self):
        """Debate template triggers should include debate keywords."""
        tpl = SUBTASK_TEMPLATES["debate"]
        triggers = tpl["triggers"]
        assert "debate" in triggers
        assert "discutir" in triggers
        assert "consenso" in triggers
        assert "votar" in triggers
        assert "criticar" in triggers
        assert "revisar" in triggers

    def test_debate_template_subtask_agents(self):
        """Debate subtasks should involve coordinator, builder, scientist, guardian."""
        tpl = SUBTASK_TEMPLATES["debate"]
        agents = {s["agent"] for s in tpl["subtasks"]}
        assert "coordinator" in agents
        assert "builder" in agents
        assert "scientist" in agents
        assert "guardian" in agents

    def test_debate_template_detected_by_keyword(self):
        """TaskPlanner should detect 'debate' keyword and use debate template."""
        planner = TaskPlanner()
        # Use a message that ONLY matches the debate template (no other template triggers)
        plan = planner.decompose("debate para decidir el mejor enfoque tecnico")
        assert plan.template_name == "debate"

    def test_debate_template_detected_by_votar(self):
        """TaskPlanner should detect 'votar' keyword -> debate template."""
        planner = TaskPlanner()
        plan = planner.decompose("votar entre opciones de diseño de base de datos")
        assert plan.template_name == "debate"

    def test_debate_template_detected_by_revisar(self):
        """TaskPlanner should detect 'revisar' keyword -> debate template."""
        planner = TaskPlanner()
        plan = planner.decompose("revisar y discutir el enfoque de arquitectura")
        assert plan.template_name == "debate"

    def test_debate_plan_has_coordinator_first(self):
        """Debate plan's first subtask should be coordinator."""
        planner = TaskPlanner()
        plan = planner.decompose("debate para decidir el mejor camino")
        assert plan.subtasks[0].agent == "coordinator"

    def test_debate_plan_has_correct_subtasks(self):
        """Debate plan should have 5 subtasks with proper dependencies."""
        planner = TaskPlanner()
        plan = planner.decompose("debate sobre elección de framework")
        assert len(plan.subtasks) == 5
        # Level 0: coordinator (facilitate)
        # Level 1: builder, scientist, guardian (parallel)
        # Level 2: coordinator (consolidate)
        levels = plan.get_levels()
        assert len(levels) == 3
        assert levels[0][0].agent == "coordinator"
        assert {s.agent for s in levels[1]} == {"builder", "scientist", "guardian"}
        assert levels[2][0].agent == "coordinator"

    def test_debate_template_not_detected_for_normal_tasks(self):
        """Normal tasks should not use the debate template."""
        planner = TaskPlanner()
        plan = planner.decompose("implementa una API REST en Rust")
        assert plan.template_name != "debate"


# ---------------------------------------------------------------------------
# Integration with TaskOrchestrator
# ---------------------------------------------------------------------------


class TestDebateOrchestratorIntegration:
    """Verify integration between TaskOrchestrator and DebateOrchestrator."""

    def test_orchestrator_detects_debate(self, task_orch):
        """TaskOrchestrator should detect debate plan and set is_debate=True."""
        result = task_orch.process_message("debate sobre arquitectura del sistema")
        assert result.is_debate is True
        # Should have debate_agents populated
        assert len(result.debate_agents) >= 2

    def test_orchestrator_debate_agents(self, task_orch):
        """Debate plan should extract non-coordinator agents."""
        result = task_orch.process_message("debate sobre elección de stack tecnológico")
        assert len(result.debate_agents) >= 2
        assert "coordinator" not in result.debate_agents

    def test_orchestrator_no_debate_for_normal(self, task_orch):
        """Normal (non-debate) tasks should have is_debate=False."""
        result = task_orch.process_message("implementa una API REST")
        assert result.is_debate is False

    def test_orchestrator_debate_strategy_default(self, task_orch):
        """Debate plan should default to 'consensus' strategy."""
        result = task_orch.process_message("debate sobre diseño de base de datos")
        assert result.debate_strategy == "consensus"

    def test_orchestrator_run_debate(self, task_orch):
        """run_debate() should produce a valid DebateResult."""
        result = task_orch.process_message("debate sobre arquitectura de microservicios")
        debate_result = task_orch.run_debate(
            session_id=result.session_id,
            task=result.original_message,
            agents=["builder", "scientist", "guardian"],
        )
        assert debate_result is not None
        assert isinstance(debate_result, DebateResult)
        assert debate_result.final_answer != ""
        assert debate_result.confidence >= 0.0

    def test_orchestrator_run_debate_with_mock(self, task_orch, mock_dispatch):
        """run_debate() with custom dispatch function."""
        result = task_orch.process_message("debate sobre estrategia de testing")
        debate_result = task_orch.run_debate(
            session_id=result.session_id,
            task=result.original_message,
            agents=["builder", "guardian"],
            strategy="consensus",
            dispatch_fn=mock_dispatch,
        )
        assert debate_result.strategy == DebateStrategy.CONSENSUS
        assert debate_result.final_answer != ""

    def test_orchestrator_run_debate_critique(self, task_orch, mock_dispatch):
        """run_debate() with critique strategy."""
        result = task_orch.process_message("debate sobre seguridad")
        debate_result = task_orch.run_debate(
            session_id=result.session_id,
            task=result.original_message,
            agents=["builder", "guardian"],
            strategy="critique",
            dispatch_fn=mock_dispatch,
        )
        assert debate_result.strategy == DebateStrategy.CRITIQUE

    def test_orchestrator_run_debate_deliberation(self, task_orch, mock_dispatch):
        """run_debate() with deliberation strategy."""
        result = task_orch.process_message("debate sobre diseño de API")
        debate_result = task_orch.run_debate(
            session_id=result.session_id,
            task=result.original_message,
            agents=["builder", "scientist", "guardian"],
            strategy="deliberation",
            dispatch_fn=mock_dispatch,
        )
        assert debate_result.strategy == DebateStrategy.DELIBERATION

    def test_orchestrator_debate_result_has_rounds(self, task_orch, mock_dispatch):
        """Debate result from orchestrator should contain rounds."""
        result = task_orch.process_message("debate sobre optimización de queries")
        debate_result = task_orch.run_debate(
            session_id=result.session_id,
            task=result.original_message,
            agents=["builder", "scientist"],
            strategy="consensus",
            dispatch_fn=mock_dispatch,
        )
        assert len(debate_result.rounds) > 0
        # Each round should have agent outputs OR critique feedback
        for round_data in debate_result.rounds:
            has_outputs = len(round_data.agent_outputs) > 0
            has_feedback = len(round_data.critique_feedback) > 0
            assert has_outputs or has_feedback, (
                f"Round {round_data.round_num} has no outputs or feedback"
            )

    def test_orchestrator_target_agent_for_debate(self, task_orch):
        """Debate plan should target coordinator (since level 0 is coordinator)."""
        result = task_orch.process_message("debate sobre estrategia")
        assert result.target_agent == "coordinator"
