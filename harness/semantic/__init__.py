"""Capa semántica gobernada (ADR-0050) — API pública del paquete.

Re-exporta los símbolos canónicos para que los consumidores usen
``from harness.semantic import SemanticLayer`` sin conocer el módulo interno.
"""

from __future__ import annotations

from harness.semantic.layer import (
    BANK_CASE_COST_REDUCTION_RATIO,
    SemanticDefinition,
    SemanticDimension,
    SemanticLayer,
    SemanticMetric,
    SemanticRoute,
    build_bank_reference_layer,
)

__all__ = [
    "BANK_CASE_COST_REDUCTION_RATIO",
    "SemanticDefinition",
    "SemanticDimension",
    "SemanticLayer",
    "SemanticMetric",
    "SemanticRoute",
    "build_bank_reference_layer",
]
