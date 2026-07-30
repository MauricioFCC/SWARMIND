# -*- coding: utf-8 -*-
"""
builtin_evals — Evaluaciones incorporadas para las 7 capas del stack Swarmind.

Cada funcion implementa una evaluacion concreta que produce una lista de
EvalResult con metricas cuantitativas. Las evaluaciones son deterministicas
(simuladas con datos sinteticos) y pueden ser reemplazadas por implementaciones
reales que conecten con modelos, bases de datos o agentes en produccion.

Las funciones de evaluacion se han dividido en modulos por capa:
    eval_llm.py      — LLM: accuracy, latency, cost
    eval_rag.py      — RAG: recall, faithfulness
    eval_agent.py    — Agent: completion, tool_usage
    builtin_evals.py — VectorDB, MCP, Guardrails, Integration (este archivo)
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timezone
from typing import Any, Dict, List

from harness.evals.eval_factory import EvalResult, register_layer_evals

# Re-exportar funciones de modulos especializados
from harness.evals.eval_llm import (
    eval_llm_accuracy,
    eval_llm_latency,
    eval_llm_cost,
)
from harness.evals.eval_rag import (
    eval_rag_recall,
    eval_rag_faithfulness,
)
from harness.evals.eval_agent import (
    eval_agent_completion,
    eval_agent_tool_usage,
)

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
    "vectordb": {"recall@k": 0.75, "latency": 0.5, "index_quality": 0.80},
    "mcp": {"availability": 0.95, "latency": 1.0, "error_rate": 0.05},
    "guardrails": {"detection_rate": 0.90, "false_positive": 0.10},
    "integration": {"success_rate": 0.90, "latency": 5.0},
}

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
                expected = min(k, _VECTOR_DIM)
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
            pipeline_latency = (
                _random.uniform(0.5, 1.5) +   # LLM
                _random.uniform(0.1, 0.4) +   # RAG retrieval
                _random.uniform(0.3, 0.8) +   # Agent planning
                _random.uniform(0.05, 0.2) +  # MCP tool call
                _random.uniform(0.01, 0.05)   # Guardrails check
            )
            total_latency += pipeline_latency
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
