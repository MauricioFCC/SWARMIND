"""Health checks periodicos y bajo demanda (mixin de funciones).

Extraccion mecanica de las funciones de health check del modulo original
``harness/model_router/provider_health.py`` (sin cambios de logica ni firmas).

Cada funcion recibe ``self`` como primer argumento (instancia de
MultiAPIProvider) para acceder a sus atributos internos.
"""

from __future__ import annotations

import logging
import os
import threading
import time

from harness.model_router.multi_provider_types import (
    ProviderHealth,
    ProviderStatus,
)

logger = logging.getLogger("harness.model_router.provider_health")

# Intervalo en segundos entre health checks periodicos
HEALTH_CHECK_INTERVAL_S = 30


def health_check(self, provider: str | None = None) -> bool:
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

    except Exception as exc:  # noqa: BLE001
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
            except Exception as exc:  # noqa: BLE001
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
