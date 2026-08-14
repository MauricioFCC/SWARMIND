"""Clase ``MultiAPIProvider`` — gestion multi-proveedor con failover.

Antes: harness/model_router/multi_provider.py (511 lineas).
Ahora: paquete ``harness/model_router/multi_provider/``:

- ``registry.py``: mixin ``_RegistryMixin`` (registro/eliminacion/listado).
- ``execution.py``: mixin ``_ExecutionMixin`` (failover + delegados).
- ``core.py``: clase ``MultiAPIProvider(_RegistryMixin, _ExecutionMixin)``.

Regla AGR: cada archivo del paquete queda por debajo de 500 lineas.
"""

from __future__ import annotations

import threading
from collections import defaultdict, deque
from typing import Any

from harness.model_router.multi_provider_types import (
    LATENCY_WINDOW_SIZE,
    BudgetLimit,
    ProviderHealth,
)

from .execution import _ExecutionMixin
from .registry import _RegistryMixin


class MultiAPIProvider(_RegistryMixin, _ExecutionMixin):
    """AbstracciÃ³n multi-provider con failover automÃ¡tico y balanceo de carga.

    Gestiona mÃºltiples proveedores LLM (OpenAI, Anthropic, Google, Mistral,
    DeepSeek) con registro dinÃ¡mico, health checks periÃ³dicos, round-robin
    por tier, tracking de costos y mÃ©tricas de latencia P50/P95/P99.

    Ejemplo:
        mcp = MultiAPIProvider()
        mcp.register_provider(ProviderConfig(
            name="openai", api_key_env="OPENAI_API_KEY",
            base_url="https://api.openai.com/v1",
            models=["gpt-4o", "gpt-4o-mini"],
            tier="premium", cost_per_1k_input=2.5, cost_per_1k_output=10.0,
        ))
        result = mcp.execute("gpt-4o", "Hello world")
        stats = mcp.get_stats()
    """

    def __init__(self) -> None:
        """Inicializa el gestor multi-provider.

        WHY: Se requiere un estado compartido para proveedores, mÃ©tricas y
        controles de costo a nivel de instancia.
        WHERE: Constructor de MultiAPIProvider.
        """
        # name -> {config, client}
        self._providers: dict[str, dict[str, Any]] = {}

        # tier -> list of provider names (for round-robin)
        self._tier_providers: dict[str, list[str]] = defaultdict(list)

        # tier -> current round-robin index
        self._rr_indices: dict[str, int] = defaultdict(int)

        # provider health cache
        self._health: dict[str, ProviderHealth] = {}

        # latency history per provider (rolling window)
        self._latency_history: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=LATENCY_WINDOW_SIZE)
        )

        # cost tracking per provider (USD total)
        self._costs: dict[str, float] = defaultdict(float)

        # cost tracking per model (USD total)
        self._model_costs: dict[str, float] = defaultdict(float)

        # request counts
        self._request_counts: dict[str, int] = defaultdict(int)
        self._error_counts: dict[str, int] = defaultdict(int)

        # budget limits per project
        self._budgets: dict[str, BudgetLimit] = {}

        # health check thread control
        self._health_thread: threading.Thread | None = None
        self._health_stop = threading.Event()

        # lock for thread safety
        self._lock = threading.RLock()

        # iniciar health checks en background
        self._start_health_checks()


    def __del__(self) -> None:
        """Cleanup: detiene health checks al destruir la instancia."""
        try:
            self.stop_health_checks()
        except Exception:  # noqa: S110, BLE001
            pass
