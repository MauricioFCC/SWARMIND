"""Modulo de Guardrails Multi-Capa para AGENTIC.

Implementa un sistema de guardrails en 5 capas inspirado en el AI Factory Stack:
1. Input Guardrails: Filtra prompts maliciosos antes del LLM.
2. Output Guardrails: Valida respuestas antes de entregar al usuario.
3. Content Guardrails: Bloquea contenido peligroso (PII, codigo malicioso).
4. Tool Guardrails: Valida llamadas a herramientas (reusa ToolGuardian).
5. Policy Guardrails: Enforce politicas de negocio (reusa GovernanceGuard).

Cada guardrail produce un GuardrailResult con verdict, score y violaciones.

Exporta:
    - GuardrailVerdict, GuardrailResult, GuardrailRule, GuardrailLayer
    - GuardrailEngine
    - builtin_rules (modulo con reglas incorporadas)
"""

from __future__ import annotations

from harness.guardrails.guardrail_engine import (
    GuardrailEngine,
    GuardrailLayer,
    GuardrailResult,
    GuardrailRule,
    GuardrailVerdict,
)

__all__ = [
    "GuardrailEngine",
    "GuardrailLayer",
    "GuardrailResult",
    "GuardrailRule",
    "GuardrailVerdict",
]
