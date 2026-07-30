"""
workflow_patterns.py â€” Patrones de flujo reutilizables para orquestacion de agentes.

4 patrones atomicos simples, intemporales y efectivos:
  1. EVALUATOR_OPTIMIZER: Genera â†’ Evalua â†’ Loop hasta threshold
  2. VOTING: N variantes â†’ Ranking â†’ Mejor
  3. CRITIQUE_REVISE: Genera â†’ Critica â†’ Revisa â†’ Loop
  4. PARALLEL_TRANSFORM: Fan-out â†’ Transforma â†’ Fan-in merge

Uso:
    from harness.orchestrator.workflow_patterns import (
        evaluator_optimizer, voting, critique_revise, parallel_transform
    )
    resultado = evaluator_optimizer(
        generator_fn=mi_generador,
        evaluator_fn=mi_evaluador,
        task="implementar modulo X",
        max_iterations=3,
        quality_threshold=0.8,
    )
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tipos compartidos
# ---------------------------------------------------------------------------

AgentFn = Callable[[str], str]           # (task) -> resultado
EvaluatorFn = Callable[[str, str], float]  # (task, resultado) -> puntaje 0..1
CriticFn = Callable[[str, str], str]       # (task, resultado) -> critica
MergeFn = Callable[[list[str]], str]       # ([resultados]) -> merge


@dataclass
class PatternResult:
    """Resultado estandar de cualquier workflow pattern."""
    success: bool
    output: str
    iterations: int = 0
    scores: list[float] = field(default_factory=list)
    traces: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    total_tokens_est: int = 0


# ---------------------------------------------------------------------------
# Pattern 1: Evaluator-Optimizer
# ---------------------------------------------------------------------------

def evaluator_optimizer(
    generator_fn: AgentFn,
    evaluator_fn: EvaluatorFn,
    task: str,
    max_iterations: int = 3,
    quality_threshold: float = 0.8,
    task_id: str = "",
) -> PatternResult:
    """Genera â†’ Evalua â†’ Loop hasta threshold o max_iterations.

    Args:
        generator_fn: Funcion que genera una solucion.
        evaluator_fn: Funcion que evalua calidad (0..1).
        task: Descripcion de la tarea.
        max_iterations: Maximo de iteraciones.
        quality_threshold: Umbral de calidad para aceptar.
        task_id: ID opcional para trazabilidad.

    Returns:
        PatternResult con la mejor solucion encontrada.
    """
    traces: list[dict[str, Any]] = []
    scores: list[float] = []
    best_output = ""
    best_score = 0.0

    for i in range(1, max_iterations + 1):
        output = generator_fn(task)
        score = evaluator_fn(task, output)
        scores.append(score)
        traces.append({
            "iteration": i,
            "task_id": task_id,
            "score": score,
            "accepted": score >= quality_threshold,
        })

        if score > best_score:
            best_output = output
            best_score = score

        logger.info("E/O iter %d/%d: score=%.2f (threshold=%.2f)", i, max_iterations, score, quality_threshold)

        if score >= quality_threshold:
            return PatternResult(
                success=True,
                output=output,
                iterations=i,
                scores=scores,
                traces=traces,
            )

    return PatternResult(
        success=best_score >= quality_threshold,
        output=best_output,
        iterations=max_iterations,
        scores=scores,
        traces=traces,
        error=f"Mejor score {best_score:.2f} no alcanzo threshold {quality_threshold}" if best_score < quality_threshold else None,
    )


# ---------------------------------------------------------------------------
# Pattern 2: Voting / Ranking
# ---------------------------------------------------------------------------

def voting(
    generator_fns: list[AgentFn],
    evaluator_fn: EvaluatorFn,
    task: str,
    task_id: str = "",
) -> PatternResult:
    """N agentes generan variantes â†’ Se rankean â†’ Mejor se entrega.

    Args:
        generator_fns: Lista de funciones generadoras (3-5 ideal).
        evaluator_fn: Funcion que evalua calidad (0..1).
        task: Descripcion de la tarea.
        task_id: ID opcional para trazabilidad.

    Returns:
        PatternResult con la mejor variante.
    """
    candidates: list[tuple[str, float, int]] = []  # (output, score, index)
    traces: list[dict[str, Any]] = []

    for i, gen_fn in enumerate(generator_fns):
        output = gen_fn(task)
        score = evaluator_fn(task, output)
        candidates.append((output, score, i))
        traces.append({
            "candidate": i,
            "task_id": task_id,
            "score": score,
        })
        logger.info("Voting candidato %d/%d: score=%.2f", i + 1, len(generator_fns), score)

    # Rankear por score descendente
    candidates.sort(key=lambda c: c[1], reverse=True)
    best_output, _best_score, _best_idx = candidates[0]

    return PatternResult(
        success=True,
        output=best_output,
        iterations=len(generator_fns),
        scores=[c[1] for c in candidates],
        traces=traces,
    )


# ---------------------------------------------------------------------------
# Pattern 3: Critique-Revise
# ---------------------------------------------------------------------------

def critique_revise(
    generator_fn: AgentFn,
    critic_fn: CriticFn,
    task: str,
    max_iterations: int = 3,
    task_id: str = "",
) -> PatternResult:
    """Genera â†’ Critica â†’ Revisa â†’ Loop hasta sin critica o max_iterations.

    Args:
        generator_fn: Funcion que genera/refina una solucion.
        critic_fn: Funcion que devuelve critica ("" = sin objeciones).
        task: Descripcion de la tarea.
        max_iterations: Maximo de iteraciones.
        task_id: ID opcional para trazabilidad.

    Returns:
        PatternResult con la solucion revisada.
    """
    traces: list[dict[str, Any]] = []
    current = generator_fn(task)

    for i in range(1, max_iterations + 1):
        critique = critic_fn(task, current)
        traces.append({
            "iteration": i,
            "task_id": task_id,
            "has_critique": bool(critique),
            "critique_length": len(critique),
        })

        if not critique:
            logger.info("C/R iter %d: sin criticas, aceptado", i)
            return PatternResult(
                success=True,
                output=current,
                iterations=i,
                traces=traces,
            )

        current = generator_fn(f"{task}\n---\nCritica anterior:\n{critique}")
        logger.info("C/R iter %d: critica de %d chars, revisando...", i, len(critique))

    return PatternResult(
        success=True,
        output=current,
        iterations=max_iterations,
        traces=traces,
    )


# ---------------------------------------------------------------------------
# Pattern 4: Parallel Transform
# ---------------------------------------------------------------------------

def parallel_transform(
    transform_fns: list[AgentFn],
    merge_fn: MergeFn,
    task: str,
    task_id: str = "",
) -> PatternResult:
    """Fan-out a N transformadores â†’ Cada uno transforma â†’ Fan-in merge.

    Args:
        transform_fns: Lista de funciones transformadoras (ejecutadas en paralelo).
        merge_fn: Funcion que mergea todos los resultados.
        task: Descripcion de la tarea.
        task_id: ID opcional para trazabilidad.

    Returns:
        PatternResult con el resultado mergeado.
    """
    partials: list[str] = []
    traces: list[dict[str, Any]] = []

    for i, tfn in enumerate(transform_fns):
        partial = tfn(task)
        partials.append(partial)
        traces.append({
            "transformer": i,
            "task_id": task_id,
            "partial_length": len(partial),
        })
        logger.info("P/T transformador %d/%d: %d chars", i + 1, len(transform_fns), len(partial))

    merged = merge_fn(partials)
    traces.append({
        "merge": True,
        "task_id": task_id,
        "input_count": len(partials),
        "output_length": len(merged),
    })

    return PatternResult(
        success=True,
        output=merged,
        iterations=len(transform_fns),
        traces=traces,
    )


# ---------------------------------------------------------------------------
# Utilitario: runner con timeout
# ---------------------------------------------------------------------------

def run_with_timeout(fn: Callable, timeout_sec: float = 30.0, *args, **kwargs) -> Any:
    """Ejecuta una funcion con timeout."""
    import threading
    result = [None]
    error = [None]

    def worker():
        try:
            result[0] = fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            error[0] = e

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(timeout=timeout_sec)

    if thread.is_alive():
        raise TimeoutError(f"Funcion excedio timeout de {timeout_sec}s")

    if error[0]:
        raise error[0]

    return result[0]
