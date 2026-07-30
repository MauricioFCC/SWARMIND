# -*- coding: utf-8 -*-
"""
builtin_evals — Evaluaciones incorporadas para las 7 capas del stack AGENTIC.

Cada funcion implementa una evaluacion concreta que produce una lista de
EvalResult con metricas cuantitativas. Las evaluaciones son deterministicas
(simuladas con datos sinteticos) y pueden ser reemplazadas por implementaciones
reales que conecten con modelos, bases de datos o agentes en produccion.

Evaluaciones disponibles:
    LLM:
        eval_llm_accuracy()   — Mide exactitud de respuestas simuladas
        eval_llm_latency()    — Mide tiempos de respuesta P50/P95/P99
        eval_llm_cost()       — Estima costo por token de distintos modelos

    RAG:
        eval_rag_recall()         — Mide recuperacion de documentos relevantes
        eval_rag_faithfulness()   — Mide fidelidad de respuestas al contexto

    Agent:
        eval_agent_completion()   — Mide tasa de exito en finalizacion de tareas
        eval_agent_tool_usage()   — Mide uso correcto de herramientas
"""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

from harness.evals.eval_factory import EvalResult, register_layer_evals

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Semilla fija para resultados deterministicos
# ---------------------------------------------------------------------------
_SEED = 42
_random = random.Random(_SEED)

# ---------------------------------------------------------------------------
# Umbrales por defecto por capa y metrica
# ---------------------------------------------------------------------------
_DEFAULT_THRESHOLDS: Dict[str, Dict[str, float]] = {
    "llm": {"accuracy": 0.85, "latency": 2.0, "cost": 0.005},
    "rag": {"recall": 0.80, "faithfulness": 0.85},
    "vectordb": {"recall@k": 0.75, "latency": 0.5, "index_quality": 0.80},
    "agent": {"completion": 0.80, "tool_usage": 0.85},
    "mcp": {"availability": 0.95, "latency": 1.0, "error_rate": 0.05},
    "guardrails": {"detection_rate": 0.90, "false_positive": 0.10},
    "integration": {"success_rate": 0.90, "latency": 5.0},
}

# ---------------------------------------------------------------------------
# LLM Evals
# ---------------------------------------------------------------------------


def eval_llm_accuracy() -> List[EvalResult]:
    """Evalua la exactitud (accuracy) del LLM en respuestas simuladas.

    Simula un conjunto de N preguntas con respuestas esperadas y mide
    cuantas respuestas generadas son correctas. Usa un generador
    deterministico basado en semilla fija.

    La simulacion considera diferentes variantes de prompt y modelos
    para producir una distribucion realista de aciertos.

    Returns:
        List[EvalResult] con un resultado de accuracy global y uno por
        variante de prompt si hay diferencias significativas.

    Raises:
        RuntimeError: Si el generador aleatorio falla al producir valores.
    """
    _N_QUESTIONS = 50
    _MODEL_VARIANTS = [
        {"model": "gpt-4o", "prompt": "estandar", "base_acc": 0.92},
        {"model": "gpt-4o-mini", "prompt": "estandar", "base_acc": 0.88},
        {"model": "gpt-4o", "prompt": "few-shot", "base_acc": 0.95},
    ]

    results: List[EvalResult] = []
    total_correct = 0
    total_questions = 0

    for variant in _MODEL_VARIANTS:
        try:
            correct = 0
            for _ in range(_N_QUESTIONS):
                # Simula si la respuesta es correcta basado en la exactitud base
                if _random.random() < variant["base_acc"]:
                    correct += 1

            accuracy = correct / _N_QUESTIONS
            total_correct += correct
            total_questions += _N_QUESTIONS

            result = EvalResult(
                layer="llm",
                metric="accuracy",
                value=round(accuracy, 4),
                threshold=_DEFAULT_THRESHOLDS["llm"]["accuracy"],
                timestamp=datetime.now(timezone.utc).isoformat(),
                metadata={
                    "model": variant["model"],
                    "prompt_type": variant["prompt"],
                    "n_questions": _N_QUESTIONS,
                    "n_correct": correct,
                    "eval_type": "simulated",
                },
            )
            results.append(result)

            logger.info(
                "[builtin_evals] LLM accuracy %s/%s: %.1f%% (umbral: %.0f%%). "
                "WHERE: eval_llm_accuracy()",
                variant["model"], variant["prompt"], accuracy * 100,
                _DEFAULT_THRESHOLDS["llm"]["accuracy"] * 100,
            )

        except Exception as exc:
            logger.exception(
                "[builtin_evals] Error simulando accuracy para variante %s: %s. "
                "WHERE: eval_llm_accuracy() | WHAT: fallo en variante de modelo | WHY: excepcion.",
                variant.get("model", "?"), exc,
            )

    # Resultado global agregado
    if total_questions > 0:
        global_acc = total_correct / total_questions
        results.append(EvalResult(
            layer="llm",
            metric="accuracy",
            value=round(global_acc, 4),
            threshold=_DEFAULT_THRESHOLDS["llm"]["accuracy"],
            metadata={
                "model": "all",
                "n_questions": total_questions,
                "n_correct": total_correct,
                "eval_type": "simulated_aggregated",
            },
        ))

    return results


