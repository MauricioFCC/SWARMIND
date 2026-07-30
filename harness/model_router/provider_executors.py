"""Provider executors - OpenAI, Anthropic, Google implementations."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

from harness.model_router.multi_provider_types import (
    ExecutionResult,
    ProviderConfig,
    ProviderHealth,
)

def execute_openai_compat(
    self,
    config: ProviderConfig,
    api_key: str,
    model: str,
    prompt: str,
    max_tokens: int,
) -> ExecutionResult:
    """Ejecuta contra APIs OpenAI-compatibles (OpenAI, Mistral, DeepSeek, etc.).

    Args:
        config: Configuración del proveedor.
        api_key: API key.
        model: Modelo.
        prompt: Prompt.
        max_tokens: Límite de tokens.

    Returns:
        ExecutionResult con la respuesta.
    """
    import requests

    base_url = config.base_url.rstrip("/")
    timeout_s = config.timeout_ms / 1000.0

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    headers.update(config.headers_extra)

    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            json=payload,
            headers=headers,
            timeout=timeout_s,
        )
        resp.raise_for_status()
        data = resp.json()

        content = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        # Estimación de tokens desde la respuesta o cálculo
        usage = data.get("usage", {})
        total_tokens = usage.get("total_tokens", 0)

        return ExecutionResult(
            success=True,
            output=content,
            source="cloud",
            model=model,
            duration_ms=0.0,
            tokens_used=total_tokens,
        )

    except requests.exceptions.Timeout as exc:
        return ExecutionResult(
            success=False,
            output="",
            source="cloud",
            model=model,
            duration_ms=0.0,
            error=(
                f"Timeout ({timeout_s}s) en provider '{config.name}': {exc}. "
                "WHY: El servidor no respondió dentro del límite. "
                "WHERE: _execute_openai_compat"
            ),
        )
    except requests.exceptions.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else 0
        error_detail = ""
        if exc.response is not None:
            try:
                error_detail = exc.response.json().get("error", {}).get("message", "")
            except Exception:
                error_detail = exc.response.text[:200]

        return ExecutionResult(
            success=False,
            output="",
            source="cloud",
            model=model,
            duration_ms=0.0,
            error=(
                f"HTTP {status_code} en '{config.name}': {error_detail}. "
                "WHY: La API rechazó la solicitud. "
                "WHERE: _execute_openai_compat"
            ),
        )
    except Exception as exc:
        return ExecutionResult(
            success=False,
            output="",
            source="cloud",
            model=model,
            duration_ms=0.0,
            error=(
                f"Error en provider '{config.name}': {exc}. "
                f"WHY: Fallo no categorizado en la comunicación HTTP. "
                f"WHERE: _execute_openai_compat"
            ),
        )

def execute_anthropic(
    self,
    config: ProviderConfig,
    api_key: str,
    model: str,
    prompt: str,
    max_tokens: int,
) -> ExecutionResult:
    """Ejecuta contra la API de Anthropic (Claude).

    Args:
        config: Configuración del proveedor.
        api_key: API key de Anthropic.
        model: Modelo (ej: "claude-3-5-sonnet-20241022").
        prompt: Prompt de entrada.
        max_tokens: Máximo de tokens de salida.

    Returns:
        ExecutionResult con la respuesta.
    """
    import requests

    base_url = config.base_url.rstrip("/")
    timeout_s = config.timeout_ms / 1000.0

    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    headers.update(config.headers_extra)

    try:
        resp = requests.post(
            f"{base_url}/messages",
            json=payload,
            headers=headers,
            timeout=timeout_s,
        )
        resp.raise_for_status()
        data = resp.json()

        content = ""
        content_blocks = data.get("content", [])
        if content_blocks:
            # Anthropic puede devolver múltiples bloques (text, tool_use)
            for block in content_blocks:
                if block.get("type") == "text":
                    content += block.get("text", "")

        # Anthropic reporta usage.input_tokens + usage.output_tokens
        usage = data.get("usage", {})
        total_tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)

        return ExecutionResult(
            success=True,
            output=content,
            source="cloud",
            model=model,
            duration_ms=0.0,
            tokens_used=total_tokens,
        )

    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else 0
        detail = ""
        if exc.response is not None:
            try:
                err = exc.response.json()
                detail = err.get("error", {}).get("message", str(err))
            except Exception:
                detail = exc.response.text[:200]
        return ExecutionResult(
            success=False,
            output="",
            source="cloud",
            model=model,
            duration_ms=0.0,
            error=(
                f"Anthropic HTTP {status}: {detail}. "
                "WHY: La API de Anthropic rechazó la solicitud. "
                "WHERE: _execute_anthropic"
            ),
        )
    except Exception as exc:
        return ExecutionResult(
            success=False,
            output="",
            source="cloud",
            model=model,
            duration_ms=0.0,
            error=(
                f"Anthropic error: {exc}. "
                "WHY: Fallo en la comunicación con Anthropic. "
                "WHERE: _execute_anthropic"
            ),
        )

def execute_google(
    self,
    config: ProviderConfig,
    api_key: str,
    model: str,
    prompt: str,
    max_tokens: int,
) -> ExecutionResult:
    """Ejecuta contra la API de Google Gemini.

    Args:
        config: Configuración del proveedor.
        api_key: API key de Google.
        model: Modelo (ej: "gemini-1.5-pro").
        prompt: Prompt de entrada.
        max_tokens: Máximo de tokens de salida.

    Returns:
        ExecutionResult con la respuesta.
    """
    import requests

    base_url = config.base_url.rstrip("/")
    timeout_s = config.timeout_ms / 1000.0

    # Gemini usa generateContent con estructura específica
    url = f"{base_url}/v1/models/{model}:generateContent"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": max_tokens,
        },
    }
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json",
    }
    headers.update(config.headers_extra)

    try:
        resp = requests.post(
            url, json=payload, headers=headers, timeout=timeout_s,
        )
        resp.raise_for_status()
        data = resp.json()

        # Extraer texto de la respuesta Gemini
        content = ""
        candidates = data.get("candidates", [])
        if candidates:
            content_parts = candidates[0].get("content", {}).get("parts", [])
            for part in content_parts:
                content += part.get("text", "")

        # Gemini puede reportar usageMetadata
        usage = data.get("usageMetadata", {})
        total_tokens = usage.get("totalTokenCount", 0)

        return ExecutionResult(
            success=True,
            output=content,
            source="cloud",
            model=model,
            duration_ms=0.0,
            tokens_used=total_tokens,
        )

    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else 0
        detail = ""
        if exc.response is not None:
            try:
                err = exc.response.json()
                detail = err.get("error", {}).get("message", str(err))
            except Exception:
                detail = exc.response.text[:200]
        return ExecutionResult(
            success=False,
            output="",
            source="cloud",
            model=model,
            duration_ms=0.0,
            error=(
                f"Google Gemini HTTP {status}: {detail}. "
                "WHY: La API de Gemini rechazó la solicitud. "
                "WHERE: _execute_google"
            ),
        )
    except Exception as exc:
        return ExecutionResult(
            success=False,
            output="",
            source="cloud",
            model=model,
            duration_ms=0.0,
            error=(
                f"Google Gemini error: {exc}. "
                "WHY: Fallo en la comunicación con Gemini. "
                "WHERE: _execute_google"
            ),
        )

# ------------------------------------------------------------------
# Health checks
# ------------------------------------------------------------------



def health_check(self, provider: Optional[str] = None) -> bool:
    """Ejecuta health check sobre uno o todos los proveedores.

    Args:
        provider: Nombre del proveedor. Si es None, verifica todos.

    Returns:
        True si el/los proveedor(es) están disponibles.

    WHY: Permite verificar disponibilidad bajo demanda, además de
    los chequeos periódicos en background.
    WHERE: health_check en MultiAPIProvider.
    """
    if provider is not None:
        return self._check_single_provider(provider)

    # Verificar todos los proveedores
    all_ok = True
    with self._lock:
        names = list(self._providers.keys())
    for pname in names:
        ok = self._check_single_provider(pname)
        all_ok = all_ok and ok
    return all_ok

def _check_single_provider(self, name: str) -> bool:
    """Verifica disponibilidad de un proveedor individual.

    Realiza una solicitud liviana (listado de modelos o ping) para
    determinar si el proveedor responde.

    Args:
        name: Nombre del proveedor.

    Returns:
        True si el proveedor está disponible.
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

        timeout_s = max(5.0, config.timeout_ms / 2000.0)  # mitad del timeout

        # Intentar obtener lista de modelos (liviano si el endpoint
        # soporta GET /models, o fallback a un POST mínimo)
        base_url = config.base_url.rstrip("/")
        api_key = os.environ.get(config.api_key_env, "")

        if config.name.lower() == "anthropic":
            # Anthropic no tiene GET /models pública sencilla; hacemos GET /
            resp = requests.get(
                f"{base_url}/", timeout=timeout_s,
                headers={"x-api-key": api_key},
            )
            available = resp.status_code < 500

        elif config.name.lower() == "google":
            # Google tiene GET /v1/models
            resp = requests.get(
                f"{base_url}/v1/models",
                timeout=timeout_s,
                headers={"x-goog-api-key": api_key},
            )
            available = resp.status_code == 200

        else:
            # OpenAI-compatible: GET /models
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
            # Actualizar latencia con la del health check
            self._latency_history[name].append(elapsed_ms)
            self._update_percentiles(name, health)
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

    # Calcular error rate en ventana
    total_reqs = self._request_counts.get(name, 1)
    errs = self._error_counts.get(name, 0)
    health.error_rate = errs / max(total_reqs, 1)

