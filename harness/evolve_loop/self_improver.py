"""
Self-improvement loop orchestrator.

Runs iterative rounds of skill improvement using the C.A.S.E. evaluator
and logs lessons to the cognition store.  Designed to support the ASI-Evolve
loop (Learn → Design → Experiment → Analyze).
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from harness.evolve_loop.cognition_sync import CognitionLesson, CognitionSync
from harness.evolve_loop.evaluator import CASEEvaluator, FullEvaluation

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class ImprovementRound:
    """Records the result of a single improvement round."""

    round_number: int
    skill_name: str
    input_response: str
    output_response: str
    evaluation: FullEvaluation
    score_delta: float  # improvement over previous round
    lesson: Optional[CognitionLesson] = None
    timestamp: str = ""

    def __post_init__(self) -> None:
        """Post init."""
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


@dataclass
class SkillImprovementStatus:
    """Aggregate status for a skill being improved."""

    skill_name: str
    total_rounds: int
    best_score: float
    current_score: float
    last_round_timestamp: str
    snapshot_history: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# SelfImprover
# ---------------------------------------------------------------------------


class SelfImprover:
    """
    Orchestrates iterative improvement cycles over skills.

    Typical usage::

        improver = SelfImprover()
        improver.run_round("quant-developer", rounds=3)
        status = improver.get_status()
        improver.promote_best_snapshot("quant-developer")
    """

    def __init__(
        self,
        evaluator: Optional[CASEEvaluator] = None,
        cognition: Optional[CognitionSync] = None,
    ) -> None:
        """
        Args:
            evaluator: A ``CASEEvaluator`` instance.  Defaults to a new one.
            cognition: A ``CognitionSync`` instance.  Defaults to a new one.
        """
        self.evaluator = evaluator or CASEEvaluator()
        self.cognition = cognition or CognitionSync()

        # Internal state
        self._rounds: Dict[str, List[ImprovementRound]] = {}
        self._current_snapshots: Dict[str, str] = {}  # skill -> snapshot_id
        self._best_scores: Dict[str, float] = {}
        self._promoted: Dict[str, bool] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_round(
        self,
        skill_name: str,
        rounds: int = 1,
        input_text: Optional[str] = None,
    ) -> List[ImprovementRound]:
        """
        Run N rounds of improvement for a given skill.

        Each round:
        1. Evaluates a current "response" (either the provided input or a
           generated placeholder) using the C.A.S.E. framework.
        2. Logs the evaluation as a cognition lesson.
        3. Tracks score progression.

        Args:
            skill_name: The name of the skill to improve.
            rounds: Number of improvement rounds to run (default 1).
            input_text: Optional base response to evaluate.  If omitted,
                a templated placeholder is used.

        Returns:
            List of ``ImprovementRound`` records, one per round.
        """
        if skill_name not in self._rounds:
            self._rounds[skill_name] = []
            self._best_scores[skill_name] = 0.0

        completed: List[ImprovementRound] = []

        for r in range(1, rounds + 1):
            round_num = len(self._rounds[skill_name]) + 1

            # Determine input for this round
            current_input = input_text or self._generate_input_placeholder(
                skill_name, round_num
            )

            # --- Step 1: Evaluate with C.A.S.E. ---
            evaluation = self.evaluator.evaluate_full(current_input)

            # --- Step 2: Compute delta ---
            previous_score = self._best_scores.get(skill_name, 0.0)
            delta = evaluation.overall - previous_score

            # --- Step 3: Build "improved" response (simulated) ---
            improved = self._simulate_improvement(
                current_input, evaluation, skill_name
            )

            # --- Step 4: Store as cognition lesson ---
            lesson = self._store_lesson(skill_name, round_num, evaluation)

            # --- Step 5: Record round ---
            improvement_round = ImprovementRound(
                round_number=round_num,
                skill_name=skill_name,
                input_response=current_input,
                output_response=improved,
                evaluation=evaluation,
                score_delta=round(delta, 4),
                lesson=lesson,
            )

            self._rounds[skill_name].append(improvement_round)

            # Update best score
            if evaluation.overall > self._best_scores.get(skill_name, 0.0):
                self._best_scores[skill_name] = evaluation.overall
                snapshot_id = self._take_snapshot(
                    skill_name, improved, evaluation
                )
                self._current_snapshots[skill_name] = snapshot_id

            completed.append(improvement_round)

            logger.info(
                "Round %d for '%s' — score=%.2f, delta=%.2f, lesson=%s",
                round_num,
                skill_name,
                evaluation.overall,
                delta,
                lesson.id if lesson else "none",
            )

        return completed

    def promote_best_snapshot(self, skill_name: str) -> Optional[str]:
        """
        Promote the best-performing snapshot for a skill.

        In a full implementation this would replace the live skill definition
        with the snapshot.  Currently it logs the promotion and returns the
        snapshot ID.

        Args:
            skill_name: The skill whose best snapshot should be promoted.

        Returns:
            The snapshot ID, or ``None`` if no snapshot exists.
        """
        snapshot_id = self._current_snapshots.get(skill_name)
        if not snapshot_id:
            logger.warning(
                "No snapshot available for '%s'; cannot promote.", skill_name
            )
            return None

        best = self._best_scores.get(skill_name, 0.0)

        # In production this would:
        #   1. Load the snapshot from the store
        #   2. Replace the live skill definition
        #   3. Run validation tests
        #   4. Deploy the updated skill

        self._promoted[skill_name] = True
        logger.info(
            "Promoted snapshot '%s' for skill '%s' (score=%.2f).",
            snapshot_id,
            skill_name,
            best,
        )

        self.cognition.add_lesson(
            title=f"Snapshot promoted: {skill_name}",
            content=(
                f"Promoted snapshot {snapshot_id} for skill '{skill_name}' "
                f"with best C.A.S.E. score {best:.2f}."
            ),
            domain="self_improvement",
            tags=["promotion", skill_name, "snapshot"],
            metrics={"best_score": best, "snapshot_id": snapshot_id},
        )

        return snapshot_id

    def get_status(self) -> List[SkillImprovementStatus]:
        """
        Return current improvement status for all tracked skills.

        Returns:
            List of ``SkillImprovementStatus`` dataclass instances.
        """
        statuses: List[SkillImprovementStatus] = []

        for skill_name, rounds in self._rounds.items():
            if not rounds:
                continue

            last_round = rounds[-1]
            statuses.append(
                SkillImprovementStatus(
                    skill_name=skill_name,
                    total_rounds=len(rounds),
                    best_score=self._best_scores.get(skill_name, 0.0),
                    current_score=last_round.evaluation.overall,
                    last_round_timestamp=last_round.timestamp,
                    snapshot_history=list(self._current_snapshots.keys()),
                )
            )

        return statuses

    def get_round_history(
        self, skill_name: str
    ) -> List[ImprovementRound]:
        """
        Get the full round history for a skill.

        Args:
            skill_name: The skill name.

        Returns:
            List of ``ImprovementRound`` records, or empty list.
        """
        return self._rounds.get(skill_name, [])

    def has_been_promoted(self, skill_name: str) -> bool:
        """Check whether a skill's snapshot has been promoted."""
        return self._promoted.get(skill_name, False)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_input_placeholder(
        self, skill_name: str, round_num: int
    ) -> str:
        """Generate a realistic placeholder response for a skill."""
        return (
            f"As a {skill_name}, my response for round {round_num} is to "
            f"analyze the problem, propose a structured solution, implement "
            f"the necessary changes, and evaluate the trade-offs involved. "
            f"I will consider alternative approaches, assess risks, and "
            f"document lessons learned for future reference."
        )

    def _simulate_improvement(
        self, input_text: str, evaluation: FullEvaluation, skill_name: str
    ) -> str:
        """
        Simulate an improved response based on evaluation feedback.

        In production this would call an LLM or apply a transformation rule.
        Here we simply append a reflection paragraph.
        """
        improvements: List[str] = []
        if evaluation.clarify.score < 0.3:
            improvements.append(
                "I will clarify the requirements and constraints more thoroughly."
            )
        if evaluation.architect.score < 0.3:
            improvements.append(
                "I will design a clearer architecture with defined components."
            )
        if evaluation.solve.score < 0.3:
            improvements.append(
                "I will provide concrete implementation steps and code examples."
            )
        if evaluation.evaluate.score < 0.3:
            improvements.append(
                "I will evaluate trade-offs, risks, and alternative approaches."
            )

        suffix = " ".join(improvements) if improvements else (
            "I have addressed the C.A.S.E. dimensions and improved the response."
        )

        return f"{input_text}\n\n[Improved round]: {suffix}"

    def _store_lesson(
        self, skill_name: str, round_num: int, evaluation: FullEvaluation
    ) -> CognitionLesson:
        """Persist the round result as a cognition lesson."""
        domain = f"self_improvement.{skill_name}"
        tags = [
            "self_improvement",
            skill_name,
            f"round_{round_num}",
        ]

        # Determine the weakest dimension
        scores = {
            "clarify": evaluation.clarify.score,
            "architect": evaluation.architect.score,
            "solve": evaluation.solve.score,
            "evaluate": evaluation.evaluate.score,
        }
        weakest = min(scores, key=scores.get)
        strongest = max(scores, key=scores.get)

        content = (
            f"C.A.S.E. evaluation for {skill_name} round {round_num}.\n"
            f"Overall score: {evaluation.overall:.2f}\n"
            f"Strongest dimension: {strongest} ({scores[strongest]:.2f})\n"
            f"Weakest dimension: {weakest} ({scores[weakest]:.2f})\n"
        )

        lesson = self.cognition.add_lesson(
            title=f"Evolve round {round_num}: {skill_name}",
            content=content,
            domain=domain,
            tags=tags,
            metrics={
                "round": round_num,
                "overall_score": evaluation.overall,
                **{f"case_{k}": v for k, v in scores.items()},
            },
        )
        return lesson

    def _take_snapshot(
        self,
        skill_name: str,
        response: str,
        evaluation: FullEvaluation,
    ) -> str:
        """
        Create a snapshot of the current best state.

        Returns:
            A unique snapshot identifier.
        """
        snapshot_id = f"snap_{skill_name}_{uuid.uuid4().hex[:8]}"

        self.cognition.add_lesson(
            title=f"Snapshot: {skill_name} ({evaluation.overall:.2f})",
            content=response,
            domain="self_improvement.snapshots",
            tags=["snapshot", skill_name, "best"],
            metrics={
                "snapshot_id": snapshot_id,
                "score": evaluation.overall,
            },
        )

        logger.info(
            "Snapshot '%s' taken for '%s' (score=%.2f).",
            snapshot_id,
            skill_name,
            evaluation.overall,
        )

        return snapshot_id