def eval_llm_latency() -> List[EvalResult]:
    """Mide los percentiles de latencia P50, P95 y P99 del LLM.

    Simula tiempos de respuesta para distintos modelos con distribuciones
    realistas (log-normal) que replican el comportamiento observado en
    sistemas de produccion.

    Incluye latencia de red, procesamiento y generacion de tokens.

    Returns:
        List[EvalResult] con tres resultados: P50, P95 y P99 en segundos.

    Raises:
        RuntimeError: Si no se pueden calcular los percentiles.
    """
    _N_SAMPLES = 100
    _MODEL_LATENCY_PARAMS = {
        "gpt-4o": {"mean": 1.2, "std": 0.4},
        "gpt-4o-mini": {"mean": 0.6, "std": 0.2},
        "claude-3-opus": {"mean": 1.8, "std": 0.6},
    }

    results: List[EvalResult] = []

    for model_name, params in _MODEL_LATENCY_PARAMS.items():
        try:
            samples: List[float] = []
            for _ in range(_N_SAMPLES):
                # Distribucion log-normal para simular latencia realista
                sample = _random.lognormvariate(params["mean"], params["std"])
                samples.append(round(sample, 4))

            samples.sort()
            p50 = samples[int(len(samples) * 0.50)]
            p95 = samples[int(len(samples) * 0.95)]
            p99 = samples[int(len(samples) * 0.99)]

            for percentile_name, value in [("P50", p50), ("P95", p95), ("P99", p99)]:
                metric_name = f"latency_{percentile_name.lower()}"
                result = EvalResult(
                    layer="llm",
                    metric=metric_name,
                    value=value,
                    threshold=_DEFAULT_THRESHOLDS["llm"]["latency"],
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    metadata={
                        "model": model_name,
                        "percentile": percentile_name,
                        "n_samples": _N_SAMPLES,
                        "unit": "seconds",
                        "eval_type": "simulated",
                    },
                )
                results.append(result)

            logger.info(
                "[builtin_evals] LLM latency %s: P50=%.2fs P95=%.2fs P99=%.2fs. "
                "WHERE: eval_llm_latency()",
                model_name, p50, p95, p99,
            )

        except Exception as exc:
            logger.exception(
                "[builtin_evals] Error simulando latencia para modelo %s: %s. "
                "WHERE: eval_llm_latency() | WHAT: fallo en generacion de muestras | WHY: excepcion.",
                model_name, exc,
            )

    return results


