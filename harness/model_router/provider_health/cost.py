"""Cost tracking y budget control (mixin de funciones).

Extraccion mecanica de las funciones de costos/presupuestos del modulo
original ``harness/model_router/provider_health.py`` (sin cambios de
logica ni firmas).

Cada funcion recibe ``self`` como primer argumento (instancia de
MultiAPIProvider) para acceder a sus atributos internos.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("harness.model_router.provider_health")


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

def get_total_cost(self, provider: str | None = None) -> float:
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

def check_budget(self, project: str) -> tuple[float, float, bool]:
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
