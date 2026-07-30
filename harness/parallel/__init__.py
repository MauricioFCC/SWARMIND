"""Modulo de Paralelismo Maximo — Estrategias frontier 2026.

Implementa 5 estrategias de paralelismo para Swarmind basadas en
investigacion frontier (Scepsy, MACU, PEP 684):

1. Async I/O Fusion: BatchAccumulator para operaciones I/O batch.
2. Adaptive Worker Pool: Auto-escalado por CPU/memoria.
3. Pipeline MACU: DAG vivo con replanning continuo.
4. Zero-copy Shared Memory: Buffer circular en shared memory.
5. ProcessPoolExecutor: CPU-bound tasks sin GIL.

Referencias:
- arXiv:2604.15186 (Scepsy): Aggregate LLM Pipelines
- arXiv:2606.01533 (MACU): Multi-Agent Computer Use DAG
"""

from __future__ import annotations

from harness.parallel.io_fusion import BatchAccumulator
from harness.parallel.adaptive_pool import AdaptivePool
from harness.parallel.pipeline_macu import PipelineMACU, PipelineTask

__all__ = [
    "BatchAccumulator",
    "AdaptivePool",
    "PipelineMACU",
    "PipelineTask",
]
