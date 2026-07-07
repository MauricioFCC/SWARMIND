"""
Confidence Scorer — Evaluates confidence of agent outputs using heuristic signals.

KISS: Simple heuristic signals, not ML-based.
DRY: Reuses estimate_tokens() from common.py for length analysis.
Clean Code: Single Responsibility — scorer only scores.

Signals:
  - Length: output length relative to task length (very short/long → low confidence)
  - Hedging: presence of hedging/uncertainty language
  - Self-Correction: presence of self-correction patterns
  - Speed: fast generation often correlates with high confidence
  - Agreement: when multiple agents agree, confidence is higher
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from harness.common import estimate_tokens

# ---------------------------------------------------------------------------
# Confidence thresholds
# ---------------------------------------------------------------------------

CONFIDENCE_HIGH = 0.90
CONFIDENCE_MEDIUM = 0.70
CONFIDENCE_LOW = 0.40

# ---------------------------------------------------------------------------
# Language pattern constants
# ---------------------------------------------------------------------------

# Hedging language: expressions that indicate uncertainty or low confidence
_HEDGING_PATTERNS: List[str] = [
    r"\bi think\b",
    r"\bi believe\b",
    r"\bi'm not sure\b",
    r"\bi am not sure\b",
    r"\bnot entirely sure\b",
    r"\bnot 100%\b",
    r"\bnot certain\b",
    r"\bnot confident\b",
    r"\bmaybe\b",
    r"\bperhaps\b",
    r"\bpossibly\b",
    r"\bprobably\b",
    r"\bmight be\b",
    r"\bcould be\b",
    r"\bit depends\b",
    r"\bhard to say\b",
    r"\bdifficult to say\b",
    r"\bi guess\b",
    r"\bi suppose\b",
    r"\bin my opinion\b",
    r"\bnot sure if\b",
    r"\bunsure\b",
    r"\bapproximate\w*\b",
    r"\broughly\b",
    r"\bestimate\b",
    r"\bthis is just\b",
    r"\bjust a guess\b",
    r"\bnot guarantee\b",
    r"\bno guarantee\b",
    r"\btentative\b",
    r"\bconsidered\b",
    r"\bsuggest\b",
    r"\boption\b",
    r"\balternative\b",
    r"\bup to you\b",
    # Spanish hedging patterns
    r"\bquiz[áa]s\b",
    r"\btal vez\b",
    r"\bno estoy seguro\b",
    r"\bno est[aá] seguro\b",
    r"\bno estoy convencido\b",
    r"\bpuede ser\b",
    r"\bpuede que\b",
    r"\ba lo mejor\b",
    r"\bcreo que\b",
    r"\bpienso que\b",
    r"\bme parece\b",
    r"\bsupongo\b",
    r"\bprobablemente\b",
    r"\bposiblemente\b",
    r"\bseguramente\b",
    r"\btalmente\b",
    r"\bcapaz\b",
    r"\bno sé\b",
    r"\bdepende\b",
    r"\ben mi opinión\b",
    r"\bconsidero\b",
    r"\bsugiero\b",
    r"\bopción\b",
    r"\balternativa\b",
    r"\baproximadamente\b",
    r"\bcasi\b",
    r"\bcomo que\b",
    r"\bno estoy seguro de\b",
]

# Self-correction patterns: indicate the agent is revising its own output
_SELF_CORRECTION_PATTERNS: List[str] = [
    r"\bactually\b",
    r"\bon second thought\b",
    r"\blet me reconsider\b",
    r"\blet me rethink\b",
    r"\blet me revise\b",
    r"\bcorrection\b",
    r"\bscratch that\b",
    r"\bnever mind\b",
    r"\bignore that\b",
    r"\breconsider\b",
    r"\brethink\b",
    r"\brevis\w*\b",
    r"\bretract\b",
    r"\binstead\b",
    r"\bwait\b",
    r"\bhmm\b",
    r"\bhang on\b",
    r"\bhold on\b",
]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ConfidenceScore:
    """
    Result of a confidence evaluation.

    Attributes:
        score: Overall confidence score between 0.0 and 1.0.
        reasoning: Human-readable explanation of the score.
        signals: Per-signal scores (signal_name -> value).
    """

    score: float  # 0.0 to 1.0
    reasoning: str = ""
    signals: Dict[str, float] = field(default_factory=dict)

    @property
    def level(self) -> str:
        """Categorize the confidence level."""
        if self.score >= CONFIDENCE_HIGH:
            return "high"
        if self.score >= CONFIDENCE_MEDIUM:
            return "medium"
        return "low"

    @property
    def should_stop(self) -> bool:
        """If confidence is high enough, execution can stop early."""
        return self.score >= CONFIDENCE_HIGH

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": round(self.score, 4),
            "level": self.level,
            "should_stop": self.should_stop,
            "reasoning": self.reasoning,
            "signals": {k: round(v, 4) for k, v in self.signals.items()},
        }


# ---------------------------------------------------------------------------
# ConfidenceScorer
# ---------------------------------------------------------------------------

class ConfidenceScorer:
    """
    Evaluates confidence of agent outputs using multiple heuristic signals.

    Usage:
        scorer = ConfidenceScorer()
        score = scorer.score_completion(
            task="implementa una API en Rust",
            result="Código implementado...",
            agent="builder",
        )
        if score.should_stop:
            print("Early stopping possible!")
    """

    def __init__(self) -> None:
        # Compile regex patterns once for performance
        self._hedging_re: re.Pattern = re.compile(
            "|".join(_HEDGING_PATTERNS),
            re.IGNORECASE,
        )
        self._self_correction_re: re.Pattern = re.compile(
            "|".join(_SELF_CORRECTION_PATTERNS),
            re.IGNORECASE,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def score_completion(
        self,
        task: str,
        result: str,
        agent: str = "",
        duration_ms: float = 0.0,
    ) -> ConfidenceScore:
        """
        Score a single agent completion using heuristic signals.

        Args:
            task: The original task description.
            result: The agent's output/result.
            agent: Agent name (for potential agent-specific tuning).
            duration_ms: Execution duration in milliseconds.

        Returns:
            ConfidenceScore with aggregated score and reasoning.
        """
        if not result or not result.strip():
            return ConfidenceScore(
                score=0.0,
                reasoning="Empty result — zero confidence",
                signals={"length": 0.0, "hedging": 0.0, "self_correction": 0.0},
            )

        signals: Dict[str, float] = {}

        # Signal 1: Length
        length_score = self._signal_length(task, result)
        signals["length"] = length_score

        # Signal 2: Hedging (inverted: less hedging = higher score)
        hedging_score = self._signal_hedging(result)
        signals["hedging"] = hedging_score

        # Signal 3: Self-correction (inverted: less self-correction = higher score)
        correction_score = self._signal_self_correction(result)
        signals["self_correction"] = correction_score

        # Signal 4: Speed (faster = more confident, if duration available)
        if duration_ms > 0:
            speed_score = self._signal_speed(duration_ms, result)
            signals["speed"] = speed_score

        # Weighted average of all signals (equal weighting by default)
        weights = self._get_weights(agent, bool(signals.get("speed") is not None))
        combined = sum(
            signals[s] * weights[s] for s in signals if s in weights
        )

        # Build reasoning
        reasoning_parts = []
        for sig_name, sig_score in sorted(signals.items()):
            status = "✓" if sig_score >= 0.7 else "△" if sig_score >= 0.4 else "✗"
            reasoning_parts.append(f"{status} {sig_name}={sig_score:.2f}")

        return ConfidenceScore(
            score=min(1.0, max(0.0, combined)),
            reasoning=" | ".join(reasoning_parts),
            signals=signals,
        )

    def score_debate_agreement(
        self,
        outputs: Dict[str, str],
    ) -> ConfidenceScore:
        """
        Score agreement across multiple agent outputs on the same topic.

        When multiple agents produce similar outputs, confidence is higher.
        Uses length similarity as a proxy for agreement.

        Args:
            outputs: Mapping of agent_name -> output_text.

        Returns:
            ConfidenceScore based on inter-agent agreement.
        """
        if not outputs or len(outputs) < 2:
            return ConfidenceScore(
                score=0.5,
                reasoning="Need at least 2 agents to measure agreement",
                signals={"agreement": 0.5},
            )

        agents = list(outputs.keys())
        output_texts = [outputs[a] for a in agents]

        # Measure token-length similarity as proxy for agreement
        token_counts = [estimate_tokens(t) for t in output_texts]
        if any(t == 0 for t in token_counts):
            return ConfidenceScore(
                score=0.3,
                reasoning="Some outputs are empty — low agreement confidence",
                signals={"agreement": 0.3},
            )

        # Compute pairwise agreement: ratio of shorter/longer token counts
        pairwise_scores = []
        for i in range(len(agents)):
            for j in range(i + 1, len(agents)):
                shorter = min(token_counts[i], token_counts[j])
                longer = max(token_counts[i], token_counts[j])
                if longer > 0:
                    pairwise_scores.append(shorter / longer)

        if not pairwise_scores:
            return ConfidenceScore(
                score=0.5,
                reasoning="Could not compute pairwise agreement",
                signals={"agreement": 0.5},
            )

        # Average pairwise agreement — 0.7+ is high agreement
        avg_agreement = sum(pairwise_scores) / len(pairwise_scores)

        # Boost/stretch: 0.0-1.0 ratio maps to 0.3-1.0 confidence
        agreement_score = 0.3 + (avg_agreement * 0.7)

        return ConfidenceScore(
            score=min(1.0, agreement_score),
            reasoning=(
                f"Agreement across {len(agents)} agents: "
                f"{avg_agreement:.2f} avg token-length ratio"
            ),
            signals={"agreement": agreement_score},
        )

    # ------------------------------------------------------------------
    # Signal evaluators
    # ------------------------------------------------------------------

    def _signal_length(self, task: str, result: str) -> float:
        """
        Evaluate output length relative to task length.

        Ideal: output is 2x-20x the task length in tokens.
        - Too short (< 0.5x task): likely incomplete, low confidence
        - Too long (> 50x task): likely rambling, low confidence
        - Goldilocks zone (2x-20x): high confidence
        """
        task_tokens = estimate_tokens(task)
        result_tokens = estimate_tokens(result)

        if task_tokens <= 0 or result_tokens <= 0:
            return 0.5

        ratio = result_tokens / max(1, task_tokens)

        # Goldilocks zone: 2x to 20x task length
        if 2.0 <= ratio <= 20.0:
            return 0.95
        if 1.0 <= ratio <= 30.0:
            return 0.80
        if 0.5 <= ratio <= 50.0:
            return 0.60

        # Too short or too long
        if ratio < 0.5:
            return 0.30
        # ratio > 50
        return 0.20

    def _signal_hedging(self, result: str) -> float:
        """
        Detect hedging language in the result.

        Returns a score from 0.0 (lots of hedging) to 1.0 (no hedging).
        The more hedging patterns found, the lower the confidence.
        """
        if not result:
            return 0.0

        matches = self._hedging_re.findall(result)
        match_count = len(matches)

        if match_count == 0:
            return 1.0  # No hedging — high confidence

        # Normalize by output length (longer outputs may have more hedging)
        normalized = match_count / max(1, estimate_tokens(result))

        if normalized <= 0.01:
            return 0.90  # Very sparse hedging
        if normalized <= 0.02:
            return 0.70
        if normalized <= 0.05:
            return 0.50
        if normalized <= 0.10:
            return 0.30

        return 0.10  # Heavy hedging

    def _signal_self_correction(self, result: str) -> float:
        """
        Detect self-correction patterns in the result.

        Self-correction can indicate uncertainty, but it can also
        indicate thoroughness. We penalize mild-moderate levels,
        but very high levels are a strong negative signal.
        """
        if not result:
            return 0.0

        matches = self._self_correction_re.findall(result)
        match_count = len(matches)

        if match_count == 0:
            return 1.0  # No self-correction — high confidence

        # Normalize by output token count
        normalized = match_count / max(1, estimate_tokens(result))

        # A single self-correction in a long output is fine
        if normalized <= 0.005:
            return 0.90
        if normalized <= 0.015:
            return 0.70
        if normalized <= 0.03:
            return 0.50

        return 0.20  # Excessive self-correction

    def _signal_speed(self, duration_ms: float, result: str) -> float:
        """
        Evaluate generation speed as a confidence signal.

        Faster generation often correlates with higher confidence.
        Very slow generation may indicate hesitation/uncertainty.

        Speed is measured as tokens per second.
        """
        if duration_ms <= 0:
            return 0.5

        tokens = estimate_tokens(result)
        seconds = duration_ms / 1000.0
        if seconds <= 0:
            return 0.5

        tokens_per_second = tokens / seconds

        # Very fast: >50 tokens/sec
        if tokens_per_second > 50:
            return 0.95
        if tokens_per_second > 20:
            return 0.80
        if tokens_per_second > 10:
            return 0.60
        if tokens_per_second > 5:
            return 0.40

        return 0.20  # Very slow generation

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_weights(agent: str, has_speed: bool) -> Dict[str, float]:
        """
        Get signal weights for the weighted average.

        Can be tuned per-agent if needed. Default uses equal weights.
        When speed is unavailable, redistributes its weight.
        """
        base_weights = {
            "length": 0.35,
            "hedging": 0.35,
            "self_correction": 0.30,
        }

        if has_speed:
            # Redistribute when speed is available
            return {
                "length": 0.25,
                "hedging": 0.25,
                "self_correction": 0.20,
                "speed": 0.30,
            }

        return base_weights
