"""Metricas y estadisticas de proveedores (mixin de funciones).

Extraccion mecanica de las funciones de metricas/estadisticas del modulo
original ``harness/model_router/provider_health.py`` (sin cambios de
logica ni firmas).

Cada funcion recibe ``self`` como primer argumento (instancia de
MultiAPIProvider) para acceder a sus atributos internos.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from harness.model_router.multi_provider_types import (
    ProviderHealth,
    ProviderStatus,
)

from .health import _update_percentiles

logger = logging.getLogger("harness.model_router.provider_health")


def get_stats(self) -> dict[str, Any]:
    """Retorna estadisticas completas de todos los proveedores.

    Returns:
        Diccionario con metricas por proveedor, incluyendo estado,
        latencias, costos, tasas de error y conteo de requests.
    """
    stats: dict[str, Any] = {
        "providers": {},
        "total_cost_usd": 0.0,
        "total_requests": 0,
        "global_health": ProviderStatus.UNKNOWN.value,
    }

    with self._lock:
        for pname in self._providers:
            config = self._providers[pname]["config"]
            health = self._health.get(pname)
            history = self._latency_history.get(pname)

            pstats: dict[str, Any] = {
                "tier": config.tier,
                "models": config.models,
                "health": {
                    "available": health.available if health else False,
                    "status": health.status.value if health else ProviderStatus.UNKNOWN.value,
                    "latency_p50_ms": round(health.latency_p50, 2) if health else 0.0,
                    "latency_p95_ms": round(health.latency_p95, 2) if health else 0.0,
                    "latency_p99_ms": round(health.latency_p99, 2) if health else 0.0,
                    "error_rate": round(health.error_rate, 4) if health else 0.0,
                    "consecutive_failures": health.consecutive_failures if health else 0,
                    "last_check": health.last_check if health else 0,
                } if health else {},
                "costs": {
                    "total_usd": round(self._costs.get(pname, 0.0), 6),
                },
                "requests": {
                    "total": self._request_counts.get(pname, 0),
                    "errors": self._error_counts.get(pname, 0),
                },
                "samples": len(history) if history else 0,
            }

            stats["providers"][pname] = pstats
            stats["total_cost_usd"] += self._costs.get(pname, 0.0)
            stats["total_requests"] += self._request_counts.get(pname, 0)

    stats["total_cost_usd"] = round(stats["total_cost_usd"], 6)

    all_available = all(
        self._health.get(p, ProviderHealth()).available
        for p in self._providers
    )
    any_available = any(
        self._health.get(p, ProviderHealth()).available
        for p in self._providers
    )

    if all_available and stats["providers"]:
        stats["global_health"] = ProviderStatus.AVAILABLE.value
    elif any_available:
        stats["global_health"] = ProviderStatus.DEGRADED.value
    else:
        stats["global_health"] = ProviderStatus.UNAVAILABLE.value

    return stats

def get_provider_stats(self, name: str) -> dict[str, Any] | None:
    """Retorna estadisticas detalladas de un proveedor especifico.

    Args:
        name: Nombre del proveedor.

    Returns:
        Diccionario con metricas del proveedor o None si no existe.
    """
    all_stats = get_stats(self)
    return all_stats.get("providers", {}).get(name)

def _record_success(self, provider: str, latency_ms: float) -> None:
    """Registra una ejecucion exitosa y actualiza metricas de latencia.

    Args:
        provider: Nombre del proveedor.
        latency_ms: Latencia de la ejecucion en milisegundos.
    """
    with self._lock:
        self._latency_history[provider].append(latency_ms)
        self._request_counts[provider] += 1

        health = self._health.get(provider)
        if health is not None:
            health.last_success = time.time()
            health.consecutive_failures = 0
            health.status = ProviderStatus.AVAILABLE
            health.available = True
            _update_percentiles(self, provider, health)

def _record_error(self, provider: str, error: str) -> None:
    """Registra un error de ejecucion.

    Args:
        provider: Nombre del proveedor.
        error: Mensaje de error.
    """
    with self._lock:
        self._error_counts[provider] += 1
        self._request_counts[provider] += 1

        health = self._health.get(provider)
        if health is not None:
            health.consecutive_failures += 1
            if health.consecutive_failures >= 3:
                health.status = ProviderStatus.UNAVAILABLE
                health.available = False
            elif health.consecutive_failures >= 1:
                health.status = ProviderStatus.DEGRADED