def eval_llm_cost() -> List[EvalResult]:
    """Estima el costo por token de distintos modelos del LLM.

    Calcula el costo estimado por consulta basado en tokens de entrada
    y salida, usando las tarifas publicas de cada proveedor (OpenAI,
    Anthropic, etc.) simuladas con valores realistas.

    Returns:
        List[EvalResult] con el costo estimado por modelo y un promedio global.

    Raises:
        ValueError: Si los parametros de costo son invalidos.
    """
    _PRICING_PER_MODEL = {
        "gpt-4o": {"input": 2.50e-6, "output": 10.00e-6},    # $2.50/$10.00 por 1M tokens
        "gpt-4o-mini": {"input": 0.15e-6, "output": 0.60e-6},  # $0.15/$0.60 por 1M tokens
        "claude-3-opus": {"input": 15.00e-6, "output": 75.00e-6},  # $15/$75 por 1M tokens
    }
    _AVG_INPUT_TOKENS = 500
    _AVG_OUTPUT_TOKENS = 200

    results: List[EvalResult] = []
    total_cost = 0.0

    for model_name, pricing in _PRICING_PER_MODEL.items():
        try:
            input_cost = _AVG_INPUT_TOKENS * pricing["input"]
            output_cost = _AVG_OUTPUT_TOKENS * pricing["output"]
            total = input_cost + output_cost
            total_cost += total

            result = EvalResult(
                layer="llm",
                metric="cost",
                value=round(total, 6),
                threshold=_DEFAULT_THRESHOLDS["llm"]["cost"],
                timestamp=datetime.now(timezone.utc).isoformat(),
                metadata={
                    "model": model_name,
                    "input_tokens": _AVG_INPUT_TOKENS,
                    "output_tokens": _AVG_OUTPUT_TOKENS,
                    "input_cost": round(input_cost, 8),
                    "output_cost": round(output_cost, 8),
                    "currency": "USD",
                    "eval_type": "estimated",
                },
            )
            results.append(result)

            logger.info(
                "[builtin_evals] LLM cost %s: $%.6f/consulta (input: %d, output: %d tokens). "
                "WHERE: eval_llm_cost()",
                model_name, total, _AVG_INPUT_TOKENS, _AVG_OUTPUT_TOKENS,
            )

        except Exception as exc:
            logger.exception(
                "[builtin_evals] Error calculando costo para modelo %s: %s. "
                "WHERE: eval_llm_cost() | WHAT: fallo en estimacion | WHY: excepcion.",
                model_name, exc,
            )

    # Costo promedio global
    if results:
        avg_cost = total_cost / len(results)
        results.append(EvalResult(
            layer="llm",
            metric="cost",
            value=round(avg_cost, 6),
            threshold=_DEFAULT_THRESHOLDS["llm"]["cost"],
            metadata={
                "model": "average",
                "eval_type": "estimated_aggregated",
            },
        ))

    return results


# ---------------------------------------------------------------------------
# RAG Evals
# ---------------------------------------------------------------------------


