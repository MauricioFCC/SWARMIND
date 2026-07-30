"""
Evals — Evaluacion Multi-Capa para el AI Factory Stack de Swarmind.

Provee un framework unificado para medir calidad, rendimiento y confiabilidad
a traves de las 7 capas del stack. Cada evaluacion produce metricas accionables,
comparables contra umbrales y trazables en el tiempo.

Arquitectura:
    eval_factory.py   →  EvalResult, EvalSuite, EvalReport, EvalDiff
    builtin_evals.py  →  Evaluaciones incorporadas para cada capa

Uso tipico:
    from harness.evals import run_all, run_layer, compare_reports
    report = run_all()
    for rec in report.recommendations:
        print(rec)

Capas evaluadas:
    1. LLM         — accuracy, latencia, costos por modelo
    2. RAG         — retrieval precision, recall, faithfulness
    3. VectorDB    — recall@k, latency, index quality
    4. Agent       — task completion, tool usage, planning quality
    5. MCP         — tool availability, latency, error rate
    6. Guardrails  — detection rate, false positive rate
    7. Integration — end-to-end latency, success rate
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from harness.evals.eval_factory import (
    EvalResult,
    EvalSuite,
    EvalReport,
    EvalDiff,
    run_all,
    run_layer,
    compare_reports,
    get_recommendations,
)

from harness.evals.builtin_evals import (
    eval_llm_accuracy,
    eval_llm_latency,
    eval_llm_cost,
    eval_rag_recall,
    eval_rag_faithfulness,
    eval_agent_completion,
    eval_agent_tool_usage,
)

logger = logging.getLogger(__name__)

__all__ = [
    "EvalResult",
    "EvalSuite",
    "EvalReport",
    "EvalDiff",
    "run_all",
    "run_layer",
    "compare_reports",
    "get_recommendations",
    "eval_llm_accuracy",
    "eval_llm_latency",
    "eval_llm_cost",
    "eval_rag_recall",
    "eval_rag_faithfulness",
    "eval_agent_completion",
    "eval_agent_tool_usage",
]
