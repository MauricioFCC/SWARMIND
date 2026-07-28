"""
SwarmMode — Ejecucion paralela de agentes en flota (inspirado en CodeWhale fleet).

Permite lanzar multiples agentes en paralelo para tareas complejas.
Cada agente ejecuta su subtarea independientemente y los resultados
se consolidan al final.

Usage:
    swarm = SwarmMode()
    results = swarm.run([
        SwarmTask("builder", "implementar API REST"),
        SwarmTask("scientist", "investigar mejores practicas"),
        SwarmTask("guardian", "auditar seguridad"),
    ])
    print(swarm.consolidate(results))
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SwarmTask:
    """Tarea individual dentro de un swarm de agentes.

    Attributes:
        agent: Identificador del agente que ejecutara la tarea.
        description: Descripcion de la tarea a realizar.
        context: Contexto adicional opcional para la ejecucion.
        priority: Prioridad numerica (mayor valor = mayor prioridad).
    """

    agent: str
    description: str
    context: Optional[str] = None
    priority: int = 5


@dataclass
class SwarmResult:
    """Resultado de la ejecucion de una tarea en el swarm.

    Attributes:
        task: Tarea original ejecutada.
        success: Indica si la ejecucion fue exitosa.
        output: Salida producida por el agente.
        time_seconds: Tiempo de ejecucion en segundos.
        error: Mensaje de error si la ejecucion fallo (None si fue exitosa).
    """

    task: SwarmTask
    success: bool
    output: str
    time_seconds: float
    error: Optional[str] = None


class SwarmMode:
    """Orquestador de ejecucion paralela de agentes en flota (swarm).

    Lanza multiples tareas en paralelo usando un ThreadPoolExecutor
    y consolida los resultados en un reporte unificado.

    Args:
        max_workers: Numero maximo de hilos concurrentes (default 4).
        dispatch_fn: Funcion personalizada para ejecutar tareas.
            Debe aceptar (agent: str, task: str) -> str.
            Si no se provee, usa _mock_dispatch interno.
    """

    def __init__(
        self,
        max_workers: int = 4,
        dispatch_fn: Optional[Callable[[str, str], str]] = None,
    ) -> None:
        """Inicializa el SwarmMode.

        Args:
            max_workers: Maximo de workers concurrentes (default 4).
            dispatch_fn: Funcion de dispatch personalizada.
                Firma: (agent: str, description: str) -> str.
        """
        self._max_workers = max_workers
        self._dispatch = dispatch_fn or self._mock_dispatch

    def run(self, tasks: List[SwarmTask]) -> List[SwarmResult]:
        """Ejecuta una lista de tareas en paralelo usando un pool de hilos.

        Las tareas se ordenan por prioridad descendente en el resultado final.

        Args:
            tasks: Lista de SwarmTask a ejecutar.

        Returns:
            List[SwarmResult]: Resultados ordenados por prioridad descendente.

        Raises:
            ValueError: Si la lista de tareas es None.
        """
        if tasks is None:
            raise ValueError("tasks no puede ser None")

        results: List[SwarmResult] = []
        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            futures = {
                executor.submit(self._execute, task): task for task in tasks
            }
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as exc:
                    # Seguridad ante fallos en el propio future
                    task = futures[future]
                    logger.error(
                        "WHAT=FutureError | "
                        f"WHY=El future para agent={task.agent} lanzó excepción | "
                        f"WHERE=SwarmMode.run | error={exc}"
                    )
                    results.append(
                        SwarmResult(
                            task=task,
                            success=False,
                            output="",
                            time_seconds=0.0,
                            error=str(exc),
                        )
                    )
        return sorted(results, key=lambda r: r.task.priority, reverse=True)

    def _execute(self, task: SwarmTask) -> SwarmResult:
        """Ejecuta una tarea individual y mide su tiempo.

        Args:
            task: SwarmTask a ejecutar.

        Returns:
            SwarmResult con el resultado de la ejecucion.
        """
        start = time.time()
        try:
            output = self._dispatch(task.agent, task.description)
            elapsed = time.time() - start
            logger.info(
                "WHAT=SwarmExecute | "
                f"WHY=Tarea completada para agent={task.agent} | "
                f"WHERE=SwarmMode._execute | time={elapsed:.3f}s | "
                f"success=True"
            )
            return SwarmResult(
                task=task,
                success=True,
                output=str(output),
                time_seconds=elapsed,
            )
        except Exception as e:
            elapsed = time.time() - start
            logger.error(
                "WHAT=SwarmExecute | "
                f"WHY=Tarea fallida para agent={task.agent} | "
                f"WHERE=SwarmMode._execute | time={elapsed:.3f}s | "
                f"error={e}"
            )
            return SwarmResult(
                task=task,
                success=False,
                output="",
                time_seconds=elapsed,
                error=str(e),
            )

    def consolidate(self, results: List[SwarmResult]) -> str:
        """Consolida los resultados del swarm en un reporte legible.

        Args:
            results: Lista de SwarmResult a consolidar.

        Returns:
            str: Reporte formateado con resumen de exitos y fallos.

        Raises:
            ValueError: Si la lista de resultados es None.
        """
        if results is None:
            raise ValueError("results no puede ser None")

        lines: List[str] = [
            "## Resultados del Swarm",
            "",
        ]
        successes = [r for r in results if r.success]
        failures = [r for r in results if not r.success]
        lines.append(f"Exitosos: {len(successes)}/{len(results)}")

        if failures:
            lines.append(f"Fallos: {len(failures)}")
            for f in failures:
                agent = f.task.agent
                error = f.error or "unknown"
                lines.append(f"- {agent}: {error}")

        return "\n".join(lines)

    def _mock_dispatch(self, agent: str, task: str) -> str:
        """Dispatch mock para pruebas sin integracion real.

        Args:
            agent: Nombre del agente.
            task: Descripcion de la tarea.

        Returns:
            str: Respuesta simulada del agente.
        """
        truncated = task[:50] if len(task) > 50 else task
        return f"[{agent}] Ejecutado en swarm: {truncated}..."
