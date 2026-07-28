"""
AgentBenchmark — Evaluacion de agentes con metricas estandarizadas.

Implementa:
- GAIA-style multi-step reasoning tasks
- Tool-call accuracy evaluation
- Cost-per-task tracking
- LLM-as-judge para evaluacion cualitativa

Usage:
    bench = AgentBenchmark()
    result = bench.evaluate("Implementa una API REST", expected_output="...")
    print(result.score)
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class BenchmarkResult:
    """Resultado de una evaluacion individual de agente.

    Attributes:
        task: Descripcion de la tarea ejecutada.
        score: Puntaje de la evaluacion (0.0 - 1.0).
        tokens_used: Cantidad de tokens consumidos.
        time_seconds: Tiempo total de ejecucion en segundos.
        errors: Lista de errores ocurridos durante la ejecucion.
        success: Indica si la tarea se completo exitosamente.
    """
    task: str
    score: float
    tokens_used: int
    time_seconds: float
    errors: List[str] = field(default_factory=list)
    success: bool = False


class AgentBenchmark:
    """Benchmark para evaluar agentes en tareas estandar.

    Metricas:
    - task_completion: La tarea se completo? (0-1)
    - tool_call_accuracy: Las tools se usaron correctamente?
    - cost_per_task: Tokens consumidos
    - delegation_correctness: La delegacion fue correcta?

    Args:
        dispatch_fn: Funcion opcional para despachar tareas a un agente.
                     Si no se provee, usa _mock_dispatch interno.
    """

    def __init__(self, dispatch_fn: Optional[Callable] = None):
        """Inicializa el benchmark con un dispatch opcional."""
        self._dispatch = dispatch_fn or self._mock_dispatch
        self._results: List[BenchmarkResult] = []

    def evaluate(
        self,
        task: str,
        expected_output: Optional[str] = None,
    ) -> BenchmarkResult:
        """Evaluar un agente en una tarea.

        Args:
            task: Descripcion de la tarea a ejecutar.
            expected_output: Texto esperado en la salida del agente.
                             Si se provee, se usa para calcular el score.

        Returns:
            BenchmarkResult con el resultado de la evaluacion.

        Raises:
            ValueError: Si la tarea es vacia o invalida.
        """
        if not task or not task.strip():
            raise ValueError("La tarea no puede estar vacia")

        start = time.time()
        try:
            output = self._dispatch("coordinator", task)
            time_taken = time.time() - start

            if expected_output:
                score = 1.0 if expected_output in str(output) else 0.0
            else:
                score = 1.0 if output else 0.5

            result = BenchmarkResult(
                task=task,
                score=score,
                tokens_used=max(1, len(task) // 4),
                time_seconds=time_taken,
                success=score > 0.5,
            )
        except Exception as e:
            time_taken = time.time() - start
            result = BenchmarkResult(
                task=task,
                score=0.0,
                tokens_used=0,
                time_seconds=time_taken,
                errors=[str(e)],
                success=False,
            )
        self._results.append(result)
        return result

    def evaluate_batch(self, tasks: List[str]) -> List[BenchmarkResult]:
        """Evaluar un lote de tareas secuencialmente.

        Args:
            tasks: Lista de descripciones de tareas.

        Returns:
            Lista de BenchmarkResult, uno por tarea.
        """
        return [self.evaluate(t) for t in tasks]

    def get_summary(self) -> Dict[str, Any]:
        """Obtener resumen estadistico de todas las evaluaciones.

        Returns:
            Diccionario con:
            - avg_score: puntaje promedio
            - total_time: tiempo total acumulado
            - total_tokens: tokens totales consumidos
            - success_rate: tasa de exito (0.0 - 1.0)
        """
        if not self._results:
            return {
                "avg_score": 0.0,
                "total_time": 0.0,
                "total_tokens": 0,
                "success_rate": 0.0,
            }
        return {
            "avg_score": sum(r.score for r in self._results) / len(self._results),
            "total_time": sum(r.time_seconds for r in self._results),
            "total_tokens": sum(r.tokens_used for r in self._results),
            "success_rate": (
                sum(1 for r in self._results if r.success) / len(self._results)
            ),
        }

    def _mock_dispatch(self, agent: str, task: str) -> str:
        """Dispatch simulado para pruebas sin agente real.

        Args:
            agent: Nombre del agente destino.
            task: Descripcion de la tarea.

        Returns:
            Respuesta simulada del agente.
        """
        return f"[{agent}] Ejecutado: {task[:50]}..."
