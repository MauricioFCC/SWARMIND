"""
C.A.S.E. response evaluator.

Evaluates agent responses against the C.A.S.E. framework dimensions:

- **Clarify**  – Does the response seek to understand the problem?
- **Architect** – Does it propose a structured solution?
- **Solve**    – Does it provide concrete implementation steps?
- **Evaluate** – Does it reflect on trade-offs, risks, or alternatives?

Each dimension returns a score (0.0 – 1.0) and qualitative feedback.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — keyword markers for each C.A.S.E. dimension
# ---------------------------------------------------------------------------

_CLARIFY_MARKERS: List[str] = [
    # Questions and exploration
    "what do you mean",
    "could you clarify",
    "let me understand",
    "let me confirm",
    "i need more context",
    "can you elaborate",
    "what is the goal",
    "what problem",
    "what are the requirements",
    "asking questions",
    "let me break this down",
    "what is the expected outcome",
    "clarify",
    "stakeholder",
    "requirements gathering",
    "define the problem",
    "scope",
    "what if",
    "who is",
    "when does",
    "why is",
]

_ARCHITECT_MARKERS: List[str] = [
    # Structure and design
    "architecture",
    "design",
    "component",
    "module",
    "layer",
    "interface",
    "abstraction",
    "pattern",
    "schema",
    "model",
    "structure",
    "pipeline",
    "flow",
    "diagram",
    "service",
    "api",
    "endpoint",
    "contract",
    "protocol",
    "i propose",
    "my approach",
    "the system will",
    "high-level",
    "component diagram",
    "data flow",
    "class hierarchy",
    "separation of concerns",
    "dependency injection",
    "hexagonal",
    "ports and adapters",
]

_SOLVE_MARKERS: List[str] = [
    # Implementation and action
    "implement",
    "code",
    "function",
    "class",
    "method",
    "write",
    "fix",
    "refactor",
    "test",
    "debug",
    "deploy",
    "config",
    "install",
    "setup",
    "migrate",
    "optimize",
    "here is the code",
    "let me implement",
    "steps to",
    "first",
    "second",
    "finally",
    "example",
    "snippet",
    "pull request",
    "commit",
    "build",
    "compile",
    "execute",
    "run",
    "verify",
    "validate",
]

_EVALUATE_MARKERS: List[str] = [
    # Reflection and critique
    "trade-off",
    "tradeoff",
    "risk",
    "limitation",
    "downside",
    "alternative",
    "compare",
    "benchmark",
    "metric",
    "performance",
    "scalability",
    "security",
    "maintainability",
    "complexity",
    "cost",
    "pros and cons",
    "however",
    "but",
    "on the other hand",
    "i recommend",
    "assessment",
    "review",
    "audit",
    "consider",
    "edge case",
    "failure mode",
    "lesson learned",
    "retrospective",
    "monitor",
    "alert",
    "testing strategy",
    "coverage",
    "quality gate",
    "improvement",
]


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class CASEValuation:
    """Score and feedback for a single C.A.S.E. dimension."""

    dimension: str
    score: float  # 0.0 – 1.0
    feedback: str
    matched_terms: List[str] = field(default_factory=list)
    term_count: int = 0
    total_markers: int = 0


@dataclass
class FullEvaluation:
    """Aggregated evaluation across all four C.A.S.E. dimensions."""

    clarify: CASEValuation
    architect: CASEValuation
    solve: CASEValuation
    evaluate: CASEValuation
    overall: float  # average of the four scores

    def to_dict(self) -> Dict[str, any]:
        """To dict."""
        return {
            "clarify": {
                "score": self.clarify.score,
                "feedback": self.clarify.feedback,
                "matched_terms": self.clarify.matched_terms,
            },
            "architect": {
                "score": self.architect.score,
                "feedback": self.architect.feedback,
                "matched_terms": self.architect.matched_terms,
            },
            "solve": {
                "score": self.solve.score,
                "feedback": self.solve.feedback,
                "matched_terms": self.solve.matched_terms,
            },
            "evaluate": {
                "score": self.evaluate.score,
                "feedback": self.evaluate.feedback,
                "matched_terms": self.evaluate.matched_terms,
            },
            "overall": self.overall,
        }


# ---------------------------------------------------------------------------
# CASEEvaluator
# ---------------------------------------------------------------------------


class CASEEvaluator:
    """
    Keyword & heuristic-based C.A.S.E. evaluator.

    Scores each dimension by counting how many of the predefined marker terms
    appear in the response text, then normalising to [0, 1].
    """

    def __init__(self) -> None:
        """Inicializa la instancia de la clase."""
        self._clarify_markers = _CLARIFY_MARKERS
        self._architect_markers = _ARCHITECT_MARKERS
        self._solve_markers = _SOLVE_MARKERS
        self._evaluate_markers = _EVALUATE_MARKERS

    # ------------------------------------------------------------------
    # Per-dimension evaluation
    # ------------------------------------------------------------------

    def evaluate_clarify(self, response: str) -> CASEValuation:
        """
        Evaluate how well the response clarifies / explores the problem.

        Returns:
            CASEValuation with score, feedback, and matched terms.
        """
        return self._eval_dimension(response, "clarify", self._clarify_markers)

    def evaluate_architect(self, response: str) -> CASEValuation:
        """
        Evaluate how well the response proposes structured architecture.

        Returns:
            CASEValuation with score, feedback, and matched terms.
        """
        return self._eval_dimension(
            response, "architect", self._architect_markers
        )

    def evaluate_solve(self, response: str) -> CASEValuation:
        """
        Evaluate how concretely the response provides implementation steps.

        Returns:
            CASEValuation with score, feedback, and matched terms.
        """
        return self._eval_dimension(response, "solve", self._solve_markers)

    def evaluate_evaluate(self, response: str) -> CASEValuation:
        """
        Evaluate how thoroughly the response reflects on trade-offs / risks.

        Returns:
            CASEValuation with score, feedback, and matched terms.
        """
        return self._eval_dimension(
            response, "evaluate", self._evaluate_markers
        )

    # ------------------------------------------------------------------
    # Full evaluation
    # ------------------------------------------------------------------

    def evaluate_full(self, response: str) -> FullEvaluation:
        """
        Run all four C.A.S.E. evaluations and return the aggregate.

        Args:
            response: The agent's response text.

        Returns:
            A ``FullEvaluation`` with per-dimension and overall scores.
        """
        clarify = self.evaluate_clarify(response)
        architect = self.evaluate_architect(response)
        solve = self.evaluate_solve(response)
        evaluate = self.evaluate_evaluate(response)

        overall = (clarify.score + architect.score + solve.score + evaluate.score) / 4.0

        logger.info(
            "C.A.S.E. evaluation — clarify=%.2f, architect=%.2f, "
            "solve=%.2f, evaluate=%.2f, overall=%.2f",
            clarify.score,
            architect.score,
            solve.score,
            evaluate.score,
            overall,
        )

        return FullEvaluation(
            clarify=clarify,
            architect=architect,
            solve=solve,
            evaluate=evaluate,
            overall=overall,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _eval_dimension(
        self,
        response: str,
        dimension: str,
        markers: List[str],
    ) -> CASEValuation:
        text_lower = response.lower()
        matched = [
            term for term in markers if term in text_lower
        ]
        matched_count = len(matched)

        # Score: ratio of matched to total markers, clamped to [0, 1]
        total = len(markers)
        score = min(matched_count / max(total, 1), 1.0)

        # Generate qualitative feedback
        feedback = self._dimension_feedback(dimension, score, matched_count)

        return CASEValuation(
            dimension=dimension,
            score=round(score, 4),
            feedback=feedback,
            matched_terms=matched[:10],  # keep top 10 for readability
            term_count=matched_count,
            total_markers=total,
        )

    @staticmethod
    def _dimension_feedback(
        dimension: str, score: float, matched: int
    ) -> str:
        if score >= 0.50:
            return (
                f"Strong {dimension} dimension ({matched} markers matched). "
                f"The response thoroughly addresses this area."
            )
        if score >= 0.20:
            return (
                f"Moderate {dimension} dimension ({matched} markers matched). "
                f"Consider strengthening this area with more explicit language."
            )
        return (
            f"Weak {dimension} dimension ({matched} markers matched). "
            f"The response lacks {dimension}-related content."
        )
