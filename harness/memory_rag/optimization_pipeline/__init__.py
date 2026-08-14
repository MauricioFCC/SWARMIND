"""
Optimization Pipeline — Punto de integracion de todas las optimizaciones de tokens.

Orquesta:
  1. TokenBudget: presupuesto por agente/sesion con redistribucion dinamica
  2. SemanticCache: cache semantico de respuestas LLM
  3. LazySkillLoader: carga progresiva de skills (3 tiers)
  4. ContextWindowManager: ventana de contexto adaptativa
  5. PromptCacheBuilder: prompts optimizados para cache de proveedores
  6. SkillMinifier: compresion offline de skills
  7. TrajectoryCompressor: compresion de historial conversacional
  8. MultiPass Compaction: pipeline multi-etapa con early stopping (Microsoft 2026)

Ahorro combinado estimado: 60-80% de tokens totales.

Refactorizado a paquete (regla AGR: archivo < 500 lineas). Todos los
simbolos publicos del modulo original se re-exportan desde aqui, por lo
que los imports existentes
(``from harness.memory_rag.optimization_pipeline import OptimizationPipeline``)
siguen funcionando identicos.
"""
from __future__ import annotations

from .core import OptimizationPipeline, create_pipeline
from .models import OptimizationResult

__all__ = [
    "OptimizationPipeline",
    "OptimizationResult",
    "create_pipeline",
]
