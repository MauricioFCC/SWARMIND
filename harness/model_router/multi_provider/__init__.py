"""MultiAPIProvider — Abstraccion multi-proveedor con failover (paquete).

Antes: harness/model_router/multi_provider.py (511 lineas).
Ahora: paquete ``harness/model_router/multi_provider/`` con submódulos
cohesivos (registry.py, execution.py, core.py).

Este ``__init__.py`` re-exporta TODOS los simbolos publicos del modulo
original (incluidos los tipos re-exportados de multi_provider_types que
router.py y harness/model_router/__init__.py consumen) para mantener
backward-compat:

    from harness.model_router.multi_provider import MultiAPIProvider

Regla AGR: cada archivo del paquete queda por debajo de 500 lineas.
"""

from __future__ import annotations

from harness.model_router.multi_provider_types import (
    LATENCY_WINDOW_SIZE,
    MAX_TOKENS_BY_AGENT,
    BudgetLimit,
    ExecutionResult,
    ProviderConfig,
    ProviderHealth,
    ProviderTier,
)

from .core import MultiAPIProvider

__all__ = [
    "LATENCY_WINDOW_SIZE",
    "MAX_TOKENS_BY_AGENT",
    "BudgetLimit",
    "ExecutionResult",
    "MultiAPIProvider",
    "ProviderConfig",
    "ProviderHealth",
    "ProviderTier",
]
