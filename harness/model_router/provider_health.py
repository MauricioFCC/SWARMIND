"""provider_health — Health checks, cost tracking, budget control y metricas.

Extraido de provider_executors.py para mantener modulos < 900 lines.

Cada funcion recibe ``self`` como primer argumento (instancia de
MultiAPIProvider) para acceder a sus atributos internos.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from harness.model_router.multi_provider_types import (
    ProviderHealth,
    ProviderStatus,
    ProviderTier,
)

logger = logging.getLogger(__name__)

# Intervalo en segundos entre health checks periodicos
HEALTH_CHECK_INTERVAL_S = 30


# ------------------------------------------------------------------
# Health checks
# ------------------------------------------------------------------


def health_check(self, provider: Optional[str] = None) -> bool:
    """Ejecuta health check sobre uno o todos los proveedores.

    Args:
        provider: Nombre del proveedor. Si es None, verifica todos.

    Returns:
        True si el/los proveedor(es) estan disponibles.

    WHY: Permite verificar disponibilidad bajo demanda, ademas de
    los chequeos periodicos en background.
    WHERE: health_check en MultiAPIProvider.
    """
    if provider is not None:
        return _check_single_provider(self, provider)

    all_ok = True
    with self._lock:
        names = list(self._providers.keys())
    for pname in names:
        ok = _check_single_provider(self, pname)
        all_ok = all_ok and ok
    return all_ok


def _check_single_provider(self, name: str) -> bool:
    """Verifica disponibilidad de un proveedor individual.

    Realiza una solicitud liviana (listado de modelos o ping) para
    determinar si el proveedor responde.

    Args:
        name: Nombre del proveedor.

    Returns:
        True si el proveedor esta disponible.
    """
    with self._lock:
        entry = self._providers.get(name)
        if entry is None:
            logger.warning(
                "Health check: provider '%s' no registrado. WHERE: _check_single_provider",
                name,
            )
            return False
        config = entry["config"]

    start = time.perf_counter()
    available = False
    try:
        import requests

        timeout_s = max(5.0, config.timeout_ms / 2000.0)

        base_url = config.base_url.rstrip("/")
        api_key = os.environ.get(config.api_key_env, "")

        if config.name.lower() == "anthropic":
            resp = requests.get(
                f"{base_url}/", timeout=timeout_s,
                headers={"x-api-key": api_key},
            )
            available = resp.status_code < 500

        elif config.name.lower() == "google":
            resp = requests.get(
                f"{base_url}/v1/models",
                timeout=timeout_s,
                headers={"x-goog-api-key": api_key},
            )
            available = resp.status_code == 200

        else:
            resp = requests.get(
                f"{base_url}/models",
                timeout=timeout_s,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
            available = resp.status_code == 200

    except Exception as exc:
        logger.debug(
            "Health check fail for '%s': %s. WHERE: _check_single_provider",
            name, exc,
        )
        available = False

    elapsed_ms = (time.perf_counter() - start) * 1000

    with self._lock:
        health = self._health.get(name)
        if health is None:
            health = ProviderHealth()
            self._health[name] = health

        health.last_check = time.time()
        health.available = available
        if available:
            health.last_success = time.time()
            health.consecutive_failures = 0
            health.status = ProviderStatus.AVAILABLE
            self._latency_history[name].append(elapsed_ms)
            _update_percentiles(self, name, health)
        else:
            health.consecutive_failures += 1
            if health.consecutive_failures >= 3:
                health.status = ProviderStatus.UNAVAILABLE
            else:
                health.status = ProviderStatus.DEGRADED

    return available


def _update_percentiles(self, name: str, health: ProviderHealth) -> None:
    """Actualiza los percentiles de latencia para un proveedor.

    Args:
        name: Nombre del proveedor.
        health: Objeto de salud a actualizar.
    """
    history = self._latency_history.get(name)
    if not history or len(history) < 5:
        return

    sorted_latencies = sorted(history)
    n = len(sorted_latencies)
    health.latency_p50 = sorted_latencies[int(n * 0.50)]
    health.latency_p95 = sorted_latencies[int(n * 0.95)]
    health.latency_p99 = sorted_latencies[int(n * 0.99)]

    total_reqs = self._request_counts.get(name, 1)
    errs = self._error_counts.get(name, 0)
    health.error_rate = errs / max(total_reqs, 1)


def _start_health_checks(self) -> None:
    """Inicia el hilo de health checks periodicos en background.

    WHY: Los health checks automaticos aseguran que el estado de
    disponibilidad se mantenga actualizado sin intervencion del
    llamante.
    WHERE: _start_health_checks.
    """
    if self._health_thread is not None and self._health_thread.is_alive():
        return

    self._health_stop.clear()

    def _loop() -> None:
        while not self._health_stop.is_set():
            try:
                health_check(self)
            except Exception as exc:
                logger.error(
                    "Health check background error: %s. "
                    "WHY: El hilo de health check no debe interrumpirse. "
                    "WHERE: _loop en _start_health_checks",
                    exc,
                )
            self._health_stop.wait(HEALTH_CHECK_INTERVAL_S)

    self._health_thread = threading.Thread(
        target=_loop,
        name="mapi-healthcheck",
        daemon=True,
    )
    self._health_thread.start()
    logger.debug(
        "Health check background thread iniciado (intervalo=%ds). "
        "WHERE: _start_health_checks",
        HEALTH_CHECK_INTERVAL_S,
    )


def stop_health_checks(self) -> None:
    """Detiene el hilo de health checks periodicos.

    WHY: Necesario para un shutdown limpio cuando la instancia ya
    no se necesita.
    WHERE: stop_health_checks.
    """
    self._health_stop.set()
    if self._health_thread is not None:
        self._health_thread.join(timeout=5.0)
        logger.debug(
            "Health check thread detenido. WHERE: stop_health_checks",
        )


# ------------------------------------------------------------------
# Cost tracking
# ------------------------------------------------------------------


def _track_cost(self, provider: str, model: str, total_tokens: int) -> float:
    """Registra el costo de una ejecucion y retorna el monto.

    Args:
        provider: Nombre del proveedor.
        model: Nombre del modelo.
        total_tokens: Tokens totales consumidos (input + output).

    Returns:
        Costo estimado en USD.
    """
    cost = _calculate_cost(self, provider, total_tokens)

    with self._lock:
        self._costs[provider] += cost
        self._model_costs[model] += cost
        self._request_counts[provider] += 1

    return cost


def _calculate_cost(self, provider: str, total_tokens: int) -> float:
    """Calcula el costo estimado de una ejecucion.

    Args:
        provider: Nombre del proveedor.
        total_tokens: Tokens totales consumidos.

    Returns:
        Costo estimado en USD.
    """
    with self._lock:
        entry = self._providers.get(provider)
        if entry is None:
            return 0.0
        config = entry["config"]

    input_tokens = int(total_tokens * 0.7)
    output_tokens = total_tokens - input_tokens

    cost_input = (input_tokens / 1000) * config.cost_per_1k_input
    cost_output = (output_tokens / 1000) * config.cost_per_1k_output

    return cost_input + cost_output


def get_total_cost(self, provider: Optional[str] = None) -> float:
    """Retorna el costo total acumulado en USD.

    Args:
        provider: Nombre del proveedor. Si es None, suma todos.

    Returns:
        Costo total en USD.
    """
    with self._lock:
        if provider is not None:
            return self._costs.get(provider, 0.0)
        return sum(self._costs.values())


# ------------------------------------------------------------------
# Budget control
# ------------------------------------------------------------------


def set_budget(self, project: str, limit: float, alert_threshold: float = 0.8) -> None:
    """Establece un presupuesto maximo para un proyecto.

    Args:
        project: Identificador del proyecto.
        limit: Limite maximo en USD.
        alert_threshold: Fraccion del limite para emitir alerta (default 0.8).

    Raises:
        ValueError: Si limit <= 0 o alert_threshold fuera de [0,1].

    WHY: Control de costos por proyecto para evitar sobrecostos no
    planificados.
    WHERE: set_budget en MultiAPIProvider.
    """
    if limit <= 0:
        raise ValueError(
            f"Budget limit debe ser > 0, recibido {limit}. "
            "WHY: Un presupuesto debe ser positivo. "
            "WHERE: set_budget"
        )
    if not 0 <= alert_threshold <= 1:
        raise ValueError(
            f"alert_threshold debe estar entre 0 y 1, recibido {alert_threshold}. "
            "WHY: La fraccion de alerta debe ser un valor valido. "
            "WHERE: set_budget"
        )

    with self._lock:
        from harness.model_router.multi_provider import BudgetLimit
        if project in self._budgets:
            existing = self._budgets[project]
            existing.limit = limit
            existing.alert_threshold = alert_threshold
            logger.info(
                "Budget actualizado para '%s': $%.2f (threshold=%.0f%%). "
                "WHERE: set_budget",
                project, limit, alert_threshold * 100,
            )
        else:
            self._budgets[project] = BudgetLimit(
                limit=limit,
                alert_threshold=alert_threshold,
            )
            logger.info(
                "Budget creado para '%s': $%.2f (threshold=%.0f%%). "
                "WHERE: set_budget",
                project, limit, alert_threshold * 100,
            )


def check_budget(self, project: str) -> Tuple[float, float, bool]:
    """Verifica el estado del presupuesto de un proyecto.

    Args:
        project: Identificador del proyecto.

    Returns:
        Tupla (spent, limit, exceeded) donde exceeded es True si
        spent >= limit.
    """
    with self._lock:
        budget = self._budgets.get(project)
        if budget is None:
            return 0.0, 0.0, False

        exceeded = budget.spent >= budget.limit
        return budget.spent, budget.limit, exceeded


def _allocate_cost_to_project(self, project: str, cost: float) -> None:
    """Asigna un costo a un proyecto y verifica limites.

    Args:
        project: Identificador del proyecto.
        cost: Costo en USD a asignar.
    """
    with self._lock:
        budget = self._budgets.get(project)
        if budget is None:
            return

        budget.spent += cost

        if budget.spent >= budget.limit:
            logger.warning(
                "Proyecto '%s' ha excedido el presupuesto: $%.2f / $%.2f. "
                "WHY: El limite de gasto fue alcanzado. "
                "WHERE: _allocate_cost_to_project",
                project, budget.spent, budget.limit,
            )
        elif budget.spent >= budget.limit * budget.alert_threshold:
            logger.info(
                "Proyecto '%s' ha alcanzado %.0f%% del presupuesto: $%.2f / $%.2f. "
                "WHERE: _allocate_cost_to_project",
                project, budget.alert_threshold * 100, budget.spent, budget.limit,
            )


# ------------------------------------------------------------------
# Metricas y estadisticas
# ------------------------------------------------------------------


def get_stats(self) -> Dict[str, Any]:
    """Retorna estadisticas completas de todos los proveedores.

    Returns:
        Diccionario con metricas por proveedor, incluyendo estado,
        latencias, costos, tasas de error y conteo de requests.
    """
    stats: Dict[str, Any] = {
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

            pstats: Dict[str, Any] = {
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


def get_provider_stats(self, name: str) -> Optional[Dict[str, Any]]:
    """Retorna estadisticas detalladas de un proveedor especifico.

    Args:
        name: Nombre del proveedor.

    Returns:
        Diccionario con metricas del proveedor o None si no existe.
    """
    all_stats = get_stats(self)
    return all_stats.get("providers", {}).get(name)


# ------------------------------------------------------------------
# Helpers internos
# ------------------------------------------------------------------


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
