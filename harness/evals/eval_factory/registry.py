"""Registro de evaluaciones por capa del framework.

Submodulo interno del paquete :mod:`harness.evals.eval_factory`.

Extraido de forma mecanica desde ``eval_factory.py`` (regla AGR: archivos
< 500 lineas). Define ``_LAYER_EVAL_REGISTRY``, ``register_layer_evals``,
``run_layer`` y ``run_all``. Los cuerpos son identicos al original; solo
cambia la ubicacion fisica del codigo.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from .models import EvalReport, EvalResult

logger = logging.getLogger(__name__)

# Mapa de capas a funciones de evaluacion builtin
_LAYER_EVAL_REGISTRY: dict[str, list[Callable[[], list[EvalResult]]]] = {}


def register_layer_evals(layer: str, *evals: Callable[[], list[EvalResult]]) -> None:
    """Registra funciones de evaluacion para una capa especifica.

    Args:
        layer: Nombre de la capa (llm, rag, vectordb, agent, mcp, guardrails, integration).
        evals: Una o mas funciones callable que retornan list[EvalResult].

    Raises:
        ValueError: Si layer esta vacio.
        TypeError: Si algun eval no es callable.
    """
    if not layer or not layer.strip():
        raise ValueError("El nombre de la capa no puede estar vacio. Use un identificador del stack.")
    for fn in evals:
        if not callable(fn):
            raise TypeError(
                f"Cada evaluacion debe ser callable, recibio {type(fn).__name__}. "
                "WHAT: tipo invalido en registro | WHERE: register_layer_evals()"
            )
    _LAYER_EVAL_REGISTRY.setdefault(layer, []).extend(evals)
    logger.debug(
        "[EvalFactory] Registradas %d evaluaciones para capa '%s'. WHERE: register_layer_evals()",
        len(evals), layer,
    )


def run_layer(layer: str) -> list[EvalResult]:
    """Ejecuta todas las evaluaciones registradas para una capa especifica.

    Args:
        layer: Nombre de la capa a evaluar (llm, rag, vectordb, agent, mcp, guardrails, integration).

    Returns:
        Lista de EvalResult obtenidos de las evaluaciones de la capa.

    Raises:
        ValueError: Si la capa no tiene evaluaciones registradas.
    """
    evals = _LAYER_EVAL_REGISTRY.get(layer)
    if not evals:
        raise ValueError(
            f"No hay evaluaciones registradas para la capa '{layer}'. "
            "Use register_layer_evals() o builtin_evals para registrarlas. "
            "WHERE: run_layer()"
        )

    results: list[EvalResult] = []
    for eval_fn in evals:
        try:
            partial = eval_fn()
            if isinstance(partial, list):
                results.extend(partial)
            else:
                logger.warning(
                    "[EvalFactory] Funcion '%s' retorno tipo %s, se esperaba list[EvalResult]. "
                    "WHERE: run_layer() | WHAT: tipo de retorno inesperado.",
                    getattr(eval_fn, "__name__", "?"), type(partial).__name__,
                )
        except Exception:
            logger.exception(
                "[EvalFactory] Error ejecutando evaluacion para capa '%s' en funcion '%s'. "
                "WHERE: run_layer() | WHAT: fallo durante evaluacion | WHY: excepcion.",
                layer, getattr(eval_fn, "__name__", "?"),
            )

    return results


def run_all() -> EvalReport:
    """Ejecuta todas las evaluaciones de todas las capas registradas.

    Itera sobre el registro global de capas y recolecta todos los resultados
    en un unico reporte consolidado con recomendaciones.

    Returns:
        EvalReport con los resultados de todas las capas disponibles.
    """
    all_results: list[EvalResult] = []
    start_ts = time.monotonic()

    for layer in list(_LAYER_EVAL_REGISTRY.keys()):
        try:
            layer_results = run_layer(layer)
            all_results.extend(layer_results)
            logger.info(
                "[EvalFactory] Capa '%s': %d evaluaciones completadas. WHERE: run_all()",
                layer, len(layer_results),
            )
        except Exception:
            logger.exception(
                "[EvalFactory] Error ejecutando todas las evaluaciones para capa '%s'. "
                "WHERE: run_all() | WHAT: fallo en capa completa | WHY: excepcion no controlada.",
                layer,
            )

    elapsed = time.monotonic() - start_ts
    return EvalReport.from_results(suite_name="all", results=all_results, elapsed=elapsed)
