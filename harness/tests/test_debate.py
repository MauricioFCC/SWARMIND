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
from unittest.mock import MagicMock, patch

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

    @pytest.mark.slow
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

    @pytest.mark.slow
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


# ---------------------------------------------------------------------------
# Edge cases: internal methods uncovered by strategies above
# ---------------------------------------------------------------------------


class TestDebateInternalMethods:
    """Coverage tests for internal helpers of DebateOrchestrator (sin LanceDB)."""

    def _make_orchestrator(self):
        """Crea DebateOrchestrator con _bus mockeado para evitar LanceDB."""
        with patch('harness.orchestrator.agent_bus.AgentBus') as mock_bus_cls:
            mock_bus_cls.return_value = MagicMock()
            from harness.orchestrator.debate_orchestrator import DebateOrchestrator
            orch = DebateOrchestrator(vector_store=None)
            orch._bus = MagicMock()
            return orch

    def test_unknown_strategy_raises(self):
        """Estrategia desconocida debe lanzar ValueError."""
        orch = self._make_orchestrator()
        # Debido a que DebateStrategy extiende str, pasamos un string invalido
        with pytest.raises(ValueError, match="Unknown debate strategy"):
            orch.debate(
                task="test",
                agents=["builder", "scientist"],
                strategy="non_existent_strategy",  # type: ignore
                dispatch_fn=lambda a, t, c: "ok",
            )

    def test_text_similarity_empty(self):
        """_text_similarity con textos vacios retorna 0.0."""
        from harness.orchestrator.debate_orchestrator import DebateOrchestrator
        assert DebateOrchestrator._text_similarity("", "hello") == 0.0
        assert DebateOrchestrator._text_similarity("hello", "") == 0.0
        assert DebateOrchestrator._text_similarity("", "") == 0.0

    def test_text_similarity_no_words(self):
        """_text_similarity con textos sin palabras retorna 0.0."""
        from harness.orchestrator.debate_orchestrator import DebateOrchestrator
        assert DebateOrchestrator._text_similarity("   ", "hello") == 0.0
        assert DebateOrchestrator._text_similarity("hello", "   ") == 0.0
        assert DebateOrchestrator._text_similarity("   ", "   ") == 0.0

    def test_text_similarity_normal(self):
        """_text_similarity calcula Jaccard similarity correctamente."""
        from harness.orchestrator.debate_orchestrator import DebateOrchestrator
        sim = DebateOrchestrator._text_similarity("hello world", "hello world")
        assert sim == 1.0
        sim = DebateOrchestrator._text_similarity("hello world", "hello there")
        assert sim == 1.0 / 3.0  # {hello} / {hello, world, there}

    def test_compute_agreement_single(self):
        """_compute_agreement con <2 outputs retorna 0.0."""
        orch = self._make_orchestrator()
        agreement = orch._compute_agreement({"a": "only one"})
        assert agreement == 0.0

    def test_compute_agreement_normal(self):
        """_compute_agreement calcula promedio pairwise."""
        orch = self._make_orchestrator()
        agreement = orch._compute_agreement({
            "a": "hello world",
            "b": "hello world",
            "c": "hello world",
        })
        assert agreement == 1.0

    def test_majority_winner_empty(self):
        """_majority_winner con outputs vacio retorna ('', 0.0)."""
        orch = self._make_orchestrator()
        winner, agreement = orch._majority_winner({})
        assert winner == ""
        assert agreement == 0.0

    def test_majority_winner_single(self):
        """_majority_winner con un solo agente retorna su texto."""
        orch = self._make_orchestrator()
        winner, agreement = orch._majority_winner({"a": "unica respuesta"})
        assert winner == "unica respuesta"
        assert agreement == 1.0

    def test_majority_winner_multiple(self):
        """_majority_winner encuentra el texto con mas soporte."""
        orch = self._make_orchestrator()
        winner, agreement = orch._majority_winner({
            "a": "usar Rust con Axum",
            "b": "usar Rust con Axum",
            "c": "usar Python con FastAPI",
        })
        assert "Rust" in winner
        assert agreement >= 0.5

    def test_synthesize_answers_empty(self):
        """_synthesize_answers con outputs vacio retorna ''."""
        orch = self._make_orchestrator()
        result = orch._synthesize_answers({})
        assert result == ""

    def test_synthesize_answers_normal(self):
        """_synthesize_answers retorna el output mas largo."""
        orch = self._make_orchestrator()
        result = orch._synthesize_answers({
            "a": "short",
            "b": "much longer answer here",
        })
        assert "much longer" in result

    def test_critique_addressed_empty(self):
        """_critique_addressed con original/refined vacio retorna False."""
        from harness.orchestrator.debate_orchestrator import DebateOrchestrator
        assert DebateOrchestrator._critique_addressed("", "refined", "critique") is False
        assert DebateOrchestrator._critique_addressed("original", "", "critique") is False
        assert DebateOrchestrator._critique_addressed("", "", "critique") is False

    def test_critique_addressed_longer(self):
        """_critique_addressed con refined > 1.1x original retorna True."""
        from harness.orchestrator.debate_orchestrator import DebateOrchestrator
        assert DebateOrchestrator._critique_addressed(
            "short", "short and much longer content here", "make it longer"
        ) is True

    def test_critique_addressed_new_words(self):
        """_critique_addressed con nuevas palabras retorna True."""
        from harness.orchestrator.debate_orchestrator import DebateOrchestrator
        assert DebateOrchestrator._critique_addressed(
            "original answer here", "original answer here with new improvements",
            "add improvements"
        ) is True

    def test_critique_addressed_not_addressed(self):
        """_critique_addressed cuando no hay cambios retorna False."""
        from harness.orchestrator.debate_orchestrator import DebateOrchestrator
        assert DebateOrchestrator._critique_addressed(
            "same text", "same text", "critique not addressed"
        ) is False

    def test_default_dispatch_critique_phase(self):
        """_default_dispatch con phase='critique' incluye critica."""
        from harness.orchestrator.debate_orchestrator import DebateOrchestrator
        result = DebateOrchestrator._default_dispatch(
            "builder",
            "design API",
            {"phase": "critique", "answer_to_review": "proposal"},
        )
        assert "Crítica" in result

    def test_default_dispatch_refinement_phase(self):
        """_default_dispatch con phase='refinement' incluye refinamiento."""
        from harness.orchestrator.debate_orchestrator import DebateOrchestrator
        result = DebateOrchestrator._default_dispatch(
            "builder",
            "design API",
            {"phase": "refinement", "critique": "needs more tests"},
        )
        assert "Refinamiento" in result
        assert "needs more tests" in result

    def test_default_dispatch_unknown_agent(self):
        """_default_dispatch con agente desconocido genera respuesta generica."""
        from harness.orchestrator.debate_orchestrator import DebateOrchestrator
        result = DebateOrchestrator._default_dispatch(
            "custom_agent",
            "some task",
            {"phase": "unknown"},
        )
        assert "custom_agent" in result
        assert "some task" in result

    def test_default_dispatch_conference_vote(self):
        """_default_dispatch con phase='conference_vote' incluye voto."""
        from harness.orchestrator.debate_orchestrator import DebateOrchestrator
        result = DebateOrchestrator._default_dispatch(
            "builder",
            "design API",
            {"phase": "conference_vote", "other_answers": {"a": "answer1", "b": "answer2"}},
        )
        assert "Voto" in result
        assert "answer1" in result


