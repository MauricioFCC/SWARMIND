"""
GEPA (Genetic Evolutionary Prompt Algorithm) â€” Hermes-inspired prompt mutator.

Creates N mutated variants of an agent/system prompt, tests them in a sandbox,
and promotes the winner. Implements the "Evolucion Genetica de Prompts" pattern.
"""
from __future__ import annotations

import logging
import random
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MutantPrompt:
    """MutantPrompt."""
    id: str
    source_agent: str
    original_prompt: str
    mutated_prompt: str
    mutations_applied: list[str]
    score: float = 0.0
    test_results: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def __post_init__(self):
        """Post init."""
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


_MUTATION_STRATEGIES = [
    # Strategy 1: Reorder paragraphs
    "reorder_paragraphs",
    # Strategy 2: Add constraint prefix
    "add_constraint_prefix",
    # Strategy 3: Strengthen action verbs
    "strengthen_verbs",
    # Strategy 4: Add specificity markers
    "add_specificity",
    # Strategy 5: Condense (remove filler)
    "condense",
    # Strategy 6: Add C.A.S.E. structure
    "add_case_structure",
    # Strategy 7: Weaken hedging language
    "remove_hedging",
    # Strategy 8: Add role emphasis
    "emphasize_role",
]


class GEPAMutator:
    """
    Genetic Evolutionary Prompt Algorithm mutator.

    Takes a source agent prompt and produces mutated variants.
    Each variant applies a random subset of mutation strategies.
    """

    def __init__(self, seed: int | None = None) -> None:
        """Inicializa la instancia de la clase."""
        self.rng = random.Random(seed)
        self._mutation_log: list[dict[str, Any]] = []

    def create_mutants(
        self,
        source_agent: str,
        original_prompt: str,
        num_mutants: int = 3,
        strategies: list[str] | None = None,
    ) -> list[MutantPrompt]:
        """
        Generate N mutated variants of a prompt.

        Args:
            source_agent: Agent name (e.g. "software-engineer").
            original_prompt: The full system prompt text.
            num_mutants: How many variants to generate.
            strategies: Subset of strategies to use (default: all).

        Returns:
            List of MutantPrompt, one per variant.
        """
        if strategies is None:
            strategies = list(_MUTATION_STRATEGIES)

        mutants: list[MutantPrompt] = []
        for _ in range(num_mutants):
            # Pick 2-4 random strategies
            num_strats = min(self.rng.randint(2, 4), len(strategies))
            chosen = self.rng.sample(strategies, num_strats)
            mutated, applied = self._apply_strategies(original_prompt, chosen)

            mid = uuid.uuid4().hex[:12]
            mutants.append(MutantPrompt(
                id=mid,
                source_agent=source_agent,
                original_prompt=original_prompt,
                mutated_prompt=mutated,
                mutations_applied=applied,
            ))

        return mutants

    def score_and_promote(
        self,
        mutants: list[MutantPrompt],
        test_scores: dict[str, float],
    ) -> tuple[MutantPrompt, float]:
        """
        Score mutants and return the winner.

        Args:
            mutants: List of MutantPrompt to evaluate.
            test_scores: Dict mapping mutant_id -> float score.

        Returns:
            (winning mutant, winning score) tuple.
        """
        best_mutant: MutantPrompt | None = None
        best_score = -1.0

        for mutant in mutants:
            score = test_scores.get(mutant.id, 0.0)
            mutant.score = score
            if score > best_score:
                best_score = score
                best_mutant = mutant

        if best_mutant is None:
            best_mutant = mutants[0]

        self._log_mutation_round(mutants, best_mutant, best_score)
        return best_mutant, best_score

    def _apply_strategies(
        self, prompt: str, strategies: list[str]
    ) -> tuple[str, list[str]]:
        """Apply selected mutation strategies to the prompt."""
        text = prompt
        applied: list[str] = []

        strategy_map = {
            "reorder_paragraphs": self._reorder_paragraphs,
            "add_constraint_prefix": self._add_constraint_prefix,
            "strengthen_verbs": self._strengthen_verbs,
            "add_specificity": self._add_specificity,
            "condense": self._condense,
            "add_case_structure": self._add_case_structure,
            "remove_hedging": self._remove_hedging,
            "emphasize_role": self._emphasize_role,
        }

        for s in strategies:
            fn = strategy_map.get(s)
            if fn:
                try:
                    text = fn(text)
                    applied.append(s)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Strategy '%s' failed: %s", s, exc)

        return text, applied

    # ------------------------------------------------------------------
    # Mutation strategies
    # ------------------------------------------------------------------

    @staticmethod
    def _reorder_paragraphs(text: str) -> str:
        """Shuffle top-level paragraph order (split by double newline)."""
        paragraphs = re.split(r"\n\s*\n", text)
        if len(paragraphs) < 2:
            return text
        # Keep first paragraph (role definition) fixed, shuffle rest
        first = paragraphs[0]
        rest = paragraphs[1:]
        random.shuffle(rest)
        return "\n\n".join([first] + rest)

    @staticmethod
    def _add_constraint_prefix(text: str) -> str:
        """Prepend a constraint line if not already present."""
        constraints = [
            "CRITICAL: You must follow C.A.S.E. (Clarify, Architect, Solve, Evaluate) reasoning in every response.",
            "IMPORTANT: Always output code that is production-ready, typed, and documented.",
            "REQUIREMENT: Stay within the token budget. Be concise and precise.",
            "RULE: Never hallucinate APIs or libraries. Only use what is available.",
        ]
        chosen = random.choice(constraints)
        if chosen not in text:
            return f"{chosen}\n\n{text}"
        return text

    @staticmethod
    def _strengthen_verbs(text: str) -> str:
        """Replace weak verbs with stronger alternatives."""
        replacements = [
            (r"\bmight\b", "will"),
            (r"\bcould\b", "shall"),
            (r"\bshould\b", "must"),
            (r"\bconsider\b", "implement"),
            (r"\btry to\b", ""),
            (r"\byou can\b", "you must"),
            (r"\byou may\b", "you will"),
        ]
        for pattern, replacement in replacements:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text

    @staticmethod
    def _add_specificity(text: str) -> str:
        """Add specificity markers like concrete examples."""
        specificity_boosters = [
            "Provide concrete code examples in every response.",
            "Include specific function names and class signatures.",
            "Reference exact file paths and line numbers when discussing code.",
            "Always include error handling and edge case coverage.",
        ]
        booster = random.choice(specificity_boosters)
        return f"{text}\n\n[Specificity]: {booster}"

    @staticmethod
    def _condense(text: str) -> str:
        """Remove filler words and redundant phrases."""
        fillers = [
            (r"\bin order to\b", "to"),
            (r"\bdue to the fact that\b", "because"),
            (r"\bas a matter of fact\b", ""),
            (r"\bin the event that\b", "if"),
            (r"\bregardless of\b", "despite"),
            (r"\bon a regular basis\b", "regularly"),
            (r"\bin the process of\b", ""),
            (r"\bthe majority of\b", "most"),
            (r"\ba number of\b", "some"),
            (r"\bis able to\b", "can"),
        ]
        for pattern, replacement in fillers:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text

    @staticmethod
    def _add_case_structure(text: str) -> str:
        """Wrap the prompt in explicit C.A.S.E. structure if missing."""
        case_block = (
            "Follow this structured reasoning process:\n"
            "1. CLARIFY: Understand the problem before solving it.\n"
            "2. ARCHITECT: Design a solution before coding it.\n"
            "3. SOLVE: Implement the solution with concrete code.\n"
            "4. EVALUATE: Review trade-offs, risks, and alternatives."
        )
        if "CLARIFY" not in text.upper() and "C.A.S.E." not in text:
            return f"{text}\n\n{case_block}"
        return text

    @staticmethod
    def _remove_hedging(text: str) -> str:
        """Remove hedging / uncertain language."""
        hedges = [
            (r"\bI think\b", ""),
            (r"\bI believe\b", ""),
            (r"\bperhaps\b", ""),
            (r"\bmaybe\b", ""),
            (r"\bprobably\b", ""),
            (r"\bI'm not sure but\b", ""),
            (r"\bit seems that\b", ""),
            (r"\bkind of\b", ""),
            (r"\bsort of\b", ""),
        ]
        for pattern, replacement in hedges:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        # Clean up double spaces
        text = re.sub(r" {2,}", " ", text)
        return text

    @staticmethod
    def _emphasize_role(text: str) -> str:
        """Strengthen the role definition at the start."""
        lines = text.split("\n")
        if lines:
            first_line = lines[0]
            if first_line.startswith(("You are", "Eres")):
                emphasis = random.choice([
                    f"[ROLE]: {first_line}",
                    f"{first_line} [AUTHORITY: You have final say on this domain]",
                ])
                lines[0] = emphasis
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log_mutation_round(
        self,
        mutants: list[MutantPrompt],
        winner: MutantPrompt,
        winner_score: float,
    ) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "num_mutants": len(mutants),
            "winner_id": winner.id,
            "winner_score": winner_score,
            "winner_mutations": winner.mutations_applied,
        }
        self._mutation_log.append(entry)
        logger.info(
            "GEPA round complete: %d mutants, winner=%s (score=%.3f)",
            len(mutants), winner.id, winner_score,
        )

    def get_mutation_log(self) -> list[dict[str, Any]]:
        """Get mutation log."""
        return list(self._mutation_log)