def eval_rag_recall() -> List[EvalResult]:
    """Mide la capacidad de recuperacion (recall) del sistema RAG.

    Simula un conjunto de consultas con documentos relevantes conocidos
    y mide que fraccion de los documentos relevantes son recuperados
    correctamente en los top-k resultados.

    La simulacion considera distintos valores de k (3, 5, 10) y
    diferentes niveles de ruido en la coleccion de documentos.

    Returns:
        List[EvalResult] con recall@k para cada k evaluado.

    Raises:
        RuntimeError: Si la generacion de consultas simuladas falla.
    """
    _N_QUERIES = 30
    _TOP_K_VALUES = [3, 5, 10]
    _TOTAL_DOCS = 100
    _RELEVANT_PER_QUERY = 5

    results: List[EvalResult] = []

    for k in _TOP_K_VALUES:
        try:
            total_relevant = 0
            total_retrieved_relevant = 0

            for _ in range(_N_QUERIES):
                relevant_docs = _random.sample(range(_TOTAL_DOCS), _RELEVANT_PER_QUERY)
                # Simula cuantos documentos relevantes caen en top-k
                retrieved = _random.sample(range(_TOTAL_DOCS), min(k, _TOTAL_DOCS))
                retrieved_set = set(retrieved)
                hits = sum(1 for d in relevant_docs if d in retrieved_set)

                total_relevant += len(relevant_docs)
                total_retrieved_relevant += hits

            recall = total_retrieved_relevant / total_relevant if total_relevant > 0 else 0.0

            result = EvalResult(
                layer="rag",
                metric="recall",
                value=round(recall, 4),
                threshold=_DEFAULT_THRESHOLDS["rag"]["recall"],
                timestamp=datetime.now(timezone.utc).isoformat(),
                metadata={
                    "top_k": k,
                    "n_queries": _N_QUERIES,
                    "total_docs": _TOTAL_DOCS,
                    "relevant_per_query": _RELEVANT_PER_QUERY,
                    "hits": total_retrieved_relevant,
                    "total_relevant": total_relevant,
                    "eval_type": "simulated",
                },
            )
            results.append(result)

            logger.info(
                "[builtin_evals] RAG recall@%d: %.1f%% (umbral: %.0f%%). "
                "WHERE: eval_rag_recall()",
                k, recall * 100, _DEFAULT_THRESHOLDS["rag"]["recall"] * 100,
            )

        except Exception as exc:
            logger.exception(
                "[builtin_evals] Error simulando recall para k=%d: %s. "
                "WHERE: eval_rag_recall() | WHAT: fallo en simulacion | WHY: excepcion.",
                k, exc,
            )

    return results


def eval_rag_faithfulness() -> List[EvalResult]:
    """Mide la fidelidad de las respuestas del LLM al contexto recuperado.

    Simula escenarios donde el LLM debe responder basado en documentos
    recuperados. Mide cuantas respuestas contienen informacion presente
    en los documentos (faithfulness) vs. alucinaciones.

    Evalua tres niveles de fidelidad: alta (respuesta correcta),
    media (respuesta parcialmente correcta) y baja (alucinacion).

    Returns:
        List[EvalResult] con la metrica de faithfulness global y por nivel.

    Raises:
        ValueError: Si los parametros de simulacion son inconsistentes.
    """
    _N_SCENARIOS = 40
    _LEVELS = {
        "high": {"prob": 0.75, "faithfulness": 0.95},
        "medium": {"prob": 0.15, "faithfulness": 0.65},
        "low": {"prob": 0.10, "faithfulness": 0.30},
    }

    results: List[EvalResult] = []
    weighted_sum = 0.0
    total_count = 0

    for level_name, level_config in _LEVELS.items():
        try:
            n_cases = int(_N_SCENARIOS * level_config["prob"])
            faithfulness = level_config["faithfulness"]

            for _ in range(n_cases):
                weighted_sum += faithfulness
                total_count += 1

            result = EvalResult(
                layer="rag",
                metric="faithfulness",
                value=faithfulness,
                threshold=_DEFAULT_THRESHOLDS["rag"]["faithfulness"],
                timestamp=datetime.now(timezone.utc).isoformat(),
                metadata={
                    "level": level_name,
                    "n_scenarios": n_cases,
                    "description": f"Fidelidad {level_name}: {faithfulness:.0%}",
                    "eval_type": "simulated",
                },
            )
            results.append(result)

        except Exception as exc:
            logger.exception(
                "[builtin_evals] Error simulando faithfulness para nivel %s: %s. "
                "WHERE: eval_rag_faithfulness() | WHAT: fallo en nivel | WHY: excepcion.",
                level_name, exc,
            )

    # Resultado global ponderado
    if total_count > 0:
        global_faithfulness = weighted_sum / total_count
        results.append(EvalResult(
            layer="rag",
            metric="faithfulness",
            value=round(global_faithfulness, 4),
            threshold=_DEFAULT_THRESHOLDS["rag"]["faithfulness"],
            metadata={
                "level": "weighted_average",
                "n_total": total_count,
                "eval_type": "simulated_aggregated",
            },
        ))

    return results


# ---------------------------------------------------------------------------
# Agent Evals
# ---------------------------------------------------------------------------


