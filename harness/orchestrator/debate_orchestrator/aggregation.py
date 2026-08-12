"""Agregacion y metricas de consenso (extraccion mecanica).

Mixin privado con helpers de similaridad, acuerdo entre agentes,
ganador por mayoria, sintesis y verificacion de critica.
"""
from __future__ import annotations


class _AggregationMixin:
    """Helpers de agregacion compartidos por las estrategias de debate."""
    @staticmethod
    def _text_similarity(a: str, b: str) -> float:
        """Compute word-overlap similarity between two strings (0.0â€“1.0)."""
        if not a or not b:
            return 0.0
        words_a = set(a.lower().split())
        words_b = set(b.lower().split())
        if not words_a or not words_b:
            return 0.0
        intersection = words_a & words_b
        union = words_a | words_b
        return len(intersection) / len(union)

    def _compute_agreement(self, outputs: dict[str, str]) -> float:
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
        outputs: dict[str, str],
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
    def _synthesize_answers(outputs: dict[str, str]) -> str:
        """
        Produce a simple synthesis of all agent outputs.

        Takes the longest output as a heuristic for most detailed answer.
        """
        if not outputs:
            return ""
        # Pick the longest output as the most detailed
        best = max(outputs.items(), key=lambda x: len(x[1]))
        return (
            f"[SÃ­ntesis de {len(outputs)} agente(s)]\n"
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
