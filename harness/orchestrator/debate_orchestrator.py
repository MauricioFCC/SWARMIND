"""
Debate Orchestrator — Multi-agent debate with consolidation strategies.

Based on ADR-0001 P2 recommendations (Princeton NLP 2026): multi-agent
debate adds ~2.1 points of accuracy over single-agent baselines.

Supports three strategies:
  - CONSENSUS: All agents answer independently, then vote.
  - CRITIQUE:  Primary agent answers, secondary agent critiques, refinement.
  - DELIBERATION: Sequential debate where each agent builds on the previous.

Usage:
    orch = DebateOrchestrator()
    result = orch.debate(
        task="Design an API architecture",
        agents=["builder", "scientist", "guardian"],
        strategy=DebateStrategy.CONSENSUS,
    )
    final = orch.consolidate(result)
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Strategy Enum
# ---------------------------------------------------------------------------


class DebateStrategy(str, Enum):
    """Available debate strategies for multi-agent coordination."""

    CONSENSUS = "consensus"
    """All agents produce answers independently, then vote on the best one."""

    CRITIQUE = "critique"
    """Primary agent produces an answer, secondary agent critiques, refinement."""

    DELIBERATION = "deliberation"
    """Sequential debate where each agent builds upon the previous output."""


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class DebateRound:
    """A single round of debate with agent outputs and feedback."""

    round_num: int
    agent_outputs: Dict[str, str] = field(default_factory=dict)
    critique_feedback: Dict[str, str] = field(default_factory=dict)
    synthesis: str = ""
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "round_num": self.round_num,
            "agent_outputs": dict(self.agent_outputs),
            "critique_feedback": dict(self.critique_feedback),
            "synthesis": self.synthesis,
            "confidence": self.confidence,
        }


@dataclass
class DebateResult:
    """The final result of a complete debate session."""

    session_id: str
    task: str
    strategy: DebateStrategy
    rounds: List[DebateRound] = field(default_factory=list)
    final_answer: str = ""
    confidence: float = 0.0
    agent_agreement: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "task": self.task,
            "strategy": self.strategy.value if isinstance(self.strategy, DebateStrategy) else self.strategy,
            "rounds": [r.to_dict() for r in self.rounds],
            "final_answer": self.final_answer,
            "confidence": self.confidence,
            "agent_agreement": self.agent_agreement,
            "metadata": dict(self.metadata),
        }


# ---------------------------------------------------------------------------
# Dispatch function type
# ---------------------------------------------------------------------------

DispatchFn = Callable[[str, str, Dict[str, Any]], str]
"""Signature: (agent_name, task, context) -> agent_response_text.

The context dict contains at least:
  - strategy: current DebateStrategy value
  - round: current round number (1-based)
  - previous_outputs: dict of agent_name -> previous round output
  - feedback: dict of agent_name -> critique feedback (if any)