def eval_agent_completion() -> List[EvalResult]:
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

    results: List[EvalResult] = []
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
                timestamp=datetime.now(timezone.utc).isoformat(),
                metadata={
                    "complexity": complexity,
                    "n_tasks": config["count"],
                    "n_completed": completed,
                    "eval_type": "simulated",
                },
            )
            results.append(result)

            logger.info(
                "[builtin_evals] Agent completion (%s): %.1f%% (%d/%d). "
                "WHERE: eval_agent_completion()",
                complexity, rate * 100, completed, config["count"],
            )

        except Exception as exc:
            logger.exception(
                "[builtin_evals] Error simulando completion para complejidad %s: %s. "
                "WHERE: eval_agent_completion() | WHAT: fallo en simulacion | WHY: excepcion.",
                complexity, exc,
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


def eval_agent_tool_usage() -> List[EvalResult]:
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

    results: List[EvalResult] = []
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
                timestamp=datetime.now(timezone.utc).isoformat(),
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
                "[builtin_evals] Agent tool_usage (%s): %.1f%% (sel: %d/%d, param: %d/%d). "
                "WHERE: eval_agent_tool_usage()",
                tool["name"], combined * 100,
                correct_selection, _N_INVOCATIONS_PER_TOOL,
                correct_params, _N_INVOCATIONS_PER_TOOL,
            )

        except Exception as exc:
            logger.exception(
                "[builtin_evals] Error simulando tool_usage para herramienta %s: %s. "
                "WHERE: eval_agent_tool_usage() | WHAT: fallo en simulacion | WHY: excepcion.",
                tool.get("name", "?"), exc,
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


# ---------------------------------------------------------------------------
# VectorDB Eval
# ---------------------------------------------------------------------------


def eval_vectordb_recall() -> List[EvalResult]:
    """Evalua recall@k del indice vectorial.

    Simula busquedas de vectores cercanos en un espacio de 384 dimensiones
    y mide cuantos de los k vecinos mas cercanos reales son recuperados.

    Returns:
        List[EvalResult] con recall@k para k=5 y k=10.
    """
    _N_QUERIES = 20
    _K_VALUES = [5, 10]
    _VECTOR_DIM = 384

    results: List[EvalResult] = []

    for k in _K_VALUES:
        try:
            total_expected = 0
            total_found = 0

            for _ in range(_N_QUERIES):
                # Simula cuantos de los k reales son recuperados
                expected = min(k, _VECTOR_DIM)
                # Ruido en la recuperacion: entre 60% y 95% de acierto
                hit_rate = _random.uniform(0.60, 0.95)
                found = int(expected * hit_rate)

                total_expected += expected
                total_found += found

            recall = total_found / total_expected if total_expected > 0 else 0.0

            result = EvalResult(
                layer="vectordb",
                metric="recall@k",
                value=round(recall, 4),
                threshold=_DEFAULT_THRESHOLDS["vectordb"]["recall@k"],
                timestamp=datetime.now(timezone.utc).isoformat(),
                metadata={
                    "top_k": k,
                    "n_queries": _N_QUERIES,
                    "vector_dim": _VECTOR_DIM,
                    "eval_type": "simulated",
                },
            )
            results.append(result)

        except Exception as exc:
            logger.exception(
                "[builtin_evals] Error simulando recall@k para k=%d: %s. "
                "WHERE: eval_vectordb_recall() | WHAT: fallo en simulacion | WHY: excepcion.",
                k, exc,
            )

    return results


def eval_vectordb_latency() -> List[EvalResult]:
    """Mide latencia de busqueda en la base de datos vectorial.

    Simula tiempos de busqueda ANN (Approximate Nearest Neighbors)
    para diferentes tamanos de indice.

    Returns:
        List[EvalResult] con latencia promedio por tamano de indice.
    """
    _INDEX_SIZES = [1000, 10000, 100000]
    _LATENCY_BASE = {"1000": 0.005, "10000": 0.015, "100000": 0.050}

    results: List[EvalResult] = []

    for size in _INDEX_SIZES:
        try:
            # Simula latencia con variacion realista
            base = _LATENCY_BASE.get(str(size), 0.01)
            latency = _random.uniform(base * 0.8, base * 1.2)

            result = EvalResult(
                layer="vectordb",
                metric="latency",
                value=round(latency, 6),
                threshold=_DEFAULT_THRESHOLDS["vectordb"]["latency"],
                timestamp=datetime.now(timezone.utc).isoformat(),
                metadata={
                    "index_size": size,
                    "unit": "seconds",
                    "eval_type": "simulated",
                },
            )
            results.append(result)

        except Exception as exc:
            logger.exception(
                "[builtin_evals] Error simulando latencia vectordb para tamano %d: %s. "
                "WHERE: eval_vectordb_latency() | WHAT: fallo | WHY: excepcion.",
                size, exc,
            )

    return results


# ---------------------------------------------------------------------------
# MCP Evals
# ---------------------------------------------------------------------------


def eval_mcp_availability() -> List[EvalResult]:
    """Mide la disponibilidad de herramientas MCP.

    Simula el estado de conexion con servidores MCP y verifica
    que las herramientas registradas respondan correctamente.

    Returns:
        List[EvalResult] con disponibilidad por servidor y global.
    """
    _MCP_SERVERS = [
        {"name": "filesystem", "uptime": 0.99},
        {"name": "web_search", "uptime": 0.97},
        {"name": "code_executor", "uptime": 0.95},
    ]

    results: List[EvalResult] = []
    total_available = 0.0

    for server in _MCP_SERVERS:
        try:
            # Simula ligeras variaciones en disponibilidad
            availability = _random.uniform(
                max(0.85, server["uptime"] - 0.03),
                min(1.0, server["uptime"] + 0.02),
            )

            total_available += availability

            result = EvalResult(
                layer="mcp",
                metric="availability",
                value=round(availability, 4),
                threshold=_DEFAULT_THRESHOLDS["mcp"]["availability"],
                timestamp=datetime.now(timezone.utc).isoformat(),
                metadata={
                    "server": server["name"],
                    "eval_type": "simulated",
                },
            )
            results.append(result)

        except Exception as exc:
            logger.exception(
                "[builtin_evals] Error simulando disponibilidad MCP para '%s': %s. "
                "WHERE: eval_mcp_availability() | WHAT: fallo | WHY: excepcion.",
                server.get("name", "?"), exc,
            )

    # Promedio global
    if results:
        avg_avail = total_available / len(results)
        results.append(EvalResult(
            layer="mcp",
            metric="availability",
            value=round(avg_avail, 4),
            threshold=_DEFAULT_THRESHOLDS["mcp"]["availability"],
            metadata={
                "server": "average",
                "eval_type": "simulated_aggregated",
            },
        ))

    return results


# ---------------------------------------------------------------------------
# Guardrails Evals
# ---------------------------------------------------------------------------


def eval_guardrails_detection() -> List[EvalResult]:
    """Mide la tasa de deteccion y falsos positivos de los guardrails.

    Simula entradas maliciosas y benignas para verificar que los
    filtros de seguridad detectan correctamente las amenazas sin
    generar falsas alarmas.

    Returns:
        List[EvalResult] con detection_rate y false_positive_rate.
    """
    _N_MALICIOUS = 30
    _N_BENIGN = 50

    results: List[EvalResult] = []

    try:
        # Simula deteccion de entradas maliciosas
        detected = sum(1 for _ in range(_N_MALICIOUS) if _random.random() < 0.88)
        detection_rate = detected / _N_MALICIOUS if _N_MALICIOUS > 0 else 0.0

        results.append(EvalResult(
            layer="guardrails",
            metric="detection_rate",
            value=round(detection_rate, 4),
            threshold=_DEFAULT_THRESHOLDS["guardrails"]["detection_rate"],
            metadata={
                "n_malicious": _N_MALICIOUS,
                "n_detected": detected,
                "eval_type": "simulated",
            },
        ))

        # Simula falsos positivos en entradas benignas
        false_positives = sum(1 for _ in range(_N_BENIGN) if _random.random() < 0.08)
        false_positive_rate = false_positives / _N_BENIGN if _N_BENIGN > 0 else 0.0

        results.append(EvalResult(
            layer="guardrails",
            metric="false_positive",
            value=round(false_positive_rate, 4),
            threshold=_DEFAULT_THRESHOLDS["guardrails"]["false_positive"],
            metadata={
                "n_benign": _N_BENIGN,
                "n_false_positives": false_positives,
                "eval_type": "simulated",
            },
        ))

        logger.info(
            "[builtin_evals] Guardrails detection_rate=%.1f%% false_positive=%.1f%%. "
            "WHERE: eval_guardrails_detection()",
            detection_rate * 100, false_positive_rate * 100,
        )

    except Exception as exc:
        logger.exception(
            "[builtin_evals] Error simulando guardrails: %s. "
            "WHERE: eval_guardrails_detection() | WHAT: fallo en simulacion | WHY: excepcion.",
            exc,
        )

    return results


# ---------------------------------------------------------------------------
# Integration Evals
# ---------------------------------------------------------------------------


def eval_integration_e2e() -> List[EvalResult]:
    """Mide la latencia y tasa de exito de flujos end-to-end.

    Simula pipelines completos que atraviesan multiples capas del stack
    (LLM -> RAG -> Agent -> MCP -> Guardrails) y mide el rendimiento
    integral del sistema.

    Returns:
        List[EvalResult] con latencia total y tasa de exito.
    """
    _N_PIPELINES = 10

    results: List[EvalResult] = []

    try:
        total_latency = 0.0
        successes = 0

        for i in range(_N_PIPELINES):
            # Simula latencia acumulada de todas las capas
            pipeline_latency = (
                _random.uniform(0.5, 1.5) +   # LLM
                _random.uniform(0.1, 0.4) +   # RAG retrieval
                _random.uniform(0.3, 0.8) +   # Agent planning
                _random.uniform(0.05, 0.2) +  # MCP tool call
                _random.uniform(0.01, 0.05)   # Guardrails check
            )
            total_latency += pipeline_latency
            # 85-98% de exito
            if _random.random() < _random.uniform(0.85, 0.98):
                successes += 1

        avg_latency = total_latency / _N_PIPELINES
        success_rate = successes / _N_PIPELINES

        results.append(EvalResult(
            layer="integration",
            metric="latency",
            value=round(avg_latency, 4),
            threshold=_DEFAULT_THRESHOLDS["integration"]["latency"],
            metadata={
                "n_pipelines": _N_PIPELINES,
                "unit": "seconds",
                "eval_type": "simulated",
            },
        ))

        results.append(EvalResult(
            layer="integration",
            metric="success_rate",
            value=round(success_rate, 4),
            threshold=_DEFAULT_THRESHOLDS["integration"]["success_rate"],
            metadata={
                "n_pipelines": _N_PIPELINES,
                "n_success": successes,
                "eval_type": "simulated",
            },
        ))

    except Exception as exc:
        logger.exception(
            "[builtin_evals] Error simulando integracion e2e: %s. "
            "WHERE: eval_integration_e2e() | WHAT: fallo en pipeline | WHY: excepcion.",
            exc,
        )

    return results


# ---------------------------------------------------------------------------
# Auto-registro de evaluaciones builtin en el registro global
# ---------------------------------------------------------------------------

register_layer_evals("llm", eval_llm_accuracy, eval_llm_latency, eval_llm_cost)
register_layer_evals("rag", eval_rag_recall, eval_rag_faithfulness)
register_layer_evals("vectordb", eval_vectordb_recall, eval_vectordb_latency)
register_layer_evals("agent", eval_agent_completion, eval_agent_tool_usage)
register_layer_evals("mcp", eval_mcp_availability)
register_layer_evals("guardrails", eval_guardrails_detection)
register_layer_evals("integration", eval_integration_e2e)
