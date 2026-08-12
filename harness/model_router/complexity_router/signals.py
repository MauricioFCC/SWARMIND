"""Senales heuristicas de complejidad (mixin ``_SignalMixin``).

Extraccion mecanica de los metodos de extraccion de senales y scoring
del modulo original (sin cambios de logica ni firmas).

Classes:
    _SignalMixin: Mixin con la extraccion de senales, el computo de score
        y los helpers de confianza/ahorro usados por ``ComplexityRouter``.
"""

from __future__ import annotations

from typing import Any

from .constants import (
    KEYWORD_COMPLEX_DOMAINS,
    KEYWORD_REASONING,
    LONG_HIGH,
    LONG_LOW,
    LONG_MED,
    SCORE_COMPLEX_DOMAIN,
    SCORE_KEYWORD_REASONING,
    SCORE_LENGTH_HIGH,
    SCORE_LENGTH_MEDIUM,
    SCORE_MAX,
    SCORE_MIN,
    SCORE_MULTI_INSTRUCTION,
    SCORE_SHORT_TASK,
    SCORE_SIMPLE_TERM,
    SIGNAL_DOMAIN_COMPLEX,
    SIGNAL_KEYWORD_REASONING,
    SIGNAL_LONG_HIGH,
    SIGNAL_LONG_MEDIUM,
    SIGNAL_MULTI_INSTRUCTION,
    SIGNAL_SHORT_TASK,
    SIGNAL_SIMPLE_TASK_TERM,
    SIMPLE_TASK_TERMS,
)


class _SignalMixin:
    """Mixin con la extraccion de senales y el computo de score."""

    def _extract_signals(self, task_text: str) -> dict[str, Any]:
        """Extrae señales heuristicas del texto de la tarea."""
        if not task_text:
            return {
                SIGNAL_SHORT_TASK: True,
                SIGNAL_KEYWORD_REASONING: False,
                SIGNAL_DOMAIN_COMPLEX: False,
                SIGNAL_SIMPLE_TASK_TERM: True,
                SIGNAL_MULTI_INSTRUCTION: False,
            }

        task_lower = task_text.lower()

        # 1. ¿Es una tarea corta? (<= 60 chars)
        is_short = len(task_text) <= LONG_LOW

        # 2. Keywords de razonamiento
        has_reasoning = any(kw in task_lower for kw in KEYWORD_REASONING)

        # 3. Dominio complejo (keywords o domain_hint explícito)
        has_complex_domain = any(
            kw in task_lower for kw in KEYWORD_COMPLEX_DOMAINS
        ) or bool(self._domain_hint)

        # 4. Términos simples (formatea, traduce, etc.)
        has_simple_term = any(kw in task_lower for kw in SIMPLE_TASK_TERMS)

        # 5. Múltiples instrucciones (comas o conectores lógicos)
        multi_instr = task_lower.count(", ") > 2 or any(
            conn in task_lower for conn in ["luego", "porque", "entonces", "ademas"]
        )

        return {
            SIGNAL_SHORT_TASK: is_short,
            SIGNAL_KEYWORD_REASONING: has_reasoning,
            SIGNAL_DOMAIN_COMPLEX: has_complex_domain,
            SIGNAL_SIMPLE_TASK_TERM: has_simple_term,
            SIGNAL_MULTI_INSTRUCTION: multi_instr,
        }

    def _long_signal(self, task_length: int) -> str | None:
        """Señal de longitud activada (None si el rango es neutral)."""
        if task_length >= LONG_HIGH:
            return SIGNAL_LONG_HIGH
        if task_length >= LONG_MED:
            return SIGNAL_LONG_MEDIUM
        if task_length <= LONG_LOW:
            return SIGNAL_SHORT_TASK
        return None

    def _compute_score(
        self, signals: dict[str, Any], task_length: int
    ) -> float:
        """Computa un score de complejidad 0..100 a partir de las señales."""
        score = SCORE_MIN

        # Señal de longitud (solo contribuye en rangos no-neutrales)
        long_signal = self._long_signal(task_length)
        if long_signal == SIGNAL_LONG_HIGH:
            score += SCORE_LENGTH_HIGH
        elif long_signal == SIGNAL_LONG_MEDIUM:
            score += SCORE_LENGTH_MEDIUM
        elif long_signal == SIGNAL_SHORT_TASK:
            score += SCORE_SHORT_TASK

        # Señal de razonamiento (cap 50)
        if signals.get(SIGNAL_KEYWORD_REASONING, False):
            score += SCORE_KEYWORD_REASONING

        # Señal de dominio complejo
        if signals.get(SIGNAL_DOMAIN_COMPLEX, False):
            score += SCORE_COMPLEX_DOMAIN

        # Señal de término simple (penaliza)
        if signals.get(SIGNAL_SIMPLE_TASK_TERM, False):
            score += SCORE_SIMPLE_TERM

        # Múltiples instrucciones (leva un poco)
        if signals.get(SIGNAL_MULTI_INSTRUCTION, False):
            score += SCORE_MULTI_INSTRUCTION

        # Clamp a 0..100
        return max(SCORE_MIN, min(SCORE_MAX, score))

    def _activated_signals(
        self, signals: dict[str, Any], long_signal: str | None
    ) -> tuple[str, ...]:
        """Nombres de las señales ACTIVADAS (tuple ordenada, sin duplicados)."""
        active: set[str] = {name for name, value in signals.items() if value}
        if long_signal:
            active.add(long_signal)
        return tuple(sorted(active))

    def _savings_ratio(self, score: float) -> float:
        """Factor estimado de ahorro según score (3x simple, 1.5x media, 1x frontier)."""
        if score < 30:
            return 3.0
        if score < 70:
            return 1.5
        return 1.0

    def _confidence(self, score: float) -> float:
        """Confianza en la decisión (más alta en scores extremos)."""
        return min(1.0, 0.5 + 0.01 * score)
