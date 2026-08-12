"""ShapleyFlow — Asignacion de tokens basada en Shapley Value.

Distribuye el presupuesto de tokens entre secciones de un prompt
proporcionalmente a su contribucion marginal al resultado final.
Usa el valor de Shapley para calcular la importancia de cada seccion.

La funcion caracteristica ``v(S)`` estima el "valor" de un subconjunto de
secciones combinando relevancia semantica, densidad de informacion y
posicion estratrgica dentro del prompt.

Basado en: ShapleyFlow (ADR-0010, B26) — Cooperative game-theoretic
attribution para workflows swarmind. ACL 2026.

Uso:
    flow = ShapleyFlow()
    sections = {
        "system": "Eres un asistente experto en Python...",
        "user": "Implementa una funcion que calcule fibonacci...",
        "rag": "Contexto recuperado: PEP 8, patrones de diseno...",
        "skill": "Habilidades: codigo, testing, revision...",
    }
    allocations = flow.allocate(sections, total_budget=4096)
    for alloc in allocations:
        print(f"{alloc.section}: {alloc.shapley_value:.3f} -> {alloc.token_budget} tokens")

Refactorizado a paquete (regla AGR: archivo < 500 lineas). Todos los
simbolos publicos del modulo original se re-exportan desde aqui, por lo
que los imports existentes
(``from harness.memory_rag.shapley_flow import ShapleyFlow``) siguen
funcionando identicos.
"""
from __future__ import annotations

from .constants import (
    _FACTORIAL_CACHE,
    MIN_SECTION_TOKENS,
    WEIGHT_KEYWORD_MATCH,
    WEIGHT_LENGTH_PENALTY,
    WEIGHT_POSITION_PREMIUM,
    WEIGHT_SEMANTIC_DENSITY,
    WEIGHT_TOKEN_COUNT,
    _factorial,
)
from .core import ShapleyFlow, create_shapley_flow
from .models import ShapleyAllocation, _SectionFeatures

__all__ = [
    "MIN_SECTION_TOKENS",
    "WEIGHT_KEYWORD_MATCH",
    "WEIGHT_LENGTH_PENALTY",
    "WEIGHT_POSITION_PREMIUM",
    "WEIGHT_SEMANTIC_DENSITY",
    "WEIGHT_TOKEN_COUNT",
    "_FACTORIAL_CACHE",
    "ShapleyAllocation",
    "ShapleyFlow",
    "_SectionFeatures",
    "_factorial",
    "create_shapley_flow",
]
