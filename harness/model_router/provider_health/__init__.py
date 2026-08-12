"""provider_health — Health checks, cost tracking, budget control y metricas.

Antes: harness/model_router/provider_health.py (524 lineas).
Ahora: paquete ``harness/model_router/provider_health/``:

- ``health.py``: health checks (health_check, _check_single_provider, ...).
- ``cost.py``: cost tracking y budget control (_track_cost, set_budget, ...).
- ``stats.py``: metricas y estadisticas (get_stats, _record_success, ...).

Este ``__init__.py`` re-exporta TODOS los simbolos del modulo original
para mantener backward-compat:

    from harness.model_router.provider_health import health_check

Regla AGR: cada archivo del paquete queda por debajo de 500 lineas.
"""

from __future__ import annotations

from harness.model_router.multi_provider_types import (
    ProviderHealth,
    ProviderStatus,
)

from .cost import (
    _allocate_cost_to_project,
    _calculate_cost,
    _track_cost,
    check_budget,
    get_total_cost,
    set_budget,
)
from .health import (
    HEALTH_CHECK_INTERVAL_S,
    _check_single_provider,
    _start_health_checks,
    _update_percentiles,
    health_check,
    stop_health_checks,
)
from .stats import (
    _record_error,
    _record_success,
    get_provider_stats,
    get_stats,
)

__all__ = [
    "HEALTH_CHECK_INTERVAL_S",
    "ProviderHealth",
    "ProviderStatus",
    "_allocate_cost_to_project",
    "_calculate_cost",
    "_check_single_provider",
    "_record_error",
    "_record_success",
    "_start_health_checks",
    "_track_cost",
    "_update_percentiles",
    "check_budget",
    "get_provider_stats",
    "get_stats",
    "get_total_cost",
    "health_check",
    "set_budget",
    "stop_health_checks",
]
