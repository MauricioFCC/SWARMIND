"""GuardrailEngine (refactorizado a paquete).

Antes: harness/guardrails/guardrail_engine.py (685 lineas).
Ahora: paquete ``harness/guardrails/guardrail_engine/`` con submódulos
cohesivos:

- ``core.py``: clase ``GuardrailEngine`` (constructor, properties, summary).
- ``rules_mixin.py``: mixin ``_RulesMixin`` (reglas built-in + gestion).
- ``checks_mixin.py``: mixin ``_ChecksMixin`` (checks de las 5 capas).
- ``stats_mixin.py``: mixin ``_StatsMixin`` (estadisticas de uso).

Este ``__init__.py`` re-exporta TODOS los simbolos publicos del modulo
original para mantener backward-compat:

    from harness.guardrails.guardrail_engine import GuardrailEngine

Regla AGR: cada archivo del paquete queda por debajo de 500 lineas.
"""

from __future__ import annotations

from .core import GuardrailEngine

__all__ = [
    "GuardrailEngine",
]