class TestDebateLoggingExceptions:
    """Verifica que excepciones en logging no propagan errores (sin LanceDB)."""

    def _make_orchestrator(self):
        """Crea DebateOrchestrator con _bus mockeado para evitar LanceDB."""
        with patch('harness.orchestrator.agent_bus.AgentBus') as mock_bus_cls:
            mock_bus_cls.return_value = MagicMock()
            from harness.orchestrator.debate_orchestrator import DebateOrchestrator
            orch = DebateOrchestrator(vector_store=None)
            orch._bus = MagicMock()
            orch._bus.post_message.side_effect = RuntimeError("log error simulado")
            return orch

    def test_logging_exceptions_do_not_propagate(self):
        """Excepciones en _bus.post_message no deben romper el debate."""
        orch = self._make_orchestrator()

        result = orch.debate(
            task="Design API",
            agents=["builder", "scientist"],
            strategy=DebateStrategy.CONSENSUS,
            max_rounds=1,
            dispatch_fn=lambda a, t, c: "respuesta de prueba",
        )
        assert result is not None
        assert result.final_answer != ""

    def test_logging_exceptions_critique(self):
        """Excepciones en logging con estrategia CRITIQUE."""
        orch = self._make_orchestrator()

        result = orch.debate(
            task="Test critique logging",
            agents=["builder", "guardian"],
            strategy=DebateStrategy.CRITIQUE,
            max_rounds=3,
            dispatch_fn=lambda a, t, c: "respuesta",
        )
        assert result is not None
        assert result.strategy == DebateStrategy.CRITIQUE

    def test_logging_exceptions_deliberation(self):
        """Excepciones en logging con estrategia DELIBERATION."""
        orch = self._make_orchestrator()

        result = orch.debate(
            task="Test deliberation logging",
            agents=["builder", "scientist", "guardian"],
            strategy=DebateStrategy.DELIBERATION,
            max_rounds=2,
            dispatch_fn=lambda a, t, c: "respuesta",
        )
        assert result is not None
        assert result.strategy == DebateStrategy.DELIBERATION

    def test_majority_winner_tie(self):
        """_majority_winner con empate escoge el primero del cluster mas grande."""
        orch = self._make_orchestrator()
        # Usamos palabras sin overlap para que clusters se formen correctamente
        winner, agreement = orch._majority_winner({
            "a": "rustlanguage",
            "b": "rustlanguage",
            "c": "pythonlanguage",
            "d": "pythonlanguage",
        })
        assert winner in ("rustlanguage", "pythonlanguage")
        assert agreement == 0.5