"""


# ---------------------------------------------------------------------------
# DebateOrchestrator
# ---------------------------------------------------------------------------


class DebateOrchestrator:
    """
    Orchestrates multi-agent debate for complex tasks.

    The orchestrator uses a **dispatch function** to obtain agent responses.
    This indirection makes testing trivial (pass a mock) and keeps the
    orchestrator decoupled from LLM invocation.

    Each round of debate is logged via AgentBus for full traceability.

    Attributes:
        _store:   LanceVectorStore instance (optional).
        _bus:     AgentBus for inter-agent communication logging.
    """

    def __init__(self, vector_store: Optional[Any] = None) -> None:
        """
        Args:
            vector_store: Optional LanceVectorStore for persistence.
        """
        from harness.orchestrator.agent_bus import AgentBus

        self._store = vector_store
        self._bus = AgentBus(vector_store=vector_store)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def debate(
        self,
        task: str,
        agents: List[str],
        strategy: DebateStrategy = DebateStrategy.CONSENSUS,
        max_rounds: int = 2,
        dispatch_fn: Optional[DispatchFn] = None,
    ) -> DebateResult:
        """
        Execute a multi-agent debate and return the consolidated result.

        Args:
            task: The task or question to debate.
            agents: List of agent names (e.g. ``["builder", "scientist"]``).
            strategy: The debate strategy to use.
            max_rounds: Maximum number of debate rounds (strategy-dependent).
            dispatch_fn: Optional callable to obtain agent responses.
                If omitted, a simple fallback is used (for testing).

        Returns:
            A DebateResult with the final answer and full debate history.

        Raises:
            ValueError: If the task is empty or fewer than 2 agents provided.
        """
        # --- Validation ---
        if not task or not task.strip():
            raise ValueError("Debate task cannot be empty.")
        if not agents or len(agents) < 2:
            raise ValueError("Debate requires at least 2 agents.")

        effective_agents = list(agents)
        effective_fn = dispatch_fn or self._default_dispatch

        session_id = str(uuid.uuid4())[:8]

        # Log debate start via AgentBus
        self._log_debate_start(session_id, task, strategy, effective_agents)

        # --- Strategy dispatch ---
        if strategy == DebateStrategy.CONSENSUS:
            result = self._execute_consensus(
                task, effective_agents, max_rounds, effective_fn, session_id,
            )
        elif strategy == DebateStrategy.CRITIQUE:
            result = self._execute_critique(
                task, effective_agents, max_rounds, effective_fn, session_id,
            )
        elif strategy == DebateStrategy.DELIBERATION:
            result = self._execute_deliberation(
                task, effective_agents, max_rounds, effective_fn, session_id,
            )
        else:
            raise ValueError(f"Unknown debate strategy: {strategy}")

        # Log debate result
        self._log_debate_result(result)

        return result

    @staticmethod
    def consolidate(result: DebateResult) -> str:
        """
        Extract the final consolidated answer from a debate result.

        Args:
            result: A completed DebateResult.

        Returns:
            The final answer as a string.
        """
        return result.final_answer

    # ------------------------------------------------------------------
    # Strategy: CONSENSUS
    # ------------------------------------------------------------------

    def _execute_consensus(
        self,
        task: str,
        agents: List[str],
        max_rounds: int,
        dispatch_fn: DispatchFn,
        session_id: str,
    ) -> DebateResult:
        """All agents produce answers independently, then vote (conference)."""
        rounds: List[DebateRound] = []
        all_outputs: Dict[str, str] = {}
        all_feedback: Dict[str, str] = {}

        # --- Round 1: Independent answers ---
        round1 = DebateRound(round_num=1)
        for agent in agents:
            context = {
                "strategy": DebateStrategy.CONSENSUS.value,
                "round": 1,
                "previous_outputs": dict(all_outputs),
                "feedback": {},
                "phase": "independent_answer",
            }
            output = dispatch_fn(agent, task, context)
            round1.agent_outputs[agent] = output
            all_outputs[agent] = output

            # Log via AgentBus
            self._log_agent_message(session_id, agent, task, output, round_num=1)

        # Round 1 confidence: how much do initial answers agree?
        round1.confidence = self._compute_agreement(round1.agent_outputs)
        round1.synthesis = self._synthesize_answers(round1.agent_outputs)
        rounds.append(round1)

        # --- Round 2 (if max_rounds > 1): Conference / Voting ---
        if max_rounds >= 2:
            round2 = DebateRound(round_num=2)

            # Each agent reviews all other answers
            for agent in agents:
                other_outputs = {
                    a: out for a, out in all_outputs.items() if a != agent
                }
                conference_context = {
                    "strategy": DebateStrategy.CONSENSUS.value,
                    "round": 2,
                    "previous_outputs": dict(all_outputs),
                    "feedback": {},
                    "phase": "conference_vote",
                    "other_answers": other_outputs,
                }
                vote = dispatch_fn(agent, task, conference_context)
                round2.critique_feedback[agent] = vote

            # Determine winner by similarity clustering
            winner_output, winner_agreement = self._majority_winner(all_outputs)

            round2.synthesis = (
                f"Consenso tras conferencia: {winner_output[:200]}"
            )
            round2.confidence = winner_agreement
            rounds.append(round2)

        else:
            # Single round — pick best by agreement directly
            winner_output, winner_agreement = self._majority_winner(all_outputs)

        # Determine final answer
        if max_rounds >= 2:
            final_answer = rounds[-1].synthesis
        else:
            final_answer = winner_output

        # Overall confidence: average of round confidences
        overall_confidence = (
            sum(r.confidence for r in rounds) / len(rounds) if rounds else 0.0
        )

        # Agent agreement: how aligned were agents in the final round
        final_agreement = rounds[-1].confidence if rounds else 0.0

        return DebateResult(
            session_id=session_id,
            task=task,
            strategy=DebateStrategy.CONSENSUS,
            rounds=rounds,
            final_answer=final_answer,
            confidence=overall_confidence,
            agent_agreement=final_agreement,
            metadata={
                "num_agents": len(agents),
                "num_rounds": len(rounds),
                "agents": list(agents),
                "strategy": DebateStrategy.CONSENSUS.value,
            },
        )

    # ------------------------------------------------------------------
    # Strategy: CRITIQUE
    # ------------------------------------------------------------------

    def _execute_critique(
        self,
        task: str,
        agents: List[str],
        max_rounds: int,
        dispatch_fn: DispatchFn,
        session_id: str,
    ) -> DebateResult:
        """Primary agent produces an answer, secondary agent critiques, then refinement."""
        rounds: List[DebateRound] = []
        primary = agents[0]
        critic = agents[1] if len(agents) > 1 else agents[0]
        refiners = agents[2:] if len(agents) > 2 else []

        # --- Round 1: Primary agent produces answer ---
        round1 = DebateRound(round_num=1)
        context_r1 = {
            "strategy": DebateStrategy.CRITIQUE.value,
            "round": 1,
            "previous_outputs": {},
            "feedback": {},
            "phase": "primary_answer",
        }
        primary_output = dispatch_fn(primary, task, context_r1)
        round1.agent_outputs[primary] = primary_output
        self._log_agent_message(session_id, primary, task, primary_output, round_num=1, phase="primary")

        outputs_so_far: Dict[str, str] = {primary: primary_output}
        feedback_so_far: Dict[str, str] = {}

        # Round 1 confidence: baseline
        round1.confidence = 0.5
        rounds.append(round1)

        # --- Round 2: Critique ---
        if max_rounds >= 2:
            round2 = DebateRound(round_num=2)
            critique_context = {
                "strategy": DebateStrategy.CRITIQUE.value,
                "round": 2,
                "previous_outputs": dict(outputs_so_far),
                "feedback": {},
                "phase": "critique",
                "answer_to_review": primary_output,
            }
            critique = dispatch_fn(critic, task, critique_context)
            round2.critique_feedback[critic] = critique
            feedback_so_far[critic] = critique
            self._log_agent_message(session_id, critic, task, critique, round_num=2, phase="critique")
            round2.confidence = 0.4  # critique phase — lower confidence
            rounds.append(round2)

        # --- Round 3 (optional): Refinement by primary ---
        has_refinement = max_rounds >= 3 or refiners
        if has_refinement:
            refiner = refiners[0] if refiners else primary
            round3 = DebateRound(round_num=3)
            refine_context = {
                "strategy": DebateStrategy.CRITIQUE.value,
                "round": 3,
                "previous_outputs": dict(outputs_so_far),
                "feedback": dict(feedback_so_far),
                "phase": "refinement",
                "original_answer": primary_output,
                "critique": feedback_so_far.get(critic, ""),
            }
            refined = dispatch_fn(refiner, task, refine_context)
            round3.agent_outputs[refiner] = refined
            outputs_so_far[refiner] = refined
            self._log_agent_message(session_id, refiner, task, refined, round_num=3, phase="refinement")

            # Check if critique was addressed (agreement improvement)
            addressed = self._critique_addressed(primary_output, refined, feedback_so_far.get(critic, ""))
            round3.confidence = 0.7 if addressed else 0.4
            round3.synthesis = refined
            rounds.append(round3)

        # Final answer: best available
        if has_refinement:
            final_answer = rounds[-1].agent_outputs.get(
                list(rounds[-1].agent_outputs.keys())[0],
                rounds[-1].synthesis or primary_output,
            )
        else:
            final_answer = primary_output

        overall_confidence = (
            sum(r.confidence for r in rounds) / len(rounds) if rounds else 0.0
        )

        return DebateResult(
            session_id=session_id,
            task=task,
            strategy=DebateStrategy.CRITIQUE,
            rounds=rounds,
            final_answer=final_answer,
            confidence=overall_confidence,
            agent_agreement=overall_confidence,
            metadata={
                "num_agents": len(agents),
                "num_rounds": len(rounds),
                "agents": list(agents),
                "primary_agent": primary,
                "critic_agent": critic,
                "strategy": DebateStrategy.CRITIQUE.value,
            },
        )

    # ------------------------------------------------------------------
    # Strategy: DELIBERATION
    # ------------------------------------------------------------------

    def _execute_deliberation(
        self,
        task: str,
        agents: List[str],
        max_rounds: int,
        dispatch_fn: DispatchFn,
        session_id: str,
    ) -> DebateResult:
        """Sequential debate where each agent builds on the previous output."""
        rounds: List[DebateRound] = []
        outputs_so_far: Dict[str, str] = {}
        num_agents = len(agents)

        for i, agent in enumerate(agents):
            if i >= max_rounds:
                break

            round_i = DebateRound(round_num=i + 1)
            context = {
                "strategy": DebateStrategy.DELIBERATION.value,
                "round": i + 1,
                "previous_outputs": dict(outputs_so_far),
                "feedback": {},
                "phase": "deliberation",
                "agent_index": i,
                "total_agents": num_agents,
            }

            output = dispatch_fn(agent, task, context)
            round_i.agent_outputs[agent] = output
            outputs_so_far[agent] = output
            self._log_agent_message(session_id, agent, task, output, round_num=i + 1, phase="deliberation")

            # Confidence increases as more agents contribute
            progress = (i + 1) / num_agents
            round_i.confidence = 0.3 + (progress * 0.5)
            round_i.synthesis = output

            rounds.append(round_i)

        # Final round's output is the synthesized answer
        final_round = rounds[-1] if rounds else DebateRound(round_num=0)
        final_answer = final_round.synthesis or (
            list(final_round.agent_outputs.values())[0]
            if final_round.agent_outputs else ""
        )

        overall_confidence = (
            sum(r.confidence for r in rounds) / len(rounds) if rounds else 0.0
        )

        # Agreement: how consistent were the outputs across rounds
        texts = [r.synthesis or next(iter(r.agent_outputs.values()), "") for r in rounds]
        pairwise_similarities = []
        for i in range(len(texts)):
            for j in range(i + 1, len(texts)):
                pairwise_similarities.append(
                    self._text_similarity(texts[i], texts[j])
                )
        agreement = (
            sum(pairwise_similarities) / len(pairwise_similarities)
            if pairwise_similarities else 0.0
        )

        return DebateResult(
            session_id=session_id,
            task=task,
            strategy=DebateStrategy.DELIBERATION,
            rounds=rounds,
            final_answer=final_answer,
            confidence=overall_confidence,
            agent_agreement=agreement,
            metadata={
                "num_agents": len(agents),
                "num_rounds": len(rounds),
                "agents": list(agents),
                "strategy": DebateStrategy.DELIBERATION.value,
            },
        )

    # ------------------------------------------------------------------
    # Aggregation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _text_similarity(a: str, b: str) -> float:
        """Compute word-overlap similarity between two strings (0.0–1.0)."""
        if not a or not b:
            return 0.0
        words_a = set(a.lower().split())
        words_b = set(b.lower().split())
        if not words_a or not words_b:
            return 0.0
        intersection = words_a & words_b
        union = words_a | words_b
        return len(intersection) / len(union)

    def _compute_agreement(self, outputs: Dict[str, str]) -> float:
        """
        Compute pairwise agreement among agent outputs.

        Returns:
            Average pairwise similarity (0.0 to 1.0).
        """
        texts = list(outputs.values())
        if len(texts) < 2:
            return 0.0
        similarities = []
        for i in range(len(texts)):
            for j in range(i + 1, len(texts)):
                similarities.append(self._text_similarity(texts[i], texts[j]))
        return sum(similarities) / len(similarities) if similarities else 0.0

    def _majority_winner(
        self,
        outputs: Dict[str, str],
    ) -> tuple:
        """
        Find the answer with the highest support via clustering.

        Returns:
            Tuple of (winning_text, agreement_score). If there is a tie,
            the first answer in the largest cluster is returned.
        """
        if not outputs:
            return ("", 0.0)

        agents = list(outputs.keys())
        texts = list(outputs.values())

        # If only one agent, return its output
        if len(agents) == 1:
            return (texts[0], 1.0)

        # Cluster by similarity: for each text, count how many others are similar (>0.3)
        threshold = 0.3
        best_idx = 0
        best_count = 0

        for i, text in enumerate(texts):
            count = 1  # count self
            for j, other in enumerate(texts):
                if i != j and self._text_similarity(text, other) >= threshold:
                    count += 1
            if count > best_count:
                best_count = count
                best_idx = i

        agreement = best_count / len(texts)
        return (texts[best_idx], agreement)

    @staticmethod
    def _synthesize_answers(outputs: Dict[str, str]) -> str:
        """
        Produce a simple synthesis of all agent outputs.

        Takes the longest output as a heuristic for most detailed answer.
        """
        if not outputs:
            return ""
        # Pick the longest output as the most detailed
        best = max(outputs.items(), key=lambda x: len(x[1]))
        return (
            f"[Síntesis de {len(outputs)} agente(s)]\n"
            f"Respuesta principal ({best[0]}):\n{best[1]}"
        )

    @staticmethod
    def _critique_addressed(
        original: str,
        refined: str,
        critique: str,
    ) -> bool:
        """
        Heuristic check if critique was addressed in the refinement.

        Returns True if the refined text differs meaningfully from the
        original (suggesting the critique was taken into account).
        """
        if not original or not refined:
            return False
        # If refinement is longer or has different content, likely addressed
        if len(refined) > len(original) * 1.1:
            return True
        # Check word-level difference
        orig_words = set(original.lower().split())
        ref_words = set(refined.lower().split())
        new_words = ref_words - orig_words
        return len(new_words) > 2

    # ------------------------------------------------------------------
    # Default dispatch (fallback when no dispatch_fn provided)
    # ------------------------------------------------------------------

    @staticmethod
    def _default_dispatch(agent: str, task: str, context: Dict[str, Any]) -> str:
        """
        Default dispatch function that returns a generic response.

        This is used when no ``dispatch_fn`` is provided to the ``debate()``
        method. It produces a templated response based on the agent name.
        """
        phase = context.get("phase", "unknown")
        templates = {
            "builder": (
                f"[Builder] Análisis de implementación para: {task[:80]}.\n"
                f"Propongo una solución modular con alta cohesión y bajo "
                f"acoplamiento, priorizando rendimiento y mantenibilidad."
            ),
            "scientist": (
                f"[Scientist] Análisis de investigación para: {task[:80]}.\n"
                f"Revisión de literatura y mejores prácticas. "
                f"Recomiendo evaluar múltiples alternativas antes de decidir."
            ),
            "guardian": (
                f"[Guardian] Revisión de calidad para: {task[:80]}.\n"
                f"Verificando cobertura de tests, seguridad OWASP, "
                f"y documentación completa."
            ),
            "coordinator": (
                f"[Coordinator] Facilitación del debate para: {task[:80]}.\n"
                f"Coordinando perspectivas de todos los agentes para "
                f"consolidar una decisión final."
            ),
        }

        base = templates.get(agent, f"[{agent}] Respondiendo a: {task[:80]}.")
        if phase == "conference_vote":
            other = context.get("other_answers", {})
            other_summary = "; ".join(
                f"{a}: {o[:60]}..." for a, o in other.items()
            )
            base += f"\nVoto tras revisar otros: {other_summary}"
        elif phase == "critique":
            answer = context.get("answer_to_review", "")
            base += (
                f"\nCrítica a la respuesta propuesta:\n"
                f"- Puntos fuertes: enfoque estructurado.\n"
                f"- Áreas de mejora: considerar más casos borde, "
                f"agregar métricas de validación."
            )
        elif phase == "refinement":
            critique_text = context.get("critique", "")
            base += (
                f"\nRefinamiento incorporando crítica:\n"
                f"{critique_text[:100]}... "
                f"Mejoras aplicadas al diseño original."
            )

        return base

    # ------------------------------------------------------------------
    # AgentBus logging
    # ------------------------------------------------------------------

    def _log_debate_start(
        self,
        session_id: str,
        task: str,
        strategy: DebateStrategy,
        agents: List[str],
    ) -> None:
        """Log the start of a debate session to AgentBus."""
        try:
            self._bus.post_message(
                channel=f"#debate-{session_id}",
                from_agent="@coordinator",
                to_agent="@all",
                message=(
                    f"🎯 **DEBATE INICIADO**\n"
                    f"Tarea: {task}\n"
                    f"Estrategia: {strategy.value}\n"
                    f"Agentes: {', '.join(agents)}"
                ),
                message_type="notification",
            )
        except Exception as exc:
            logger.debug("Debate start log non-fatal: %s", exc)

    def _log_agent_message(
        self,
        session_id: str,
        agent: str,
        task: str,
        output: str,
        round_num: int,
        phase: str = "contribution",
    ) -> None:
        """Log an individual agent's contribution to AgentBus."""
        try:
            self._bus.post_message(
                channel=f"#debate-{session_id}",
                from_agent=f"@{agent}",
                to_agent="@coordinator",
                message=(
                    f"Ronda {round_num} [{phase}]:\n"
                    f"{output[:500]}"
                ),
                message_type="response",
            )
        except Exception as exc:
            logger.debug("Agent message log non-fatal: %s", exc)

    def _log_debate_result(self, result: DebateResult) -> None:
        """Log the final debate result to AgentBus."""
        try:
            self._bus.post_message(
                channel=f"#debate-{result.session_id}",
                from_agent="@coordinator",
                to_agent="@all",
                message=(
                    f"✅ **DEBATE COMPLETADO**\n"
                    f"Estrategia: {result.strategy.value}\n"
                    f"Rondas: {len(result.rounds)}\n"
                    f"Confianza: {result.confidence:.2f}\n"
                    f"Acuerdo entre agentes: {result.agent_agreement:.2f}\n"
                    f"Respuesta final: {result.final_answer[:300]}"
                ),
                message_type="notification",
            )
        except Exception as exc:
            logger.debug("Debate result log non-fatal: %s", exc)
