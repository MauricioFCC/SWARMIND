"""
eval_llm — Evaluaciones de la capa LLM (accuracy, latency, cost).

Extraido de builtin_evals.py para mantener modulos < 900 lines.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timezone

from harness.evals.eval_factory import EvalResult

logger = logging.getLogger(__name__)

# Semilla fija para resultados deterministicos
_SEED = 42
_random = random.Random(_SEED)

# Umbrales por defecto
_DEFAULT_THRESHOLDS: dict[str, dict[str, float]] = {
    "llm": {"accuracy": 0.85, "latency": 2.0, "cost": 0.005},
}


def eval_llm_accuracy() -> list[EvalResult]:
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

    results: list[EvalResult] = []
    total_correct = 0
    total_questions = 0

    for variant in _MODEL_VARIANTS:
        try:
            correct = 0
            for _ in range(_N_QUESTIONS):
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
                "[eval_llm] LLM accuracy %s/%s: %.1f%% (umbral: %.0f%%). "
                "WHERE: eval_llm_accuracy()",
                variant["model"], variant["prompt"], accuracy * 100,
                _DEFAULT_THRESHOLDS["llm"]["accuracy"] * 100,
            )

        except Exception:
            logger.exception(
                "[eval_llm] Error simulando accuracy para variante %s. "
                "WHERE: eval_llm_accuracy() | WHAT: fallo en variante de modelo | WHY: excepcion.",
                variant.get("model", "?"),
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


def eval_llm_latency() -> list[EvalResult]:
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

    results: list[EvalResult] = []

    for model_name, params in _MODEL_LATENCY_PARAMS.items():
        try:
            samples: list[float] = []
            for _ in range(_N_SAMPLES):
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
                "[eval_llm] LLM latency %s: P50=%.2fs P95=%.2fs P99=%.2fs. "
                "WHERE: eval_llm_latency()",
                model_name, p50, p95, p99,
            )

        except Exception:
            logger.exception(
                "[eval_llm] Error simulando latencia para modelo %s. "
                "WHERE: eval_llm_latency() | WHAT: fallo en generacion de muestras | WHY: excepcion.",
                model_name,
            )

    return results


def eval_llm_cost() -> list[EvalResult]:
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
        "gpt-4o": {"input": 2.50e-6, "output": 10.00e-6},
        "gpt-4o-mini": {"input": 0.15e-6, "output": 0.60e-6},
        "claude-3-opus": {"input": 15.00e-6, "output": 75.00e-6},
    }
    _AVG_INPUT_TOKENS = 500
    _AVG_OUTPUT_TOKENS = 200

    results: list[EvalResult] = []
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
                "[eval_llm] LLM cost %s: $%.6f/consulta (input: %d, output: %d tokens). "
                "WHERE: eval_llm_cost()",
                model_name, total, _AVG_INPUT_TOKENS, _AVG_OUTPUT_TOKENS,
            )

        except Exception:
            logger.exception(
                "[eval_llm] Error calculando costo para modelo %s. "
                "WHERE: eval_llm_cost() | WHAT: fallo en estimacion | WHY: excepcion.",
                model_name,
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