def _start_health_checks(self) -> None:
    """Inicia el hilo de health checks periódicos en background.

    WHY: Los health checks automáticos aseguran que el estado de
    disponibilidad se mantenga actualizado sin intervención del
    llamante.
    WHERE: _start_health_checks.
    """
    if self._health_thread is not None and self._health_thread.is_alive():
        return

    self._health_stop.clear()

    def _loop() -> None:
        while not self._health_stop.is_set():
            try:
                self.health_check()
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
    """Detiene el hilo de health checks periódicos.

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
# Round-robin y selección de proveedor
# ------------------------------------------------------------------

def _find_provider_for_model(self, model: str) -> Optional[str]:
    """Busca el proveedor óptimo para un modelo.

    Prioriza por tier (premium > standard > budget) y hace round-robin
    entre proveedores del mismo tier.

    Args:
        model: Nombre del modelo a buscar.

    Returns:
        Nombre del proveedor seleccionado, o None si no se encuentra.
    """
    with self._lock:
        # Agrupar proveedores por tier
        candidates_by_tier: Dict[str, List[str]] = defaultdict(list)
        for pname, entry in self._providers.items():
            cfg = entry["config"]
            health = self._health.get(pname)
            if health is not None and not health.available:
                continue
            if model in cfg.models:
                candidates_by_tier[cfg.tier].append(pname)

        # Probar tiers en orden
        tier_order = [
            ProviderTier.PREMIUM.value,
            ProviderTier.STANDARD.value,
            ProviderTier.BUDGET.value,
        ]

        for tier in tier_order:
            candidates = candidates_by_tier.get(tier, [])
            if not candidates:
                continue

            # Round-robin dentro del tier
            idx = self._rr_indices[tier] % len(candidates)
            self._rr_indices[tier] = idx + 1
            return candidates[idx]

    return None

def _get_other_providers_for_model(
    self, model: str, exclude: str,
) -> List[str]:
    """Retorna otros proveedores que ofrecen el modelo, ordenados por tier.

    Args:
        model: Modelo a buscar.
        exclude: Proveedor a excluir (el primario).

    Returns:
        Lista ordenada de proveedores alternativos.
    """
    candidates: List[Tuple[str, int]] = []
    tier_rank = {
        ProviderTier.PREMIUM.value: 0,
        ProviderTier.STANDARD.value: 1,
        ProviderTier.BUDGET.value: 2,
    }

    with self._lock:
        for pname, entry in self._providers.items():
            if pname == exclude:
                continue
            cfg = entry["config"]
            health = self._health.get(pname)
            if health is not None and not health.available:
                continue
            if model in cfg.models:
                rank = tier_rank.get(cfg.tier, 99)
                candidates.append((pname, rank))

    # Ordenar por tier (menor rank = mejor tier)
    candidates.sort(key=lambda x: x[1])
    return [c[0] for c in candidates]

# ------------------------------------------------------------------
# Cost tracking
# ------------------------------------------------------------------

def _track_cost(self, provider: str, model: str, total_tokens: int) -> float:
    """Registra el costo de una ejecución y retorna el monto.

    Distribuye proporcionalmente entre input/output estimando una
    relación 1:3 (output cuesta ~3x más por token).

    Args:
        provider: Nombre del proveedor.
        model: Nombre del modelo.
        total_tokens: Tokens totales consumidos (input + output).

    Returns:
        Costo estimado en USD.
    """
    cost = self._calculate_cost(provider, total_tokens)

    with self._lock:
        self._costs[provider] += cost
        self._model_costs[model] += cost
        self._request_counts[provider] += 1

    return cost

def _calculate_cost(self, provider: str, total_tokens: int) -> float:
    """Calcula el costo estimado de una ejecución.

    Asume una proporción 70% input / 30% output como estimación
    cuando no se tiene el detalle.

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

    # Estimación: ~70% input, ~30% output
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
    """Establece un presupuesto máximo para un proyecto.

    Args:
        project: Identificador del proyecto.
        limit: Límite máximo en USD.
        alert_threshold: Fracción del límite para emitir alerta (default 0.8).

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
            "WHY: La fracción de alerta debe ser un valor válido. "
            "WHERE: set_budget"
        )

    with self._lock:
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
    """Asigna un costo a un proyecto y verifica límites.

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
                "WHY: El límite de gasto fue alcanzado. "
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
# Métricas y estadísticas
# ------------------------------------------------------------------

def get_stats(self) -> Dict[str, Any]:
    """Retorna estadísticas completas de todos los proveedores.

    Returns:
        Diccionario con métricas por proveedor, incluyendo estado,
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

    # Determinar estado global
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
    """Retorna estadísticas detalladas de un proveedor específico.

    Args:
        name: Nombre del proveedor.

    Returns:
        Diccionario con métricas del proveedor o None si no existe.
    """
    all_stats = self.get_stats()
    return all_stats.get("providers", {}).get(name)

# ------------------------------------------------------------------
# Helpers internos
# ------------------------------------------------------------------

def _record_success(self, provider: str, latency_ms: float) -> None:
    """Registra una ejecución exitosa y actualiza métricas de latencia.

    Args:
        provider: Nombre del proveedor.
        latency_ms: Latencia de la ejecución en milisegundos.
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
            self._update_percentiles(provider, health)

def _record_error(self, provider: str, error: str) -> None:
    """Registra un error de ejecución.

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

def __del__(self) -> None:
    """Cleanup: detiene health checks al destruir la instancia."""
    self.stop_health_checks()


# ===================================================================
# ModelRouter (MEJORADO) — mantiene compatibilidad total hacia atrás
# ===================================================================


