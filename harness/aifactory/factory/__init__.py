"""AIFactory - Core orchestrator (refactorizado a paquete).

Antes: harness/aifactory/factory.py (905 lineas).
Ahora: paquete ``harness/aifactory/factory/`` con submódulos cohesivos:

- ``core.py``: clase ``AIFactory`` (estado, metricas, resultado).
- ``pipeline.py``: mixin ``_PipelineMixin`` con ``process()``.
- ``layers.py``: mixin ``_LayerExecutorMixin`` con los ``_execute_*``
  y ``process_stream()`` (fusionado con el antiguo ``_StreamMixin``).

Este ``__init__.py`` re-exporta TODOS los simbolos publicos del modulo
original para mantener backward-compat:

    from harness.aifactory.factory import AIFactory, FactoryStatus

Regla AGR: cada archivo del paquete queda por debajo de 500 lineas.
"""

from __future__ import annotations

from harness.aifactory.factory_types import (
    EvalReport,
    FactoryConfig,
    FactoryResult,
    FactoryStatus,
    LayerTrace,
    LayerType,
)

from .core import AIFactory

__all__ = [
    "AIFactory",
    "EvalReport",
    "FactoryConfig",
    "FactoryResult",
    "FactoryStatus",
    "LayerTrace",
    "LayerType",
]
