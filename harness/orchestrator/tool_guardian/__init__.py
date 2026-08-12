"""ToolGuardian — Seguridad declarativa para interacciones agente-herramienta.

Antes: harness/orchestrator/tool_guardian.py (722 lineas).
Ahora: paquete ``harness/orchestrator/tool_guardian/``:

- ``constants.py``: patrones peligrosos, syscalls y ofuscacion.
- ``models.py``: ToolRiskLevel, CharacterizationStage, ToolPolicy,
  CharacterizationResult.
- ``policies.py``: mixin ``_PoliciesMixin`` (politicas por defecto + CRUD).
- ``validation.py``: mixin ``_ValidationMixin`` (validate_tool_call).
- ``analysis.py``: mixin ``_AnalysisMixin`` (analyze_tool).
- ``characterization.py``: mixin ``_CharacterizationMixin`` (pipeline 4 etapas).
- ``core.py``: clase ``ToolGuardian`` (estado + __init__).

Este ``__init__.py`` re-exporta TODOS los simbolos publicos del modulo
original para mantener backward-compat:

    from harness.orchestrator.tool_guardian import ToolGuardian

Regla AGR: cada archivo del paquete queda por debajo de 500 lineas.
"""

from __future__ import annotations

from .constants import DANGEROUS_PATTERNS, HIGH_RISK_SYSCALLS, OBFUSCATION_PATTERNS
from .core import ToolGuardian
from .models import (
    CharacterizationResult,
    CharacterizationStage,
    ToolPolicy,
    ToolRiskLevel,
)

__all__ = [
    "DANGEROUS_PATTERNS",
    "HIGH_RISK_SYSCALLS",
    "OBFUSCATION_PATTERNS",
    "CharacterizationResult",
    "CharacterizationStage",
    "ToolGuardian",
    "ToolPolicy",
    "ToolRiskLevel",
]
