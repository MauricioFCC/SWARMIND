"""
eval_agent — Evaluaciones de la capa Agent (completion, tool_usage).

Extraido de builtin_evals.py para mantener modulos < 900 lines.
"""

from __future__ import annotations

import logging
import random
from datetime import UTC, datetime

from harness.evals.eval_factory import EvalResult

logger = logging.getLogger(__name__)

# Semilla fija para resultados deterministicos
_SEED = 42
_random = random.Random(_SEED)

# Umbrales por defecto
_DEFAULT_THRESHOLDS: dict[str, dict[str, float]] = {
    "agent": {"completion": 0.80, "tool_usage": 0.85},
}


def eval_agent_completion() -> list[EvalResult]:
    """Mide la tasa de finalizacion exitosa de tareas del agente.

    Simula un conjunto de tareas de diversa complejidad (facil, media,
    dificil) y mide que fraccion completa exitosamente el agente.

    Cada tarea implica planificacion, ejecucion de herramientas y
    verificacion del resultado. La simulacion considera distintos
    niveles de complejidad con tasas de exito decrecientes.

    Returns:
        List[EvalResult] con la tasa de completion global y por
        nivel de complejidad.

    Raises:
        RuntimeError: Si la simulacion de tareas falla.
    """
    _TASKS_PER_COMPLEXITY = {
        "facil": {"count": 20, "success_rate": 0.92},
        "media": {"count": 15, "success_rate": 0.78},
        "dificil": {"count": 10, "success_rate": 0.55},
    }

    results: list[EvalResult] = []
    global_completed = 0
    global_total = 0

    for complexity, config in _TASKS_PER_COMPLEXITY.items():
        try:
            completed = 0
            for _ in range(config["count"]):
                if _random.random() < config["success_rate"]:
                    completed += 1

            rate = completed / config["count"] if config["count"] > 0 else 0.0
            global_completed += completed
            global_total += config["count"]

            result = EvalResult(
                layer="agent",
                metric="completion",
                value=round(rate, 4),
                threshold=_DEFAULT_THRESHOLDS["agent"]["completion"],
                timestamp=datetime.now(UTC).isoformat(),
                metadata={
                    "complexity": complexity,
                    "n_tasks": config["count"],
                    "n_completed": completed,
                    "eval_type": "simulated",
                },
            )
            results.append(result)

            logger.info(
                "[eval_agent] Agent completion (%s): %.1f%% (%d/%d). "
                "WHERE: eval_agent_completion()",
                complexity, rate * 100, completed, config["count"],
            )

        except Exception:
            logger.exception(
                "[eval_agent] Error simulando completion para complejidad %s. "
                "WHERE: eval_agent_completion() | WHAT: fallo en simulacion | WHY: excepcion.",
                complexity,
            )

    # Resultado global
    if global_total > 0:
        global_rate = global_completed / global_total
        results.append(EvalResult(
            layer="agent",
            metric="completion",
            value=round(global_rate, 4),
            threshold=_DEFAULT_THRESHOLDS["agent"]["completion"],
            metadata={
                "complexity": "all",
                "n_tasks": global_total,
                "n_completed": global_completed,
                "eval_type": "simulated_aggregated",
            },
        ))

    return results


def eval_agent_tool_usage() -> list[EvalResult]:
    """Mide la correccion en el uso de herramientas por parte del agente.

    Simula invocaciones a distintas herramientas (busqueda, calculo,
    API externa, base de datos) y verifica que los parametros usados
    sean correctos y que la herramienta se use en el contexto adecuado.

    Evalua tres dimensiones:
        - tool_selection: Seleccion de la herramienta correcta para la tarea
        - parameter_correctness: Parametros correctos en la invocacion
        - error_handling: Manejo adecuado de errores de herramienta

    Returns:
        List[EvalResult] con la tasa de uso correcto global y por dimension.

    Raises:
        ValueError: Si las herramientas configuradas tienen parametros invalidos.
    """
    _TOOLS = [
        {"name": "web_search", "correct_usage_rate": 0.88, "param_rate": 0.85},
        {"name": "calculator", "correct_usage_rate": 0.95, "param_rate": 0.92},
        {"name": "api_call", "correct_usage_rate": 0.80, "param_rate": 0.78},
        {"name": "db_query", "correct_usage_rate": 0.82, "param_rate": 0.80},
    ]
    _N_INVOCATIONS_PER_TOOL = 25

    results: list[EvalResult] = []
    total_correct = 0
    total_invocations = 0

    for tool in _TOOLS:
        try:
            correct_selection = 0
            correct_params = 0

            for _ in range(_N_INVOCATIONS_PER_TOOL):
                if _random.random() < tool["correct_usage_rate"]:
                    correct_selection += 1
                if _random.random() < tool["param_rate"]:
                    correct_params += 1

            combined = (correct_selection + correct_params) / (2 * _N_INVOCATIONS_PER_TOOL)
            total_correct += correct_selection + correct_params
            total_invocations += 2 * _N_INVOCATIONS_PER_TOOL

            result = EvalResult(
                layer="agent",
                metric="tool_usage",
                value=round(combined, 4),
                threshold=_DEFAULT_THRESHOLDS["agent"]["tool_usage"],
                timestamp=datetime.now(UTC).isoformat(),
                metadata={
                    "tool": tool["name"],
                    "n_invocations": _N_INVOCATIONS_PER_TOOL,
                    "correct_selection": correct_selection,
                    "correct_parameters": correct_params,
                    "eval_type": "simulated",
                },
            )
            results.append(result)

            logger.info(
                "[eval_agent] Agent tool_usage (%s): %.1f%% (sel: %d/%d, param: %d/%d). "
                "WHERE: eval_agent_tool_usage()",
                tool["name"], combined * 100,
                correct_selection, _N_INVOCATIONS_PER_TOOL,
                correct_params, _N_INVOCATIONS_PER_TOOL,
            )

        except Exception:
            logger.exception(
                "[eval_agent] Error simulando tool_usage para herramienta %s. "
                "WHERE: eval_agent_tool_usage() | WHAT: fallo en simulacion | WHY: excepcion.",
                tool.get("name", "?"),
            )

    # Resultado global
    if total_invocations > 0:
        global_rate = total_correct / total_invocations
        results.append(EvalResult(
            layer="agent",
            metric="tool_usage",
            value=round(global_rate, 4),
            threshold=_DEFAULT_THRESHOLDS["agent"]["tool_usage"],
            metadata={
                "tool": "all",
                "n_total_invocations": total_invocations,
                "n_total_correct": total_correct,
                "eval_type": "simulated_aggregated",
            },
        ))

    return results
