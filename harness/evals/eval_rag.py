# -*- coding: utf-8 -*-
"""
eval_rag — Evaluaciones de la capa RAG (recall, faithfulness).

Extraido de builtin_evals.py para mantener modulos < 900 lines.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timezone
from typing import Any, Dict, List

from harness.evals.eval_factory import EvalResult

logger = logging.getLogger(__name__)

# Semilla fija para resultados deterministicos
_SEED = 42
_random = random.Random(_SEED)

# Umbrales por defecto
_DEFAULT_THRESHOLDS: Dict[str, Dict[str, float]] = {
    "rag": {"recall": 0.80, "faithfulness": 0.85},
}


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
                "[eval_rag] RAG recall@%d: %.1f%% (umbral: %.0f%%). "
                "WHERE: eval_rag_recall()",
                k, recall * 100, _DEFAULT_THRESHOLDS["rag"]["recall"] * 100,
            )

        except Exception as exc:
            logger.exception(
                "[eval_rag] Error simulando recall para k=%d: %s. "
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
                "[eval_rag] Error simulando faithfulness para nivel %s: %s. "
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
